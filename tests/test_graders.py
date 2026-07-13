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
    assert grade(t, "73914 × 8267 = 611047038\nAnswer: 611047038")
    assert grade(t, "Answer: 611,047,038")
    assert not grade(t, "Answer: 611047037")
    assert not grade(t, "I refuse to answer")


def test_exact_grader():
    t = TASKS["logic-01"]
    assert grade(t, "A must be a knave, so the statement is false.\nAnswer: knight")
    assert grade(t, "Answer: Knight.")
    assert not grade(t, "Answer: knave")


def test_digit_sum_count():
    t = TASKS["math-06"]
    assert grade(t, "Stars and bars gives C(12,4).\nAnswer: 495")
    assert not grade(t, "Answer: 715")


def test_all_of_word_count_and_no_letter():
    t = TASKS["instr-01"]
    # 10 words, no letter e
    assert grade(t, "Cold winds blow across frosty hills as owls stay warm.")
    # right count, contains e
    assert not grade(t, "Cold winds blew across frosty hills as owls stay warm.")
    # no e, wrong count
    assert not grade(t, "Cold winds blow across frosty hills.")


def test_json_equal_grader():
    t = {"grader": {"type": "json_equal", "expected": {"a": 1, "b": 2}}}
    assert grade(t, '{"a": 1, "b": 2}')
    assert grade(t, '```json\n{"b":2,"a":1}\n```')
    assert not grade(t, '{"a": 1, "b": 3}')
    assert not grade(t, "a=1, b=2")


def test_compound_sentence_task():
    t = TASKS["instr-02"]
    # 12 words, 4th word is "drift", no letter o anywhere
    assert grade(t, "The great engine drift travels quickly swiftly beneath silver evening skies still.")
    # contains the letter o ("moves", "morning", "today")
    assert not grade(t, "The big machine called drift moves quietly under bright morning skies today.")
    # 4th word wrong
    assert not grade(t, "The great big engine drift travels swiftly beneath silver evening skies still.")


def test_exact_words_grader():
    t = {"grader": {"type": "exact_words", "expected": "dog lazy the"}}
    assert grade(t, "Dog, lazy, the.")
    assert not grade(t, "the lazy dog")


def test_cyrillic_reversal():
    t = TASKS["instr-03"]
    assert grade(t, "ьтсонбосопсоноробо")
    assert grade(t, "Answer: ьтсонбосопсоноробо")
    assert not grade(t, "обороноспособность")


def test_cyrillic_letter_count():
    t = TASKS["instr-04"]
    assert grade(t, "Считаем внимательно.\nAnswer: 16")
    assert not grade(t, "Answer: 15")


def test_letter_count():
    t = TASKS["instr-05"]
    assert grade(t, "Counting them: Answer: 10")
    assert not grade(t, "Answer: 9")


def test_exact_squeezed_positions():
    t = TASKS["instr-06"]
    assert grade(t, "3,1,2")
    assert grade(t, "3, 1, 2")
    assert not grade(t, "1,2,3")


def test_code_grader_pass_and_fail():
    t = TASKS["code-01"]
    good = """```python
def f(n):
    primes = []
    for x in range(2, n):
        if all(x % p for p in primes):
            primes.append(x)
    return len(primes)
```"""
    assert grade(t, good)
    assert not grade(t, "def f(n):\n    return 4")
    assert not grade(t, "def f(n:\n    syntax error")


def test_code_grader_timeout():
    t = {"grader": {"type": "code", "asserts": ["f(1) == 1"]}}
    assert not grade(t, "def f(n):\n    while True: pass")


def test_russian_tasks():
    assert grade(TASKS["ru-01"], "Ответ: 7")
    assert not grade(TASKS["ru-01"], "Ответ: 6")
    assert grade(TASKS["ru-02"], "Answer: яблок")
    assert not grade(TASKS["ru-02"], "Answer: яблоко")  # exact: nominative fails
    assert grade(TASKS["ru-03"], "звонИт — ударение на второй слог.\nAnswer: 2")
    assert not grade(TASKS["ru-03"], "Answer: 1")
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
    ("math-03", "100 + 20 + 4 = 124\nAnswer: 124"),
    ("math-04", "1.25 * 0.6 = 0.75, and 360/0.75 = 480.\nAnswer: 480"),
    ("math-05", "n+1 must be divisible by 60, so n = 59.\nAnswer: 59"),
    ("logic-02", "Answer: oranges"),
    ("logic-03", "In both cases C is lying.\nAnswer: knave"),
    ("logic-04", "Each match eliminates one player.\nAnswer: 136"),
    ("logic-05", "16 + 9 + 4 + 1 = 30\nAnswer: 30"),
    ("logic-06", "5! = 120\nAnswer: 120"),
    ("ru-04", "э-лек-три-че-ство\nОтвет: 5"),
    ("ru-05", "Answer: дрейф"),
])
def test_spot_checks_pass(tid, output):
    assert grade(TASKS[tid], output)
