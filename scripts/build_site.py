"""Regenerate docs/data.json from data/daily.csv + data/drift_log.jsonl.
The site (docs/index.html) is static; this file is its only data source."""
from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DAILY = ROOT / "data" / "daily.csv"
LOG = ROOT / "data" / "drift_log.jsonl"
OUT = ROOT / "docs" / "data.json"

# Fixed display order = fixed palette slot per provider (never reassigned).
PROVIDER_ORDER = ["groq", "gemini", "mistral", "openrouter", "cerebras", "mock"]


def main() -> None:
    rows = []
    if DAILY.exists():
        with DAILY.open() as f:
            for r in csv.DictReader(f):
                for k in ("overall", "math", "logic", "instructions", "code",
                          "russian", "refusal", "stability"):
                    r[k] = float(r[k]) if r[k] else None
                for k in ("latency_p50_ms", "errors", "n_graded"):
                    r[k] = int(float(r[k])) if r[k] else 0
                rows.append(r)
    rows.sort(key=lambda r: (r["date"], r["provider"]))

    alerts = []
    if LOG.exists():
        for line in LOG.read_text().splitlines():
            e = json.loads(line)
            if e.get("alerts"):
                alerts.append(e)
    alerts = alerts[-50:]

    providers = sorted(
        {r["provider"] for r in rows},
        key=lambda p: PROVIDER_ORDER.index(p) if p in PROVIDER_ORDER else 99,
    )
    models = {}
    for r in rows:
        models[r["provider"]] = r["model_alias"]

    OUT.write_text(json.dumps({
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "battery_version": rows[-1]["battery_version"] if rows else "1",
        "providers": providers,
        "models": models,
        "rows": rows,
        "alerts": alerts,
    }, ensure_ascii=False))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(rows)} rows, {len(alerts)} alert days")


if __name__ == "__main__":
    main()
