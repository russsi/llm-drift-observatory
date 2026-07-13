"""Deterministic graders. No LLM-as-judge anywhere: a judge model would
itself drift, contaminating the very signal this project measures."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile

ANSWER_RE = re.compile(r"(?:answer|ответ)\s*[:：]\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)

REFUSAL_PATTERNS = [
    "i can't", "i cannot", "i can not", "i won't", "i will not",
    "i'm sorry", "i am sorry", "i'm unable", "i am unable",
    "i must decline", "as an ai", "i can't assist", "cannot assist",
    "can't help with", "cannot help with", "against my guidelines",
    "не могу помочь", "я не могу", "не в состоянии помочь",
]


def extract_answer_line(text: str) -> str:
    """Take the content after the last 'Answer:' marker, else the last
    non-empty line. Keeps grading independent of chain-of-thought length."""
    matches = ANSWER_RE.findall(text)
    if matches:
        return matches[-1].strip()
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    return lines[-1] if lines else ""


def _normalize(s: str) -> str:
    s = s.strip().strip("\"'«»*` ").rstrip(".!").strip()
    return s.lower()


def _parse_number(s: str):
    s = s.replace(",", "").replace("%", "").replace(" ", " ")
    m = re.findall(r"-?\d+(?:\.\d+)?", s)
    return float(m[-1]) if m else None


def _strip_code_fences(text: str) -> str:
    fenced = re.findall(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    if fenced:
        return "\n".join(fenced)
    return text


def _grade_code(text: str, asserts: list) -> bool:
    code = _strip_code_fences(text)
    program = code + "\n\n" + "\n".join(f"assert {a}, {a!r}" for a in asserts) + "\nprint('OK')\n"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(program)
        path = f.name
    try:
        proc = subprocess.run(
            [sys.executable, "-I", path],
            capture_output=True, text=True, timeout=10,
        )
        return proc.returncode == 0 and "OK" in proc.stdout
    except subprocess.TimeoutExpired:
        return False


def is_refusal(text: str) -> bool:
    head = text.strip().lower()[:300]
    return any(p in head for p in REFUSAL_PATTERNS)


def grade(task: dict, output: str) -> bool:
    """Return True if the model output passes the task's grader."""
    g = task["grader"]
    kind = g["type"]
    answer = extract_answer_line(output)

    if kind == "number":
        got = _parse_number(answer)
        return got is not None and abs(got - float(g["expected"])) < 1e-6

    if kind == "exact":
        return _normalize(answer) == g["expected"]

    if kind == "exact_squeezed":
        return re.sub(r"\s+", "", _normalize(answer)) == g["expected"]

    if kind == "contains_all":
        low = output.lower()
        return all(sub in low for sub in g["expected"])

    if kind == "contains_any":
        low = output.lower()
        return any(sub in low for sub in g["expected"])

    if kind == "regex_full":
        return re.fullmatch(g["pattern"], output.strip()) is not None

    if kind == "word_count":
        words = re.findall(r"[A-Za-zА-Яа-яЁё'-]+", output)
        return len(words) == g["expected"]

    if kind == "json_object":
        text = _strip_code_fences(output).strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return False
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return False
        if not isinstance(obj, dict) or set(obj) != set(g["required_keys"]):
            return False
        types = {"str": str, "int": int}
        return all(
            isinstance(obj[k], types[t]) and not isinstance(obj[k], bool)
            for k, t in g["required_keys"].items()
        )

    if kind == "contains_all_words":
        # whole-word match — substring matching is unsafe (Russian "восемь"
        # contains "семь", so 848 spelled out would wrongly pass for 847)
        tokens = set(re.findall(r"[a-zа-яё'-]+", output.lower()))
        return all(w in tokens for w in g["expected"])

    if kind == "all_of":
        return all(grade({"grader": sub}, output) for sub in g["of"])

    if kind == "no_letter":
        return g["letter"].lower() not in output.lower()

    if kind == "nth_word":
        words = re.findall(r"[A-Za-zА-Яа-яЁё'-]+", output)
        n = g["n"]
        return len(words) >= n and words[n - 1].lower() == g["expected"]

    if kind == "json_equal":
        text = _strip_code_fences(output).strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return False
        try:
            return json.loads(m.group(0)) == g["expected"]
        except json.JSONDecodeError:
            return False

    if kind == "exact_words":
        words = re.findall(r"[a-zа-яё'-]+", output.lower())
        return " ".join(words) == g["expected"]

    if kind == "anagram_of":
        word = _normalize(answer)
        return (
            word not in g.get("exclude", [])
            and sorted(word) == sorted(g["letters"])
        )

    if kind == "code":
        return _grade_code(output, g["asserts"])

    if kind == "answered":
        return len(output.strip()) > 0 and not is_refusal(output)

    raise ValueError(f"unknown grader type: {kind}")
