import csv

import scripts.run_battery as rb


def _write(path, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rb.FIELDS)
        w.writeheader()
        w.writerows(rows)


def _row(date, provider, n_graded, overall=""):
    r = {k: "" for k in rb.FIELDS}
    r.update({"date": date, "provider": provider, "battery_version": "1",
              "model_alias": "m", "errors": 0, "n_graded": n_graded,
              "overall": overall})
    return r


def test_error_row_is_replaced_by_rerun(tmp_path, monkeypatch):
    daily = tmp_path / "daily.csv"
    monkeypatch.setattr(rb, "DAILY", daily)
    _write(daily, [_row("2026-07-13", "gemini", 0)])

    rb.append_daily([_row("2026-07-13", "gemini", 36, overall=0.8)])
    with daily.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["n_graded"] == "36"
    assert rows[0]["overall"] == "0.8"


def test_graded_row_is_immutable(tmp_path, monkeypatch):
    daily = tmp_path / "daily.csv"
    monkeypatch.setattr(rb, "DAILY", daily)
    _write(daily, [_row("2026-07-13", "groq", 36, overall=0.83)])

    rb.append_daily([_row("2026-07-13", "groq", 36, overall=0.99)])
    with daily.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["overall"] == "0.83"


def test_completed_providers_ignores_error_rows(tmp_path, monkeypatch):
    daily = tmp_path / "daily.csv"
    monkeypatch.setattr(rb, "DAILY", daily)
    _write(daily, [
        _row("2026-07-13", "groq", 36, overall=0.83),
        _row("2026-07-13", "gemini", 0),
        _row("2026-07-12", "mistral", 36, overall=0.8),
    ])
    assert rb.completed_providers("2026-07-13") == {"groq"}
    assert rb.completed_providers("2026-07-14") == set()
