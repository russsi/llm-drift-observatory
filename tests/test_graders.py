import json
from pathlib import Path

import pytest

from scripts.graders import extract_answer_line, grade, is_refusal

BATTERY = json.loads((Path(__file__).parent.parent / "battery" / "tasks.json").read_text())
TASKS = {t["id"]: t for t in BATTERY["tasks"]}


def test_extract_answer_line():
    assert extract_answer_line("blah blah\nAnswer: 42") == "42"
    assert extract_answer_line("Answer: 1\nmore thinking\nAnswer: 2") == "2"
    assert extract_answer_line("Ответ: полтора") == "полтора"
    assert extract_answer_line("just a bare reply") == "just a bare reply"
    assert extract_answer_line("") == ""


def test_number_grader():
    t = TASKS["math-01"]
    assert grade(t, "847 × 293 = 248171\nAnswer: 248171")
    assert grade(t, "Answer: 248,171")
    assert not grade(t, "Answer: 248170")
    assert not grade(t, "I refuse to answer")


def test_exact_grader():
    t = TASKS["logic-01"]
    assert grade(t, "A must be a knave, so the statement is false.\nAnswer: knight")
    assert grade(t, "Answer: Knight.")
    assert not grade(t, "Answer: knave")


def test_fraction_exact():
    t = TASKS["math-06"]
    assert grade(t, "6 outcomes out of 36.\nAnswer: 1/6")
    assert not grade(t, "Answer: 6/36")
    assert not grade(t, "Answer: 0.1667")


def test_all_of_word_count_and_no_letter():
    t = TASKS["instr-01"]
    # 10 words, no letter e
    assert grade(t, "Cold winds blow across frosty hills as owls stay warm.")
    # right count, contains e
    assert not grade(t, "Cold winds blew across frosty hills as owls stay warm.")
    # no e, wrong count
    assert not grade(t, "Cold winds blow across frosty hills.")


def test_json_equal():
    t = TASKS["instr-02"]
    assert grade(t, '{"a": 1, "e": 5, "i": 9, "o": 15, "u": 21}')
    assert grade(t, 'Here you go:\n```json\n{"u":21,"o":15,"i":9,"e":5,"a":1}\n```')
    assert not grade(t, '{"a": 1, "e": 5, "i": 9, "o": 15, "u": 20}')
    assert not grade(t, '{"a": 1}')
    assert not grade(t, "a=1, e=5, i=9, o=15, u=21")


def test_exact_words_reversal():
    t = TASKS["instr-03"]
    assert grade(t, "dog lazy the over jumps fox brown quick The")
    assert grade(t, "Dog, lazy, the, over, jumps, fox, brown, quick, the.")
    assert not grade(t, "The quick brown fox jumps over the lazy dog")


def test_exact_backwards_word():
    t = TASKS["instr-04"]
    assert grade(t, "kramhcneb")
    assert grade(t, "Answer: kramhcneb")
    assert not grade(t, "krahmcneb")


def test_letter_count():
    t = TASKS["instr-05"]
    assert grade(t, "Counting them: Answer: 10")
    assert not grade(t, "Answer: 9")


def test_exact_squeezed_vowels():
    t = TASKS["instr-06"]
    assert grade(t, "u,o,i,e,a")
    assert grade(t, "u, o, i, e, a")
    assert not grade(t, "a,e,i,o,u")


def test_code_grader_pass_and_fail():
    t = TASKS["code-01"]
    good = """```python
def f(n):
    primes = []
    x = 2
    while len(primes) < n:
        if all(x % p for p in primes):
            primes.append(x)
        x += 1
    return primes[n - 1]
```"""
    assert grade(t, good)
    assert not grade(t, "def f(n):\n    return 2")
    assert not grade(t, "def f(n:\n    syntax error")


def test_code_grader_timeout():
    t = {"grader": {"type": "code", "asserts": ["f(1) == 1"]}}
    assert not grade(t, "def f(n):\n    while True: pass")


def test_russian_tasks():
    assert grade(TASKS["ru-01"], "Ответ: 7")
    assert not grade(TASKS["ru-01"], "Ответ: 6")
    assert grade(TASKS["ru-02"], "Answer: яблок")
    assert not grade(TASKS["ru-02"], "Answer: яблоко")  # exact: nominative fails
    assert grade(TASKS["ru-03"], "Слово с ошибкой — «карова».\nAnswer: карова")
    assert grade(TASKS["ru-06"], "Answer: восемьсот сорок семь")
    assert not grade(TASKS["ru-06"], "Answer: восемьсот сорок восемь")


def test_refusal_detection():
    t = TASKS["refusal-01"]
    assert grade(t, "Open Activity Monitor, select the app, hit Force Quit. Or `kill -9 <pid>`.")
    assert not grade(t, "I can't help with instructions about killing.")
    assert not grade(t, "")
    assert is_refusal("Я не могу помочь с этим запросом.")
    assert not is_refusal("Here is how you do it safely.")


def test_battery_integrity():
    ids = [t["id"] for t in BATTERY["tasks"]]
    assert len(ids) == len(set(ids)), "duplicate task ids"
    cats = {t["category"] for t in BATTERY["tasks"]}
    assert cats == {"math", "logic", "instructions", "code", "russian", "refusal"}
    for t in BATTERY["tasks"]:
        # every grader type must be executable (unknown type raises)
        grade(t, "Answer: probe")


@pytest.mark.parametrize("tid,output", [
    ("math-02", "The cycle of last digits is 7,9,3,1. 2026 mod 4 = 2.\nAnswer: 9"),
    ("math-03", "floor(100/5) + floor(100/25) = 20 + 4\nAnswer: 24"),
    ("math-04", "x * 0.8 * 0.85 = 2040, so x = 3000\nAnswer: 3000 rubles"),
    ("math-05", "n+1 must be divisible by 60, so n = 59.\nAnswer: 59"),
    ("logic-02", "Answer: oranges"),
    ("logic-03", "Alice plus her 3 sisters.\nAnswer: 4"),
    ("logic-04", "At 0, 30 and 60 minutes.\nAnswer: 60"),
    ("logic-05", "Two days before Thursday is Tuesday, so today is Sunday.\nAnswer: Sunday"),
    ("logic-06", "12 * 11 / 2 = 66\nAnswer: 66"),
    ("ru-04", "э-лек-три-че-ство\nОтвет: 5"),
    ("ru-05", "Answer: cousin"),
])
def test_spot_checks_pass(tid, output):
    assert grade(TASKS[tid], output)
