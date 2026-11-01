"""AI 가 3차까지 실패했을 때 앱이 스스로 하는 배정 — 공고 3장 어려운 해결.

규칙을 모두 지키는 배정을 모든 경우를 따져 끝까지 찾는다. 팀이 없는 학생은
8명을 넘지 않고 팀은 3~4개이므로 가지치기 백트래킹으로 충분히 끝난다.
팀이 없는 학생만 넣고, 이미 팀에 있는 학생은 옮기지 않는다.
"""

from collections.abc import Mapping, Sequence

from domain import REQUIRED_ROLES, TEAM_MAX, TEAM_MIN, Student
from rules import filled_required, validate_teams


def solve(
    teams: Mapping[int, Sequence[Student]],
    unassigned: Sequence[Student],
) -> dict[str, int] | None:
    """규칙을 모두 지키는 배정을 찾는다. 없으면 None."""
    team_nos = sorted(teams)
    slots: dict[int, list[Student]] = {no: list(teams[no]) for no in team_nos}
    # 자리가 적은 팀부터 채우면 가지치기가 빨리 걸린다
    students = sorted(unassigned, key=lambda s: len(s.sub_roles))
    plan: dict[str, int] = {}

    def remaining_capacity() -> int:
        return sum(TEAM_MAX - len(slots[no]) for no in team_nos)

    def short_of_minimum() -> int:
        return sum(max(0, TEAM_MIN - len(slots[no])) for no in team_nos)

    def search(i: int) -> bool:
        if i == len(students):
            return not validate_teams(slots)

        left = len(students) - i
        # 남은 학생으로 2명을 못 채우는 팀이 생기면 더 볼 것 없다
        if short_of_minimum() > left:
            return False
        if remaining_capacity() < left:
            return False

        student = students[i]
        for team_no in team_nos:
            members = slots[team_no]
            if len(members) >= TEAM_MAX:
                continue
            if any(m.main_role == student.main_role for m in members):
                continue

            members.append(student)
            plan[student.student_no] = team_no
            if search(i + 1):
                return True
            members.pop()
            del plan[student.student_no]
        return False

    return dict(plan) if search(0) else None


def infeasible_reason(
    teams: Mapping[int, Sequence[Student]],
    unassigned: Sequence[Student],
) -> str:
    """규칙을 지키는 배정이 왜 없는지 한 줄로 설명한다 — 공고 2.5절 8항."""
    total = sum(len(ms) for ms in teams.values()) + len(unassigned)
    if total < TEAM_MIN * len(teams):
        return (
            f"학생이 {total}명뿐이라 팀 {len(teams)}개를 모두 2명 이상으로 만들 수 없음"
        )
    if total > TEAM_MAX * len(teams):
        return f"학생 {total}명을 팀 {len(teams)}개에 4명씩 넣어도 자리가 모자람"

    for team_no in sorted(teams):
        members = list(teams[team_no])
        room = TEAM_MAX - len(members)
        for role in REQUIRED_ROLES:
            if any(m.can_take(role) for m in members):
                continue
            if room == 0:
                return f"팀{team_no}이 꽉 찼는데 {role}를 맡을 학생이 없음"
            if not any(s.can_take(role) for s in unassigned):
                return f"팀{team_no}에 {role}를 맡을 학생이 없음"
        if room == 0 and filled_required(members) < len(REQUIRED_ROLES):
            return (
                f"팀{team_no}이 꽉 찼는데 "
                f"{REQUIRED_ROLES[0]}와 {REQUIRED_ROLES[1]}를 "
                "서로 다른 사람이 맡을 수 없음"
            )

    needed = {role: 0 for role in REQUIRED_ROLES}
    for team_no in sorted(teams):
        for role in REQUIRED_ROLES:
            if not any(m.can_take(role) for m in teams[team_no]):
                needed[role] += 1
    for role, count in needed.items():
        available = sum(1 for s in unassigned if s.can_take(role))
        if available < count:
            return (
                f"{role}를 맡을 학생이 {available}명인데 "
                f"{count}개 팀에 필요함"
            )

    return "주 역할 중복과 인원 제한 때문에 규칙을 모두 지키는 배정을 만들 수 없음"
