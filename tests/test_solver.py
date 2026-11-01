"""3차 모델까지 실패했을 때의 완전 탐색 배정 — 공고 3장 어려운 해결."""

import time

from assign_solver import infeasible_reason, solve
from domain import Student
from rules import validate_assignment, validate_teams


def S(no, main, *subs):
    return Student(no, f"학생{no}", main, tuple(subs))


def test_해가_있으면_규칙을_모두_지키는_배정을_찾는다():
    teams = {1: [S("1", "기획자")], 2: [S("2", "웹 프로그래머")]}
    left = [S("3", "웹 프로그래머"), S("4", "기획자")]
    plan = solve(teams, left)
    assert plan is not None
    assert validate_assignment(teams, left, plan) == []


def test_기존_팀원을_옮기지_않는다():
    teams = {1: [S("1", "기획자")], 2: [S("2", "웹 프로그래머")]}
    left = [S("3", "웹 프로그래머"), S("4", "기획자")]
    plan = solve(teams, left)
    assert set(plan) == {"3", "4"}


def test_빈_팀도_2명_이상으로_채운다():
    teams = {1: [S("1", "기획자"), S("2", "웹 프로그래머")], 2: []}
    left = [S("3", "기획자"), S("4", "웹 프로그래머")]
    plan = solve(teams, left)
    assert plan == {"3": 2, "4": 2}


def test_웹_프로그래머가_모자라면_해가_없다():
    teams = {1: [S("1", "기획자")], 2: [S("2", "기획자")]}
    left = [S("3", "웹 프로그래머"), S("4", "테스터")]
    assert solve(teams, left) is None


def test_해가_없을_때_이유를_설명한다():
    teams = {1: [S("1", "기획자")], 2: [S("2", "기획자")]}
    left = [S("3", "웹 프로그래머"), S("4", "테스터")]
    reason = infeasible_reason(teams, left)
    assert "웹 프로그래머" in reason


def test_학생이_모자라면_그_이유를_말한다():
    teams = {1: [], 2: [], 3: []}
    left = [S("1", "기획자"), S("2", "웹 프로그래머")]
    assert "2명 이상" in infeasible_reason(teams, left)


def test_꽉_찬_팀에_필수역할이_없으면_그_이유를_말한다():
    teams = {
        1: [S("1", "테스터"), S("2", "발표자"), S("3", "보고서 작성자"), S("4", "프론트엔드 디자이너")],
        2: [S("5", "기획자"), S("6", "웹 프로그래머")],
    }
    assert "팀1" in infeasible_reason(teams, [])


def test_어려움_규모에서도_빨리_끝난다():
    """16명 4팀 — 채점 때 멈추면 안 된다."""
    teams = {
        1: [S("1", "기획자", "보고서 작성자"), S("4", "웹 프로그래머", "기획자"), S("7", "프론트엔드 디자이너", "발표자", "테스터")],
        2: [S("2", "기획자", "발표자"), S("8", "프론트엔드 디자이너", "테스터"), S("5", "웹 프로그래머", "프론트엔드 디자이너")],
        3: [S("11", "테스터", "발표자"), S("15", "발표자", "프론트엔드 디자이너")],
        4: [],
    }
    left = [
        S("3", "기획자", "테스터"),
        S("6", "웹 프로그래머", "보고서 작성자"),
        S("9", "프론트엔드 디자이너", "웹 프로그래머"),
        S("10", "테스터", "보고서 작성자"),
        S("12", "테스터", "기획자"),
        S("13", "보고서 작성자", "발표자", "프론트엔드 디자이너"),
        S("14", "보고서 작성자", "테스터"),
        S("16", "발표자"),
    ]
    started = time.monotonic()
    plan = solve(teams, left)
    assert plan is not None
    assert time.monotonic() - started < 5

    merged = {no: list(ms) for no, ms in teams.items()}
    for no, team_no in plan.items():
        merged[team_no].append(next(s for s in left if s.student_no == no))
    assert validate_teams(merged) == []
