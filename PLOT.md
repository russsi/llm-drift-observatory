# PLOT — frozen 2026-07-14

This file is the project's mission, frozen the day after it was built. The
resident critic agent grades every change against it. Editing this file to
retroactively justify a feature is the project equivalent of un-freezing a
forecast — don't.

## Mission (one sentence)

Publish daily, deterministic, publicly auditable evidence of whether free-tier
LLM APIs silently change behind their stable model names — on a site that
updates itself with zero manual operation.

## Why this project exists for its builder

- It must be **public and used by strangers** — the artifact is the site and
  the dataset, not the code.
- The steady-state loop must be **fully unattended**. The only planned manual
  act is one launch post after ~2 weeks of history.
- Its moat is **time**: an unbroken daily record nobody can recreate later.
  Anything that risks breaking the record is worse than anything that merely
  looks unpolished.

## Non-goals (things this project deliberately is NOT)

1. **Not a leaderboard.** We never rank models by capability; we detect change.
2. **Not a benchmark suite.** 36 tasks is the instrument; growing it endlessly
   is instrument-tampering, not progress (additions only via versioned battery,
   only with a change-detection justification).
3. **Not a forecasting project.** No predictions, ever. Measurement only.
4. **Not a paid/monetized product.** No accounts, no API keys for visitors,
   no hosting beyond GitHub Pages.
5. **Not an LLM-judged system.** Deterministic graders only — this is
   load-bearing for credibility and non-negotiable.

## Definition of done for v1

- [x] 5 providers watched, daily cron, deterministic grading, drift alerts
- [x] Self-contained public dashboard (charts, task browser, alerts, raw data)
- [ ] 7 consecutive green daily runs with ≥4 complete provider measurements
- [x] Repo public + GitHub Pages live (2026-07-14)
- [ ] One launch post (r/LocalLLaMA and/or HN) once ~14 days of history exist

After v1 is done: **stop building for two weeks** and let the data accumulate.
The backlog (private holdout battery, more providers) waits until there is
evidence real visitors want it.

## Frozen operating rules (added 2026-07-19, before day 7)

Added once, dated, after the resident critic demanded they exist in writing
*before* the situations arise. These are additions of constraint, not
retroactive justification.

1. **Succession rule.** A series that produces zero graded tasks for **3
   consecutive days** must be succeeded (new series, day zero, changelog
   entry) or retired in the very next change to the repo. No per-case
   negotiation; the record does not wait for a provider to feel better.
2. **Streak rule.** The DoD's "7 consecutive green days" is literal. If the
   streak breaks, the count restarts at zero and the launch date slips.
   The definition is never relaxed to protect a calendar date.
3. **Design freeze.** The dashboard's visual design is frozen as of
   2026-07-19 until the post-launch two-week quiet period has passed.
   Permitted site changes until then: new series slots, and fixes for
   things that are broken — not things that are ugly.
4. **History is append-only.** No force-push, rebase, or filter of
   published history, ever again. The last permitted rewrite happened
   2026-07-19 (author-identity privacy fix), pre-launch. Post-launch the
   git history is part of the instrument.

## The gate for any new idea

Before adding anything, it must pass all four:
1. Does it serve a *visitor* of the public site, or the *unbroken record*?
2. Does it add zero recurring manual work?
3. Does it leave the frozen battery and grading untouched?
4. Would we still want it if nobody ever praised the code?
