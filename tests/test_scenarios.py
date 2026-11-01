"""공고 부록의 연습용 시나리오 3개를 그대로 돌려 기대 결과와 맞춰 본다.

이 파일은 tests/ 안에만 있고 앱 코드는 이 파일을 모른다. 시나리오 이름이나
순서에 맞춰 결과를 미리 정해 두는 코드는 앱에 넣지 않는다 (감점 19번).
"""

from pathlib import Path

import pytest

from assign_solver import solve
from domain import VOTE_NO, VOTE_YES
from engine import (
    apply_to_team,
    build_state,
    cast_vote,
    close_recruiting,
    members,
    pending_application_of,
    unassigned,
)
from roster import parse_roster
from rules import validate_assignment, validate_teams

HERE = Path(__file__).parent

# ("지원", 학번, 팀번호, 기대 첫 단어)
# ("투표", 지원자 학번, 투표자 학번, 찬성|거부, 기대 첫 단어)

쉬움 = {
    "csv": "쉬움.csv",
    "teams": 3,
    "steps": [
        ("지원", "2026101", 1, "승인"),
        ("지원", "2026102", 2, "승인"),
        ("지원", "2026103", 3, "승인"),

        ("지원", "2026104", 1, "대기"),
        ("투표", "2026104", "2026101", VOTE_YES, "승인"),

        ("지원", "2026105", 2, "대기"),
        ("투표", "2026105", "2026102", VOTE_YES, "승인"),

        ("지원", "2026107", 1, "대기"),
        ("투표", "2026107", "2026101", VOTE_YES, "대기"),
        ("투표", "2026107", "2026104", VOTE_NO, "거절"),

        ("지원", "2026106", 3, "대기"),
        ("투표", "2026106", "2026103", VOTE_YES, "승인"),
    ],
    "남는_학생": {"2026107", "2026108"},
}

중간 = {
    "csv": "중간.csv",
    "teams": 4,
    "steps": [
        ("지원", "2026201", 1, "승인"),

        ("지원", "2026205", 1, "대기"),
        ("투표", "2026205", "2026201", VOTE_YES, "승인"),

        # 3단계: 주 역할 중복이라 지원이 막히므로 뒤의 투표는 건너뛴다
        ("지원", "2026202", 1, "막힘"),

        ("지원", "2026206", 2, "승인"),

        ("지원", "2026209", 2, "대기"),
        ("투표", "2026209", "2026206", VOTE_YES, "승인"),

        ("지원", "2026210", 2, "대기"),
        ("투표", "2026210", "2026206", VOTE_YES, "대기"),
        ("투표", "2026210", "2026209", VOTE_NO, "거절"),

        ("지원", "2026203", 3, "승인"),
        ("지원", "2026211", 4, "승인"),

        ("지원", "2026212", 4, "대기"),
        ("지원", "2026212", 3, "막힘"),

        ("마감",),

        ("지원", "2026202", 3, "막힘"),
    ],
    # 마감 때 학생12의 지원은 거절되고, 1명뿐인 팀3·팀4 는 해산한다
    "남는_학생": {
        "2026202", "2026203", "2026204", "2026207",
        "2026208", "2026210", "2026211", "2026212",
    },
}

어려움 = {
    "csv": "어려움.csv",
    "teams": 4,
    "steps": [
        ("지원", "2026301", 1, "승인"),

        ("지원", "2026304", 1, "대기"),
        ("투표", "2026304", "2026301", VOTE_YES, "승인"),

        ("지원", "2026307", 1, "대기"),
        ("투표", "2026307", "2026301", VOTE_YES, "대기"),
        ("투표", "2026307", "2026304", VOTE_YES, "승인"),

        ("지원", "2026302", 2, "승인"),

        ("지원", "2026308", 2, "대기"),
        ("투표", "2026308", "2026302", VOTE_YES, "승인"),

        # 6단계: 두 명이 차례로 지원해 둘 다 대기
        ("지원", "2026305", 2, "대기"),
        ("지원", "2026306", 2, "대기"),

        ("투표", "2026305", "2026302", VOTE_YES, "대기"),
        ("투표", "2026305", "2026308", VOTE_YES, "승인"),

        # 8단계: 앞의 지원이 승인되어 주 역할이 겹치게 됨 → 승인 직전 검사로 거절
        ("투표", "2026306", "2026302", VOTE_YES, "대기"),
        ("투표", "2026306", "2026308", VOTE_YES, "대기"),
        ("투표", "2026306", "2026305", VOTE_YES, "거절"),

        ("지원", "2026311", 3, "승인"),

        ("지원", "2026315", 3, "대기"),
        ("투표", "2026315", "2026311", VOTE_YES, "승인"),

        # 11단계: 남는 자리 1개로 필수 포함 역할 2개를 채울 수 없음
        ("지원", "2026314", 3, "막힘"),

        ("지원", "2026310", 4, "승인"),

        ("지원", "2026313", 1, "대기"),
        ("투표", "2026313", "2026301", VOTE_YES, "대기"),

        ("마감",),
    ],
    "남는_학생": {
        "2026303", "2026306", "2026309", "2026310",
        "2026312", "2026313", "2026314", "2026316",
    },
}


def 시나리오_실행(spec):
    students = parse_roster((HERE / spec["csv"]).read_bytes())
    state = build_state(students, spec["teams"])

    for i, step in enumerate(spec["steps"], start=1):
        if step[0] == "마감":
            close_recruiting(state)
            continue

        if step[0] == "지원":
            _, no, team_no, expected = step
            got = apply_to_team(state, no, team_no)
        else:
            _, applicant, voter, vote, expected = step
            app = pending_application_of(state, applicant)
            assert app is not None, f"{i}번째: {applicant}의 대기 중인 지원이 없음"
            got = cast_vote(state, app.id, voter, vote)

        assert got.startswith(expected), (
            f"{i}번째 {step}: 기대 '{expected}', 실제 '{got}'"
        )

    return state


@pytest.mark.parametrize("spec", [쉬움, 중간, 어려움], ids=["쉬움", "중간", "어려움"])
def test_모든_단계의_결과가_기대와_같다(spec):
    시나리오_실행(spec)


@pytest.mark.parametrize("spec", [쉬움, 중간, 어려움], ids=["쉬움", "중간", "어려움"])
def test_마감_뒤_팀이_없는_학생이_공고와_같다(spec):
    state = 시나리오_실행(spec)
    if not state.closed:
        close_recruiting(state)
    assert {s.student_no for s in unassigned(state)} == spec["남는_학생"]


@pytest.mark.parametrize("spec", [쉬움, 중간, 어려움], ids=["쉬움", "중간", "어려움"])
def test_배정하면_모든_팀이_규칙을_지킨다(spec):
    state = 시나리오_실행(spec)
    if not state.closed:
        close_recruiting(state)

    teams = {no: members(state, no) for no in state.teams}
    left = unassigned(state)

    plan = solve(teams, left)
    assert plan is not None, "규칙을 지키는 배정을 찾지 못함"
    assert validate_assignment(teams, left, plan) == []

    for no, team_no in plan.items():
        teams[team_no].append(state.students[no])
    assert validate_teams(teams) == []
