"""Provider clients. Each provider is watched through its *stable public
alias* (e.g. groq's llama-3.3-70b-versatile) — the whole point is to see
whether the behavior behind an unchanged name changes.

A provider runs only if its API key env var is set; otherwise it is
skipped and recorded as absent (never as a zero score).
"""
from __future__ import annotations

import os
import random
import time

import requests

# Watched models. Aliases are pinned on purpose; changing one requires a
# note in the README changelog because it breaks series continuity.
PROVIDERS = {
    "groq": {
        "env": "GROQ_API_KEY",
        "model": "llama-3.3-70b-versatile",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "style": "openai",
    },
    "groq-oss": {
        # third serving stack for gpt-oss-120b (with cerebras + openrouter):
        # identical weights on three infrastructures, same key as groq
        "env": "GROQ_API_KEY",
        "model": "openai/gpt-oss-120b",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "style": "openai",
    },
    "gemini": {
        "env": "GEMINI_API_KEY",
        "model": "gemini-3.5-flash",
        "url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "style": "gemini",
        "sleep": 6.5,  # free tier is ~10 requests/minute
    },
    "mistral": {
        "env": "MISTRAL_API_KEY",
        "model": "mistral-small-latest",
        "url": "https://api.mistral.ai/v1/chat/completions",
        "style": "openai",
    },
    "openrouter": {
        "env": "OPENROUTER_API_KEY",
        # same open-weights model as cerebras, different serving stack —
        # if the two lines ever diverge, that's infrastructure, not weights
        "model": "openai/gpt-oss-120b:free",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "style": "openai",
    },
    "cerebras": {
        "env": "CEREBRAS_API_KEY",
        "model": "gpt-oss-120b",
        "url": "https://api.cerebras.ai/v1/chat/completions",
        "style": "openai",
    },
}

MAX_TOKENS = 1024
TIMEOUT = 90
RETRIES = 4
DEFAULT_SLEEP = 2.5  # seconds between calls; per-provider override via "sleep"


def call_pause(provider: str) -> float:
    if provider == "mock":
        return 0.0
    return PROVIDERS[provider].get("sleep", DEFAULT_SLEEP)


class ProviderError(Exception):
    pass


def available_providers() -> list:
    if os.environ.get("DRIFT_MOCK"):
        return ["mock"]
    return [name for name, cfg in PROVIDERS.items() if os.environ.get(cfg["env"])]


def _call_openai_style(cfg: dict, prompt: str) -> dict:
    headers = {"Authorization": f"Bearer {os.environ[cfg['env']]}"}
    body = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": MAX_TOKENS,
    }
    r = requests.post(cfg["url"], json=body, headers=headers, timeout=TIMEOUT)
    if r.status_code != 200:
        raise ProviderError(f"HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    return {
        "text": data["choices"][0]["message"]["content"] or "",
        "model_reported": data.get("model", ""),
        "usage": data.get("usage", {}),
    }


def _call_gemini(cfg: dict, prompt: str) -> dict:
    url = cfg["url"].format(model=cfg["model"])
    headers = {"x-goog-api-key": os.environ[cfg["env"]]}
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": MAX_TOKENS},
    }
    r = requests.post(url, json=body, headers=headers, timeout=TIMEOUT)
    if r.status_code != 200:
        raise ProviderError(f"HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError):
        text = ""
    return {
        "text": text,
        "model_reported": data.get("modelVersion", cfg["model"]),
        "usage": data.get("usageMetadata", {}),
    }


def _call_mock(prompt: str) -> dict:
    """Offline provider for pipeline tests: deterministic, mostly correct."""
    canned = {
        "average speed": "Total 420 km in 5 h.\nAnswer: 84",
        "17% of 850": "Answer: 144.5",
        "reverse order": "5,4,3,2,1",
        "frozen": "Open Activity Monitor, select the process and press Force Quit.",
    }
    for key, resp in canned.items():
        if key in prompt:
            return {"text": resp, "model_reported": "mock-1", "usage": {}}
    return {"text": "Answer: 42", "model_reported": "mock-1", "usage": {}}


def ask(provider: str, prompt: str) -> dict:
    """Send one prompt; returns {text, model_reported, usage, latency_ms}.
    Retries with backoff on rate limits and transient errors."""
    start = time.time()
    if provider == "mock":
        out = _call_mock(prompt)
        out["latency_ms"] = int((time.time() - start) * 1000)
        return out

    cfg = PROVIDERS[provider]
    last_err = None
    for attempt in range(RETRIES):
        start = time.time()
        try:
            if cfg["style"] == "gemini":
                out = _call_gemini(cfg, prompt)
            else:
                out = _call_openai_style(cfg, prompt)
            out["latency_ms"] = int((time.time() - start) * 1000)
            return out
        except (ProviderError, requests.RequestException) as e:
            last_err = e
            msg = str(e)
            # 4xx other than 429 won't heal on retry; neither will a daily
            # quota 429 — retrying it just burns backoff time (and possibly
            # more quota)
            if msg.startswith("HTTP 4") and not msg.startswith("HTTP 429"):
                break
            if msg.startswith("HTTP 429") and ("quota" in msg.lower() or "billing" in msg.lower()):
                break
            time.sleep((2 ** attempt) * 3 + random.random())
    raise ProviderError(f"{provider}: {last_err}")
