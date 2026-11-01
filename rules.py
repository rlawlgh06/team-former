"""팀 규칙 — 공고 2.3절, 2.4절, 2.5절 4항.

DB 와 화면을 모르는 순수 함수만 둔다. 규칙 판정은 모두 여기에만 있다.
"""

from collections.abc import Mapping, Sequence

from domain import REQUIRED_ROLES, TEAM_MAX, TEAM_MIN, Student

FULL = "팀이 꽉 찼음"
MAIN_ROLE_DUP = "같은 주 역할의 팀원이 있음"
NO_ROOM_FOR_REQUIRED = "필수 포함 역할을 맡을 학생의 자리가 모자람"


def filled_required(members: Sequence[Student]) -> int:
    """팀원이 필수 포함 역할 몇 개를 채울 수 있는지 (0~2).

    기획자와 웹 프로그래머는 서로 다른 사람이 맡아야 하므로, 역할마다 맡을 수
    있는 사람을 따로 세면 안 된다. 한 사람이 둘 다 할 수 있어도 하나로만 센다.
    필수 역할이 2개뿐이라 서로 다른 두 사람의 쌍이 있는지만 보면 충분하다.
    """
    first, second = REQUIRED_ROLES
    can_first = [m for m in members if m.can_take(first)]
    can_second = [m for m in members if m.can_take(second)]

    if not can_first and not can_second:
        return 0
    for a in can_first:
        for b in can_second:
            if a.student_no != b.student_no:
                return 2
    return 1


def missing_required(members: Sequence[Student]) -> int:
    """아직 채우지 못한 필수 포함 역할 수."""
    return len(REQUIRED_ROLES) - filled_required(members)


def main_role_conflict(members: Sequence[Student], applicant: Student) -> bool:
    return any(m.main_role == applicant.main_role for m in members)


def apply_block_reason(
    members: Sequence[Student], applicant: Student
) -> str | None:
    """지원을 막을 이유. 막지 않으면 None.

    승인 직전 재검사(공고 2.4절)도 검사 항목이 같으므로 이 함수를 그대로 쓴다.
    """
    if len(members) >= TEAM_MAX:
        return FULL
    if main_role_conflict(members, applicant):
        return MAIN_ROLE_DUP

    after = [*members, applicant]
    room_left = TEAM_MAX - len(after)
    if room_left < missing_required(after):
        return NO_ROOM_FOR_REQUIRED
    return None


def team_violations(team_no: int, members: Sequence[Student]) -> list[str]:
    """확정된 팀 하나가 공고 2.3절을 어긴 점."""
    out: list[str] = []
    if not (TEAM_MIN <= len(members) <= TEAM_MAX):
        out.append(f"팀{team_no}: 인원이 {len(members)}명 (2~4명이어야 함)")

    seen: set[str] = set()
    for m in members:
        if m.main_role in seen:
            out.append(f"팀{team_no}: 주 역할 '{m.main_role}'이 중복됨")
            break
        seen.add(m.main_role)

    if filled_required(members) < len(REQUIRED_ROLES):
        first, second = REQUIRED_ROLES
        if not any(m.can_take(first) for m in members):
            out.append(f"팀{team_no}에 {first}를 맡을 학생이 없음")
        elif not any(m.can_take(second) for m in members):
            out.append(f"팀{team_no}에 {second}를 맡을 학생이 없음")
        else:
            out.append(f"팀{team_no}: {first}와 {second}를 서로 다른 사람이 맡을 수 없음")
    return out


def validate_teams(teams: Mapping[int, Sequence[Student]]) -> list[str]:
    """확정하려는 팀 구성 전체를 검사한다. 빈 목록이면 통과."""
    out: list[str] = []
    for team_no in sorted(teams):
        out.extend(team_violations(team_no, teams[team_no]))
    return out


def validate_assignment(
    teams: Mapping[int, Sequence[Student]],
    unassigned: Sequence[Student],
    plan: Mapping[str, int],
) -> list[str]:
    """배정안을 공고 2.5절 4항의 다섯 가지로 검사한다. 빈 목록이면 통과."""
    out: list[str] = []
    left = {s.student_no: s for s in unassigned}

    # 1. 팀이 없는 학생이 빠짐없이 배정됨
    for no in left:
        if no not in plan:
            out.append(f"{left[no].name}이(가) 배정되지 않음")

    # 2. 한 학생은 한 팀에만 배정됨 (plan 에 팀이 없는 학생만 들어 있어야 함)
    for no, team_no in plan.items():
        if no not in left:
            out.append(f"학번 {no}은(는) 팀이 없는 학생이 아님 (기존 팀원을 옮길 수 없음)")
        if team_no not in teams:
            out.append(f"없는 팀 {team_no}에 배정함")

    if out:
        return out

    # 3~5. 합친 팀 구성이 인원·주 역할 중복·필수 포함 역할을 지키는지
    merged = {no: list(ms) for no, ms in teams.items()}
    for no, team_no in plan.items():
        merged[team_no].append(left[no])
    out.extend(validate_teams(merged))
    return out
