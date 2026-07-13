from scripts.detect_drift import check_provider


def mkrow(date, overall, **kw):
    row = {
        "date": date, "provider": "groq", "battery_version": "1",
        "model_alias": "llama-3.3-70b-versatile", "model_reported": "llama-3.3-70b-versatile",
        "overall": str(overall), "math": str(overall), "logic": str(overall),
        "instructions": str(overall), "code": str(overall), "russian": str(overall),
        "refusal": "1.0", "stability": "0.8", "latency_p50_ms": "900",
        "errors": "0", "n_graded": "36",
    }
    row.update({k: str(v) for k, v in kw.items()})
    return row


def days(n, overall=0.85):
    return [mkrow(f"2026-07-{i+1:02d}", overall) for i in range(n)]


def test_no_alerts_before_min_history():
    rows = days(3) + [mkrow("2026-07-04", 0.30)]
    assert check_provider(rows, "2026-07-04") == []


def test_stable_scores_stay_quiet():
    rows = days(7) + [mkrow("2026-07-08", 0.86)]
    assert check_provider(rows, "2026-07-08") == []


def test_big_drop_fires_score_alert():
    rows = days(7) + [mkrow("2026-07-08", 0.55)]
    alerts = check_provider(rows, "2026-07-08")
    kinds = {a["type"] for a in alerts}
    assert "score_shift" in kinds
    drop = next(a for a in alerts if a["type"] == "score_shift")
    assert drop["direction"] == "drop"


def test_small_wobble_below_floor_is_ignored():
    rows = days(7) + [mkrow("2026-07-08", 0.80)]  # -5pp < 0.12 floor
    assert check_provider(rows, "2026-07-08") == []


def test_model_id_change_always_flags():
    rows = days(7) + [mkrow("2026-07-08", 0.85, model_reported="llama-3.3-70b-q4")]
    kinds = {a["type"] for a in check_provider(rows, "2026-07-08")}
    assert "model_id_change" in kinds


def test_instability_flags():
    rows = days(7) + [mkrow("2026-07-08", 0.85, stability=0.30)]
    kinds = {a["type"] for a in check_provider(rows, "2026-07-08")}
    assert "output_instability" in kinds


def test_latency_shift_flags():
    rows = days(7) + [mkrow("2026-07-08", 0.85, latency_p50_ms=4000)]
    kinds = {a["type"] for a in check_provider(rows, "2026-07-08")}
    assert "latency_shift" in kinds


def test_missing_today_is_quiet():
    rows = days(7)
    assert check_provider(rows, "2026-07-08") == []


def test_partial_days_excluded_everywhere():
    # 7 good days, then a partial day with a huge apparent drop: no alert,
    # because a partial day is not a measurement
    rows = days(7) + [mkrow("2026-07-08", 0.30, n_graded=3)]
    assert check_provider(rows, "2026-07-08") == []
    # and partial days don't poison the baseline either
    rows = days(7) + [mkrow("2026-07-08", 0.10, n_graded=3)] + [mkrow("2026-07-09", 0.85)]
    assert check_provider(rows, "2026-07-09") == []


def test_single_task_flip_in_category_stays_quiet():
    # one flipped task in a 6-task category = 16.7pp, below the 20pp floor
    rows = days(7, 0.8333) + [mkrow("2026-07-08", 0.8333, math=0.6667)]
    assert check_provider(rows, "2026-07-08") == []


def test_two_task_flip_in_category_alerts():
    rows = days(7, 0.8333) + [mkrow("2026-07-08", 0.8333, math=0.5)]
    alerts = check_provider(rows, "2026-07-08")
    assert any(a["type"] == "score_shift" and a["metric"] == "math" for a in alerts)


def test_battery_versions_never_share_a_baseline():
    # 7 days of v1 history, then a v2 day with a huge apparent drop:
    # no alert, because v2 has no baseline of its own yet
    rows = days(7, 0.9) + [mkrow("2026-07-08", 0.30, battery_version="2")]
    assert check_provider(rows, "2026-07-08") == []
