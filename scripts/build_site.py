"""Regenerate docs/data.json from data/daily.csv + data/drift_log.jsonl.
The site (docs/index.html) is static; this file is its only data source."""
from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

from scripts.config import MIN_VALID
from scripts.providers import PROVIDERS

ROOT = Path(__file__).resolve().parent.parent
DAILY = ROOT / "data" / "daily.csv"
LOG = ROOT / "data" / "drift_log.jsonl"
BATTERY = ROOT / "battery" / "tasks.json"
OUT = ROOT / "docs" / "data.json"

# Fixed display order = fixed palette slot per provider (never reassigned).
PROVIDER_ORDER = ["groq", "gemini", "mistral", "openrouter", "openrouter-llama",
                  "cerebras", "groq-oss", "mock"]

SCORE_KEYS = ("overall", "math", "logic", "instructions", "code",
              "russian", "refusal", "stability")


def main() -> None:
    battery = json.loads(BATTERY.read_text())
    current_version = str(battery["version"])

    rows = []
    if DAILY.exists():
        with DAILY.open() as f:
            for r in csv.DictReader(f):
                for k in SCORE_KEYS:
                    r[k] = float(r[k]) if r[k] else None
                for k in ("latency_p50_ms", "errors", "n_graded"):
                    r[k] = int(float(r[k])) if r[k] else 0
                # not chartable: partial days aren't measurements, and rows
                # from an older battery version are a different instrument
                if r["n_graded"] < MIN_VALID or r["battery_version"] != current_version:
                    for k in SCORE_KEYS:
                        r[k] = None
                    r["latency_p50_ms"] = 0
                rows.append(r)
    rows.sort(key=lambda r: (r["date"], r["provider"]))

    alerts = []
    if LOG.exists():
        for line in LOG.read_text().splitlines():
            e = json.loads(line)
            if e.get("alerts"):
                alerts.append(e)
    alerts = alerts[-50:]

    # shown on the site: currently watched series, plus any retired series
    # that has at least one valid measurement under the current battery
    # version (its line ends where the alias died). A series that is both
    # dead and empty on this version (e.g. openrouter's gpt-oss-120b:free,
    # which OpenRouter killed before one valid v2 day) would render as a
    # permanent dash-only ghost — the README changelog is its record.
    has_valid = {r["provider"] for r in rows if r["overall"] is not None}
    providers = sorted(
        set(PROVIDERS) | has_valid,
        key=lambda p: PROVIDER_ORDER.index(p) if p in PROVIDER_ORDER else 99,
    )
    models = {p: cfg["model"] for p, cfg in PROVIDERS.items()}
    for r in rows:  # retired series keep the alias they were watched under
        if r["provider"] not in PROVIDERS:
            models[r["provider"]] = r["model_alias"]

    tasks_pub = [
        {"id": t["id"], "category": t["category"], "prompt": t["prompt"],
         "grader": {"type": t["grader"]["type"]}}
        for t in battery["tasks"]
    ]

    OUT.write_text(json.dumps({
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "battery_version": rows[-1]["battery_version"] if rows else "1",
        "providers": providers,
        "models": models,
        "rows": rows,
        "alerts": alerts,
        "battery": tasks_pub,
    }, ensure_ascii=False))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(rows)} rows, {len(alerts)} alert days")


if __name__ == "__main__":
    main()
