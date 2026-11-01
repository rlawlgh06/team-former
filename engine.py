"""지원·투표·마감 상태 기계 — 공고 2.4절, 2.5절 1~2항.

메모리 State 위에서만 돌아간다. DB 를 모르므로 부록 시나리오를 그대로
테스트로 돌릴 수 있고, db.py 는 같은 판정을 트랜잭션 안에서 다시 쓴다.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from domain import (
    APPROVED,
    BLOCKED,
    PENDING,
    REJECTED,
    VOTE_NO,
    VOTE_YES,
    Student,
)
from rules import apply_block_reason

CLOSED = "모집이 마감됨"
ALREADY_IN_TEAM = "이미 팀이 있음"
HAS_PENDING = "결과를 기다리는 지원이 있음"
NO_SUCH_TEAM = "없는 팀"
NO_SUCH_APPLICATION = "없는 지원"
NOT_A_MEMBER = "그 팀의 팀원이 아님"
ALREADY_VOTED = "이미 투표했음"
MEMBER_REJECTED = "팀원이 거부함"


@dataclass
class Application:
    id: int
    team_id: int
    student_no: str
    status: str = PENDING
    reason: str = ""


@dataclass
class State:
    students: dict[str, Student] = field(default_factory=dict)
    teams: dict[int, list[str]] = field(default_factory=dict)
    applications: dict[int, Application] = field(default_factory=dict)
    votes: dict[tuple[int, str], str] = field(default_factory=dict)
    closed: bool = False
    next_app_id: int = 1


# --- 조회 -------------------------------------------------------------------


def members(state: State, team_id: int) -> list[Student]:
    return [state.students[no] for no in state.teams.get(team_id, [])]


def team_of(state: State, student_no: str) -> int | None:
    for team_id, nos in state.teams.items():
        if student_no in nos:
            return team_id
    return None


def pending_application_of(state: State, student_no: str) -> Application | None:
    for app in state.applications.values():
        if app.student_no == student_no and app.status == PENDING:
            return app
    return None


def pending_applications_for(state: State, team_id: int) -> list[Application]:
    return [
        a
        for a in state.applications.values()
        if a.team_id == team_id and a.status == PENDING
    ]


def unassigned(state: State) -> list[Student]:
    """어느 팀에도 들어가지 못한 학생."""
    taken = {no for nos in state.teams.values() for no in nos}
    return [s for no, s in state.students.items() if no not in taken]


# --- 동작 -------------------------------------------------------------------


def apply_to_team(state: State, student_no: str, team_id: int) -> str:
    """팀에 지원한다. 승인·대기·막힘 중 하나로 시작하는 안내를 돌려준다."""
    if state.closed:
        return f"{BLOCKED}: {CLOSED}"
    if student_no not in state.students:
        return f"{BLOCKED}: 없는 학생"
    if team_id not in state.teams:
        return f"{BLOCKED}: {NO_SUCH_TEAM}"
    if team_of(state, student_no) is not None:
        return f"{BLOCKED}: {ALREADY_IN_TEAM}"
    if pending_application_of(state, student_no) is not None:
        return f"{BLOCKED}: {HAS_PENDING}"

    applicant = state.students[student_no]
    current = members(state, team_id)
    reason = apply_block_reason(current, applicant)
    if reason is not None:
        return f"{BLOCKED}: {reason}"

    app = Application(state.next_app_id, team_id, student_no)
    state.applications[app.id] = app
    state.next_app_id += 1

    if not current:
        # 투표할 팀원이 없으므로 바로 승인
        _join(state, app)
        return f"{APPROVED}: 팀{team_id}에 들어감"

    return f"{PENDING}: 팀{team_id} 팀원의 투표를 기다림"


def cast_vote(state: State, app_id: int, voter_no: str, vote: str) -> str:
    """지원에 찬성하거나 거부한다. 그 지원의 지금 상태를 돌려준다."""
    app = state.applications.get(app_id)
    if app is None:
        return f"{BLOCKED}: {NO_SUCH_APPLICATION}"
    if state.closed:
        return f"{BLOCKED}: {CLOSED}"
    if (app_id, voter_no) in state.votes:
        return f"{BLOCKED}: {ALREADY_VOTED}"
    if app.status != PENDING:
        return f"{app.status}: 이미 끝난 지원"
    if voter_no not in state.teams.get(app.team_id, []):
        return f"{BLOCKED}: {NOT_A_MEMBER}"

    state.votes[(app_id, voter_no)] = vote

    if vote == VOTE_NO:
        # 다른 팀원의 투표를 기다리지 않고 바로 거절
        app.status = REJECTED
        app.reason = MEMBER_REJECTED
        return f"{REJECTED}: {MEMBER_REJECTED}"

    # 투표할 사람은 투표하는 때의 팀원이다. 앞의 지원이 먼저 승인되어
    # 팀원이 늘었으면 그 사람의 투표도 기다린다.
    current_nos = state.teams[app.team_id]
    if not all(state.votes.get((app_id, no)) == VOTE_YES for no in current_nos):
        return f"{PENDING}: 아직 투표하지 않은 팀원이 있음"

    # 승인 직전 재검사 — 앞의 지원이 승인되어 팀이 바뀌었을 수 있다
    reason = apply_block_reason(members(state, app.team_id), state.students[app.student_no])
    if reason is not None:
        app.status = REJECTED
        app.reason = reason
        return f"{REJECTED}: {reason}"

    _join(state, app)
    return f"{APPROVED}: 팀{app.team_id}에 들어감"


def close_recruiting(state: State) -> None:
    """모집을 마감한다. 대기 지원은 거절되고 1명뿐인 팀은 해산한다."""
    state.closed = True
    for app in state.applications.values():
        if app.status == PENDING:
            app.status = REJECTED
            app.reason = CLOSED
    for team_id, nos in state.teams.items():
        if len(nos) == 1:
            state.teams[team_id] = []


def _join(state: State, app: Application) -> None:
    app.status = APPROVED
    app.reason = ""
    state.teams[app.team_id].append(app.student_no)


# --- 편의 -------------------------------------------------------------------


def build_state(students: Sequence[Student], team_count: int) -> State:
    return State(
        students={s.student_no: s for s in students},
        teams={n: [] for n in range(1, team_count + 1)},
    )
