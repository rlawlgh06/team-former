"""공고 2.7절 표의 key 와 같은지 확인한다. 하나라도 틀리면 감점 15번(-5점)."""

import re

import keys

# 공고 2.7절 표를 그대로 옮긴 것. keys.py 를 고쳐도 이 값은 고치지 않는다.
EXPECTED = {
    "LOGIN_STUDENT_NO": "login_student_no",
    "LOGIN_PASSWORD": "login_password",
    "LOGIN_SUBMIT": "login_submit",
    "WHOAMI": "whoami",
    "RESULT": "result",
    "ADMIN_ROSTER_FILE": "admin_roster_file",
    "ADMIN_TEAM_COUNT": "admin_team_count",
    "ADMIN_START": "admin_start",
    "ADMIN_CLOSE": "admin_close",
    "UNASSIGNED": "unassigned",
    "ADMIN_ASSIGN": "admin_assign",
    "ASSIGN_STATUS": "assign_status",
    "ADMIN_CONFIRM": "admin_confirm",
}

SAFE = re.compile(r"^[A-Za-z0-9_]+$")


def test_상수의_key_가_공고와_같다():
    for name, expected in EXPECTED.items():
        assert getattr(keys, name) == expected, name


def test_번호가_붙는_key():
    assert keys.team_key(1) == "team_1"
    assert keys.team_key(12) == "team_12"
    assert keys.apply_key(3) == "apply_3"


def test_학번이_붙는_key():
    assert keys.vote_yes_key("2026306") == "vote_yes_2026306"
    assert keys.vote_no_key("2026306") == "vote_no_2026306"


def test_key_에는_영문_숫자_밑줄만_쓴다():
    생성된_key = [
        *EXPECTED.values(),
        keys.team_key(1),
        keys.apply_key(1),
        keys.vote_yes_key("2026101"),
        keys.vote_no_key("2026101"),
    ]
    for k in 생성된_key:
        assert SAFE.match(k), k
