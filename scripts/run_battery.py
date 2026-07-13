"""Daily battery run: ask every watched model the frozen battery, grade
deterministically, persist raw outputs and one summary row per provider.

Raw outputs:  data/results/<date>/<provider>.json  (full transcripts)
Summary:      data/daily.csv                        (one row/provider/day)

Scores are computed once and never recomputed for past days.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import difflib
import json
import statistics
import time
from pathlib import Path

from scripts import providers
from scripts.graders import grade, is_refusal

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "data" / "results"
DAILY = ROOT / "data" / "daily.csv"
BATTERY = ROOT / "battery" / "tasks.json"

CATEGORIES = ["math", "logic", "instructions", "code", "russian", "refusal"]
FIELDS = (
    ["date", "provider", "battery_version", "model_alias", "model_reported", "overall"]
    + CATEGORIES
    + ["stability", "latency_p50_ms", "errors", "n_graded"]
)
SLEEP_BETWEEN_CALLS = 2.5  # seconds; stays well under every free-tier RPM cap


def load_battery() -> dict:
    return json.loads(BATTERY.read_text())


def previous_probe_texts(provider: str, today: str) -> dict:
    """Most recent raw file before today, for stability comparison."""
    days = sorted(d.name for d in RESULTS.iterdir() if d.is_dir() and d.name < today)
    for day in reversed(days):
        f = RESULTS / day / f"{provider}.json"
        if f.exists():
            raw = json.loads(f.read_text())
            return {p["id"]: p["output"] for p in raw.get("stability_probes", [])}
    return {}


def run_provider(provider: str, battery: dict, today: str) -> dict:
    suffix = battery["answer_suffix"]
    records, probe_records, errors, latencies = [], [], 0, []

    for task in battery["tasks"]:
        prompt = task["prompt"] + (suffix if task["use_answer_suffix"] else "")
        try:
            resp = providers.ask(provider, prompt)
            passed = grade(task, resp["text"])
            records.append({
                "id": task["id"], "category": task["category"],
                "output": resp["text"], "passed": passed,
                "latency_ms": resp["latency_ms"],
                "model_reported": resp["model_reported"],
                "refused": is_refusal(resp["text"]),
            })
            latencies.append(resp["latency_ms"])
        except providers.ProviderError as e:
            errors += 1
            records.append({"id": task["id"], "category": task["category"],
                            "error": str(e)[:300]})
        time.sleep(SLEEP_BETWEEN_CALLS if provider != "mock" else 0)

    for probe in battery["stability_probes"]:
        try:
            resp = providers.ask(provider, probe["prompt"])
            probe_records.append({"id": probe["id"], "output": resp["text"]})
        except providers.ProviderError as e:
            errors += 1
            probe_records.append({"id": probe["id"], "output": "", "error": str(e)[:300]})
        time.sleep(SLEEP_BETWEEN_CALLS if provider != "mock" else 0)

    prev = previous_probe_texts(provider, today)
    sims = [
        difflib.SequenceMatcher(None, prev[p["id"]], p["output"]).ratio()
        for p in probe_records if p.get("output") and prev.get(p["id"])
    ]

    graded = [r for r in records if "passed" in r]
    by_cat = {}
    for cat in CATEGORIES:
        cat_rows = [r for r in graded if r["category"] == cat]
        by_cat[cat] = round(sum(r["passed"] for r in cat_rows) / len(cat_rows), 4) if cat_rows else ""

    model_reported = next((r["model_reported"] for r in graded if r.get("model_reported")), "")
    summary = {
        "date": today,
        "provider": provider,
        "battery_version": battery["version"],
        "model_alias": "mock-1" if provider == "mock" else providers.PROVIDERS[provider]["model"],
        "model_reported": model_reported,
        "overall": round(sum(r["passed"] for r in graded) / len(graded), 4) if graded else "",
        **by_cat,
        "stability": round(statistics.mean(sims), 4) if sims else "",
        "latency_p50_ms": int(statistics.median(latencies)) if latencies else "",
        "errors": errors,
        "n_graded": len(graded),
    }

    day_dir = RESULTS / today
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / f"{provider}.json").write_text(json.dumps({
        "summary": summary, "tasks": records, "stability_probes": probe_records,
    }, ensure_ascii=False, indent=1))
    return summary


def append_daily(rows: list) -> None:
    exists = DAILY.exists()
    # never write two rows for the same provider+date (idempotent reruns)
    seen = set()
    if exists:
        with DAILY.open() as f:
            seen = {(r["date"], r["provider"]) for r in csv.DictReader(f)}
    with DAILY.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        for row in rows:
            if (row["date"], row["provider"]) not in seen:
                w.writerow(row)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args()

    battery = load_battery()
    active = providers.available_providers()
    if not active:
        raise SystemExit("No provider API keys configured (and DRIFT_MOCK not set).")

    print(f"battery v{battery['version']}, providers: {', '.join(active)}")
    rows = []
    for p in active:
        print(f"→ {p} ...", flush=True)
        row = run_provider(p, battery, args.date)
        rows.append(row)
        print(f"  overall={row['overall']} errors={row['errors']}")
    append_daily(rows)
    print(f"done: {len(rows)} provider(s) recorded for {args.date}")


if __name__ == "__main__":
    main()
