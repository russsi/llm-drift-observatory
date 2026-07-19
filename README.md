# LLM Drift Observatory

**Daily evidence of silent model changes behind stable API names.**

When you call `llama-3.3-70b-versatile` or `mistral-small-latest`, the name stays
the same — but the provider can quietly swap what's behind it: a quantized build,
a new safety filter, different serving infrastructure. Nothing is announced.
Users are left with a vague feeling that "the model got dumber."

This project catches that. Every day at 05:47 UTC, a GitHub Action sends the
**same frozen battery of 36 tasks** to the same models across several free-tier
providers, grades every answer with **deterministic code**, and commits the
scores to this repo. One day of scores means nothing; months of a flat line
mean that when the line moves, *something changed on their side* — and this
repo has the timestamped receipts.

**Live dashboard:** see the GitHub Pages site for this repo (`docs/`).

## What is measured

| Category | 6 tasks each | Grading |
|---|---|---|
| math | word problems, exact numeric answers | parse number, exact match |
| logic | syllogisms, classic traps | exact / substring match |
| instructions | format constraints (word counts, JSON shape, exact strings) | regex / parser |
| code | small Python functions | asserts run in a sandboxed subprocess |
| russian | comprehension & translation in Russian | exact / substring match |
| refusal | harmless questions models tend to over-refuse | refusal-pattern detector |

Plus per provider per day: **median latency**, **error rate**, reported model id,
and **output stability** — similarity of temperature-0 answers to the same three
probe prompts versus the previous day.

## Watched models

Aliases are pinned on purpose — the experiment is whether behavior behind an
unchanged name changes (see `scripts/providers.py`):

- Groq — `llama-3.3-70b-versatile`
- Groq — `openai/gpt-oss-120b` (series `groq-oss`)
- Google — `gemini-3.5-flash`
- Mistral — `mistral-small-latest`
- OpenRouter — `nvidia/nemotron-3-super-120b-a12b:free` (series `openrouter-nemotron`)
- Cerebras — `gpt-oss-120b`

One same-weights pair runs on purpose: gpt-oss-120b on Groq + Cerebras —
identical weights on different serving stacks. If the pair's lines
diverge, the difference is infrastructure (quantization, sampling,
batching), not the weights. (A second pair, llama-3.3-70b on Groq +
OpenRouter, was planned but OpenRouter's free llama endpoint never
delivered a single valid day — see the changelog.)

## When a watched alias dies mid-record

