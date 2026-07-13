"""Shared constants — single source of truth (critic charge #6)."""

# A day counts as measured only if at least this many of the 36 battery
# tasks were graded. Partial days (quota ran out mid-run) are excluded from
# charts, baselines and alerts, and may be replaced by a same-day rerun.
MIN_VALID = 30
