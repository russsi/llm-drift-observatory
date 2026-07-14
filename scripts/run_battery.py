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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scripts import providers
from scripts.config import MIN_VALID
from scripts.graders import grade, is_refusal

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "data" / "results"
DAILY = ROOT / "data" / "daily.csv"
BATTERY = ROOT / "battery" / "tasks.json"

CATEGORIES = ["math", "logic", "instructions", "code", "russian", "refusal"]
# after this many consecutive 429s that survived the full retry/backoff
# cycle, stop calling — the remaining tasks would all fail the same way
QUOTA_ABORT_AFTER = 3
FIELDS = (
    ["date", "provider", "battery_version", "model_alias", "model_reported", "overall"]
    + CATEGORIES
    + ["stability", "latency_p50_ms", "errors", "n_graded"]
)


def load_battery() -> dict:
    return json.loads(BATTERY.read_text())


def previous_probe_texts(provider: str, today: str) -> dict:
    """Most recent raw file before today, for stability comparison."""
    if not RESULTS.exists():
        return {}
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
    quota_streak = 0

    for task in battery["tasks"]:
        if quota_streak >= QUOTA_ABORT_AFTER:
            errors += 1
            records.append({"id": task["id"], "category": task["category"],
                            "error": "skipped: persistent 429s (quota or rate limit)"})
            continue
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
            quota_streak = 0
        except Exception as e:  # any per-task failure is an error record,
            # never a crashed provider — a crash would cost the whole day
            errors += 1
            err = (str(e) or type(e).__name__)[:800]
            records.append({"id": task["id"], "category": task["category"],
                            "error": err})
            # a 429 here already survived the full retry/backoff cycle (or
            # named a per-day quota), so a streak of them means the rest of
            # the battery would fail the same way
            quota_streak = quota_streak + 1 if "HTTP 429" in err else 0
        time.sleep(providers.call_pause(provider))

    for probe in battery["stability_probes"]:
        try:
            resp = providers.ask(provider, probe["prompt"])
            probe_records.append({"id": probe["id"], "output": resp["text"]})
        except Exception as e:
            errors += 1
            probe_records.append({"id": probe["id"], "output": "",
                                  "error": (str(e) or type(e).__name__)[:800]})
        time.sleep(providers.call_pause(provider))

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
    partial = len(graded) < MIN_VALID  # a partial day is not a measurement:
    # its scores never enter the CSV (the raw transcripts keep every detail)
    summary = {
        "date": today,
        "provider": provider,
        "battery_version": battery["version"],
        "model_alias": "mock-1" if provider == "mock" else providers.PROVIDERS[provider]["model"],
        "model_reported": model_reported,
        "overall": "" if partial else round(sum(r["passed"] for r in graded) / len(graded), 4),
        **({c: "" for c in CATEGORIES} if partial else by_cat),
        "stability": "" if partial or not sims else round(statistics.mean(sims), 4),
        "latency_p50_ms": "" if partial or not latencies else int(statistics.median(latencies)),
        "errors": errors,
        "n_graded": len(graded),
    }

    # raw transcripts are written by main() only if append_daily accepts
    # the row — a heal rerun that graded *less* must not clobber the raw
    # file backing the better row already in the CSV (happened 2026-07-14:
    # a 0-graded gemini rerun overwrote the 22-graded transcripts)
    return {"summary": summary, "tasks": records, "stability_probes": probe_records}


def write_raw(payload: dict) -> None:
    s = payload["summary"]
    day_dir = RESULTS / s["date"]
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / f"{s['provider']}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1))


def completed_providers(date: str) -> set:
    """Providers that already have a complete measured row for this date.
    Partial rows (n_graded < MIN_VALID) don't count, so a rerun can heal."""
    if not DAILY.exists():
        return set()
    with DAILY.open() as f:
        return {r["provider"] for r in csv.DictReader(f)
                if r["date"] == date and int(r["n_graded"] or 0) >= MIN_VALID}


def append_daily(rows: list) -> set:
    """One row per provider+date. A complete row (n_graded >= MIN_VALID) is
    immutable; a partial or error-only row may be replaced by a rerun that
    graded strictly more tasks. Returns the (date, provider) keys accepted,
    so the caller persists raw transcripts only for rows that count."""
    existing = []
    if DAILY.exists():
        with DAILY.open() as f:
            existing = list(csv.DictReader(f))
    by_key = {(r["date"], r["provider"]): r for r in existing}
    accepted = set()
    for row in rows:
        key = (row["date"], row["provider"])
        old = by_key.get(key)
        old_n = int(old["n_graded"] or 0) if old else -1
        if old is None or (old_n < MIN_VALID and row["n_graded"] > old_n):
            by_key[key] = {k: row[k] for k in FIELDS}
            accepted.add(key)
    with DAILY.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for key in sorted(by_key):
            w.writerow(by_key[key])
    return accepted


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args()

    battery = load_battery()
    active = providers.available_providers()
    if not active:
        raise SystemExit("No provider API keys configured (and DRIFT_MOCK not set).")

    done = completed_providers(args.date)
    if done:
        print(f"already graded today, skipping: {', '.join(sorted(done))}")
        active = [p for p in active if p not in done]

    print(f"battery v{battery['version']}, providers: {', '.join(active) or '(none left)'}")
    payloads = []
    if active:
        # providers have independent rate limits, so they run in parallel;
        # pacing between calls to the SAME provider is preserved inside
        # run_provider
        with ThreadPoolExecutor(max_workers=len(active)) as pool:
            futures = {p: pool.submit(run_provider, p, battery, args.date) for p in active}
            for p, fut in futures.items():
                try:
                    payloads.append(fut.result())
                except Exception as e:  # one broken provider must not cost
                    # the other providers their measurements
                    print(f"{p}: PROVIDER CRASHED: {str(e)[:300]}", flush=True)
                    continue
                row = payloads[-1]["summary"]
                print(f"{p}: overall={row['overall']} errors={row['errors']}", flush=True)
                first_err = next((r["error"] for r in payloads[-1]["tasks"]
                                  if r.get("error") and not r["error"].startswith("skipped")), None)
                if first_err:
                    print(f"{p}: first error: {first_err[:300]}", flush=True)
    accepted = append_daily([pl["summary"] for pl in payloads])
    for pl in payloads:
        s = pl["summary"]
        if (s["date"], s["provider"]) in accepted:
            write_raw(pl)
        else:
            print(f"{s['provider']}: rerun graded no more than the existing "
                  f"row — row and raw transcripts kept from the earlier run")
    print(f"done: {len(accepted)} provider(s) recorded for {args.date}")


if __name__ == "__main__":
    main()
