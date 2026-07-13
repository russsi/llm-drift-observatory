"""Compare today's scores against each provider's trailing baseline and
raise alerts when something moved beyond noise.

Honesty rules encoded here:
  - no drift claims until a provider has >= MIN_HISTORY prior days;
  - a move counts only if it exceeds max(2 sigma of the trailing window,
    an absolute floor) — the floor stops 2-sigma-of-nearly-zero-noise
    false alarms early on;
  - every alert (and every quiet day) is appended to data/drift_log.jsonl,
    so misfires stay on the record.

If GITHUB_TOKEN + GITHUB_REPOSITORY are set (as in Actions), each alert
also opens a GitHub issue.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import statistics
from pathlib import Path

import requests

from scripts.config import MIN_VALID

ROOT = Path(__file__).resolve().parent.parent
DAILY = ROOT / "data" / "daily.csv"
LOG = ROOT / "data" / "drift_log.jsonl"

MIN_HISTORY = 5          # prior days required before drift can be claimed
WINDOW = 7               # trailing baseline window
# Absolute floors sit above one-task quantization noise: a category has 6
# tasks, so a single flip moves it 16.7pp — the 20pp floor demands at least
# two flips. Overall has 36 tasks (one flip = 2.8pp), so 12pp stays meaningful.
SCORE_FLOORS = {"overall": 0.12, "default": 0.20}
STABILITY_FLOOR = 0.55   # same-prompt similarity below this is suspicious
LATENCY_RATIO = 3.0      # p50 shift beyond this ratio is suspicious
SCORE_METRICS = ["overall", "math", "logic", "instructions", "code", "russian", "refusal"]


def load_rows() -> list:
    if not DAILY.exists():
        return []
    with DAILY.open() as f:
        return list(csv.DictReader(f))


def _fl(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def check_provider(rows: list, today: str) -> list:
    """rows: all daily.csv rows for one provider, dates ascending.
    Partial days (quota ran out mid-battery) are not measurements — they
    enter neither the baseline nor today's comparison. Rows from a different
    battery version are a different instrument and never mix into a baseline."""
    rows = [r for r in rows if int(r["n_graded"] or 0) >= MIN_VALID]
    todays = [r for r in rows if r["date"] == today]
    if todays:
        version = todays[-1]["battery_version"]
        rows = [r for r in rows if r["battery_version"] == version]
    history = [r for r in rows if r["date"] < today]
    if not todays or len(history) < MIN_HISTORY:
        return []
    cur = todays[-1]
    window = history[-WINDOW:]
    alerts = []

    for metric in SCORE_METRICS:
        now = _fl(cur[metric])
        base = [_fl(r[metric]) for r in window]
        base = [b for b in base if b is not None]
        if now is None or len(base) < MIN_HISTORY:
            continue
        mean = statistics.mean(base)
        sd = statistics.stdev(base) if len(base) > 1 else 0.0
        threshold = max(2 * sd, SCORE_FLOORS.get(metric, SCORE_FLOORS["default"]))
        if abs(now - mean) > threshold:
            alerts.append({
                "type": "score_shift", "metric": metric,
                "today": now, "baseline_mean": round(mean, 4),
                "baseline_sd": round(sd, 4), "threshold": round(threshold, 4),
                "direction": "drop" if now < mean else "jump",
            })

    prev_model = next((r["model_reported"] for r in reversed(history) if r["model_reported"]), "")
    if prev_model and cur["model_reported"] and cur["model_reported"] != prev_model:
        alerts.append({"type": "model_id_change", "was": prev_model, "now": cur["model_reported"]})

    stab = _fl(cur["stability"])
    if stab is not None and stab < STABILITY_FLOOR:
        alerts.append({"type": "output_instability", "similarity_vs_prev_day": stab,
                       "floor": STABILITY_FLOOR})

    lat_now = _fl(cur["latency_p50_ms"])
    lat_base = [_fl(r["latency_p50_ms"]) for r in window]
    lat_base = [x for x in lat_base if x]
    if lat_now and lat_base:
        med = statistics.median(lat_base)
        if med > 0 and (lat_now / med > LATENCY_RATIO or med / lat_now > LATENCY_RATIO):
            alerts.append({"type": "latency_shift", "today_ms": lat_now, "baseline_ms": med})

    return alerts


def open_issue(provider: str, model: str, today: str, alerts: list) -> None:
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("  (no GITHUB_TOKEN/REPOSITORY — issue not opened)")
        return
    lines = [f"Drift detected for **{provider}** (`{model}`) on {today}:", ""]
    for a in alerts:
        lines.append(f"- `{a['type']}`: " + json.dumps({k: v for k, v in a.items() if k != "type"}))
    lines += ["", f"Raw transcripts: `data/results/{today}/{provider}.json`",
              "", "_Opened automatically by detect_drift.py._"]
    r = requests.post(
        f"https://api.github.com/repos/{repo}/issues",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json"},
        json={"title": f"[drift] {provider} {today}: " + ", ".join(a["type"] for a in alerts),
              "body": "\n".join(lines), "labels": ["drift-alert"]},
        timeout=30,
    )
    print(f"  issue: HTTP {r.status_code}")


def logged_keys() -> set:
    """(date, provider) pairs already in the append-only log — the log is
    part of the auditable dataset, so a rerun must never duplicate entries."""
    if not LOG.exists():
        return set()
    keys = set()
    for line in LOG.read_text().splitlines():
        e = json.loads(line)
        keys.add((e["date"], e["provider"]))
    return keys


def main() -> None:
    today = os.environ.get("DRIFT_DATE", dt.date.today().isoformat())
    rows = load_rows()
    providers_today = sorted({r["provider"] for r in rows if r["date"] == today})
    already = logged_keys()

    log_entries = []
    for p in providers_today:
        if (today, p) in already:
            print(f"{p}: already logged for {today}, skipping")
            continue
        p_rows = sorted((r for r in rows if r["provider"] == p), key=lambda r: r["date"])
        alerts = check_provider(p_rows, today)
        model = p_rows[-1]["model_alias"]
        entry = {"date": today, "provider": p, "alerts": alerts}
        log_entries.append(entry)
        if alerts:
            print(f"{p}: {len(alerts)} alert(s)")
            open_issue(p, model, today, alerts)
        else:
            n_hist = len([r for r in p_rows if r["date"] < today])
            status = "quiet" if n_hist >= MIN_HISTORY else f"warming up ({n_hist}/{MIN_HISTORY} days)"
            print(f"{p}: {status}")

    with LOG.open("a") as f:
        for e in log_entries:
            f.write(json.dumps(e) + "\n")


if __name__ == "__main__":
    main()