Providers retire models (it happened in this project's first 24 hours). The
rule, fixed in advance: **a dead alias ends its series** — the line stops on
its last measured day and the death is recorded in the changelog below. A
successor model starts a **new series from day zero**. A series is never
silently re-pointed at different weights, because the series *is* the claim
"same name, watched daily."

## Changelog

- 2026-07-13 (before first graded run for these providers): gemini
  `2.5-flash`→`3.5-flash` (key had no access), cerebras
  `llama-3.3-70b`→`gpt-oss-120b` (model retired), openrouter
  `llama-3.3-70b:free`→`gpt-oss-120b:free` (persistent upstream congestion).
- 2026-07-14: **battery v2 replaces v1** after exactly one live day: v1
  saturated on reasoning models (97% on cerebras), leaving no headroom to
  observe drift. Done at the cheapest possible moment; v1 day-1 data stays
  in the repo, marked `battery_version=1`, and never mixes with v2 charts
  or baselines. Also added: `groq-oss` series (third stack for gpt-oss-120b).
- 2026-07-14: **`openrouter` series died on v2 day one** — OpenRouter moved
  `openai/gpt-oss-120b:free` to paid-only (HTTP 404: "This model is
  unavailable for free"). Exactly the kind of silent free-tier change this
  project watches for; the failed day stays in the repo as the record.
  Successor series `openrouter-llama` (`meta-llama/llama-3.3-70b-instruct:free`)
  starts from day zero and pairs with groq's llama-3.3-70b as a second
  same-weights comparison.
- 2026-07-15: retry/abort logic fixed — per-*minute* 429s (which cerebras
  and gemini both phrase in quota/billing language) were being treated as
  daily exhaustion, aborting runs a 20-second wait would have healed.
  Cost cerebras and gemini their 2026-07-14 measurements. Only a 429 that
  explicitly names a per-day window ends a run now.
- 2026-07-19: **`openrouter-llama` series succeeded after zero valid days** —
  every call 2026-07-14..19 failed "temporarily rate-limited upstream" (at
  peak and off-peak alike), and by 07-19 OpenRouter listed no free llama
  (or qwen) endpoint at all. The series dies with no measured days, so
  nothing breaks; the six failed days stay in the repo as the record.
  Successor series `openrouter-nemotron` (`nvidia/nemotron-3-super-120b-a12b:free`,
  4 live upstream endpoints at succession time) starts from day zero. The
  planned llama same-weights pair is dropped rather than re-pointed.

A provider is skipped (recorded as absent, never as zero) if no API key is
configured for it.

## Honesty rules

1. **The battery is frozen.** Tasks are never edited or deleted once live. New
   tasks may only be added under a bumped battery version, and scores are
   always reported per version — no silent moving of the goalposts.
2. **No LLM judges.** Every grader is deterministic code. A judge model would
   itself drift, contaminating the signal.
3. **Scores are never recomputed.** Each day's results are graded once and
   committed; raw transcripts live in `data/results/<date>/` for anyone to audit.
4. **Drift is claimed conservatively.** No alerts until a provider has ≥5 days
   of baseline; a move counts only beyond max(2σ of the trailing 7 days, 12
   percentage points). Every alert — including false alarms — stays permanently
   in `data/drift_log.jsonl`.
5. **Known limitation, stated up front:** the battery is public, so a provider
   could in principle train on it. With 36 tasks the incentive is ~zero, but a
   private holdout battery is the planned v2 mitigation. Score *jumps* are
   therefore reported with the same prominence as drops.
6. **One day is noise.** The dashboard shows baselines and thresholds; nothing
   is called "drift" from a single bad day unless it clears the noise band.
7. **Partial days are not measurements.** If a provider's daily quota runs out
   mid-battery, fewer than 30 of 36 graded tasks means the day is excluded
   from charts, baselines and alerts (the raw transcripts stay in the repo),
   and a same-day rerun may replace it with a complete measurement. Scoring
   3 lucky tasks as "100%" would be exactly the kind of lie this project
   exists to avoid.

## Architecture

```
GitHub Actions (daily cron)
  └─ scripts/run_battery.py    ask 36 tasks + 3 probes per provider (temp 0)
       └─ scripts/graders.py   deterministic grading
  └─ scripts/detect_drift.py   compare vs trailing baseline → GitHub issue on alert
  └─ scripts/build_site.py     regenerate docs/data.json
  └─ git commit                data/ and docs/ pushed back to the repo
GitHub Pages serves docs/ — a self-contained static dashboard, no backend.
```

## Running it yourself

```bash
pip install -r requirements.txt
python -m pytest tests/ -q            # graders + drift detector
DRIFT_MOCK=1 python -m scripts.run_battery   # offline end-to-end smoke run
```

For real runs, set any of `GROQ_API_KEY`, `GEMINI_API_KEY`, `MISTRAL_API_KEY`,
`OPENROUTER_API_KEY`, `CEREBRAS_API_KEY` (repo secrets in Actions). All have
free tiers; the daily run uses ~39 requests per provider.

## FAQ

**Why free-tier models?** They're what hobbyists and indie builders actually
depend on, they're the most likely to be silently downgraded under cost
pressure, and it keeps the observatory reproducible by anyone at zero cost.

**Isn't 36 tasks small?** Yes — deliberately. The goal isn't to rank models
(use real benchmarks for that); it's *change detection* on a fixed instrument.
For detecting a step-change in the line, a small battery run every day for
months beats a huge battery run once.

**Day-to-day wiggles?** Expected — inference is not perfectly deterministic
even at temperature 0. That's exactly why alerts require clearing a noise band
measured from the instrument itself.
