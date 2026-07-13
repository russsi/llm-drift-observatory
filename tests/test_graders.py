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
    assert grade(t, "Total is 420 km over 5 h.\nAnswer: 84")
    assert grade(t, "Answer: 84.0 km/h")
    assert grade(t, "The average speed is 84 km/h")  # falls back to last line
    assert not grade(t, "Answer: 96")
    assert not grade(t, "I refuse to answer")


def test_exact_grader():
    t = TASKS["logic-01"]
    assert grade(t, "Answer: Anna")
    assert grade(t, "Answer: anna.")
    assert not grade(t, "Answer: Boris")


def test_contains_all():
    t = TASKS["logic-03"]
    assert grade(t, "A quarter and a nickel — only ONE of them is not a nickel.")
    assert not grade(t, "A dime and two dimes")


def test_regex_full_three_caps_words():
    t = TASKS["instr-01"]
    assert grade(t, "VAST DEEP BLUE")
    assert grade(t, "VAST, DEEP, BLUE.")
    assert not grade(t, "Vast deep blue")
    assert not grade(t, "VAST DEEP BLUE OCEAN")


def test_json_object():
    t = TASKS["instr-02"]
    assert grade(t, '{"city": "Paris", "population": 2148000}')
    assert grade(t, 'Sure!\n```json\n{"city": "Astana", "population": 1350000}\n```')
    assert not grade(t, '{"city": "Paris"}')
    assert not grade(t, '{"city": "Paris", "population": "big"}')
    assert not grade(t, '{"city": "Paris", "population": 2.1}')
    assert not grade(t, "Paris has 2.1M people")


def test_word_count():
    t = TASKS["instr-03"]
    assert grade(t, "Cats sleep all day and hunt at night.")
    assert not grade(t, "Cats sleep a lot.")


def test_exact_squeezed():
    t = TASKS["instr-04"]
    assert grade(t, "5,4,3,2,1")
    assert grade(t, "5, 4, 3, 2, 1")
    assert not grade(t, "1,2,3,4,5")


def test_anagram():
    t = TASKS["instr-06"]
    assert grade(t, "silent")
    assert grade(t, "Answer: enlist")
    assert grade(t, "tinsel")
    assert not grade(t, "listen")
    assert not grade(t, "lists")


def test_code_grader_pass_and_fail():
    t = TASKS["code-01"]
    good = """```python
def f(n):
    if n % 15 == 0: return 'fizzbuzz'
    if n % 3 == 0: return 'fizz'
    if n % 5 == 0: return 'buzz'
    return n
```"""
    bad = "def f(n):\n    return 'fizz'"
    assert grade(t, good)
    assert not grade(t, bad)
    assert not grade(t, "def f(n:\n    syntax error")


def test_code_grader_timeout():
    t = {"grader": {"type": "code", "asserts": ["f(1) == 1"]}}
    assert not grade(t, "def f(n):\n    while True: pass")


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
    ("math-02", "17% of 850 = 144.5\nAnswer: 144.5"),
    ("math-06", "Answer: 96%"),
    ("logic-04", "Answer: Wednesday"),
    ("ru-01", "Ответ: 6"),
    ("ru-05", "Answer: dragonfly"),
    ("ru-06", "Полтора больше.\nAnswer: полтора"),
])
def test_spot_checks_pass(tid, output):
    assert grade(TASKS[tid], output)
