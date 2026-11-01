"""지원·투표·마감 — 공고 2.4절, 2.5절."""

from domain import VOTE_NO, VOTE_YES, Student
from engine import (
    apply_to_team,
    build_state,
    cast_vote,
    close_recruiting,
    pending_application_of,
    unassigned,
)


def S(no, main, *subs):
    return Student(no, f"학생{no}", main, tuple(subs))


ROSTER = [
    S("1", "기획자"),
    S("2", "웹 프로그래머"),
    S("3", "테스터"),
    S("4", "발표자"),
    S("5", "보고서 작성자"),
    S("6", "프론트엔드 디자이너"),
    S("7", "기획자", "웹 프로그래머"),
]


def 상태(team_count=3):
    return build_state(ROSTER, team_count)


def app_id(state, student_no):
    return pending_application_of(state, student_no).id


# --- 지원 -------------------------------------------------------------------


def test_빈_팀_지원은_바로_승인():
    s = 상태()
    assert apply_to_team(s, "1", 1).startswith("승인")
    assert s.teams[1] == ["1"]


def test_팀원이_있으면_대기():
    s = 상태()
    apply_to_team(s, "1", 1)
    assert apply_to_team(s, "2", 1).startswith("대기")
    assert s.teams[1] == ["1"]


def test_결과를_기다리는_중에는_다른_팀에_지원할_수_없다():
    s = 상태()
    apply_to_team(s, "1", 1)
    apply_to_team(s, "2", 1)
    r = apply_to_team(s, "2", 2)
    assert r.startswith("막힘") and "결과를 기다리는" in r


def test_이미_팀이_있으면_지원할_수_없다():
    s = 상태()
    apply_to_team(s, "1", 1)
    r = apply_to_team(s, "1", 2)
    assert r.startswith("막힘") and "이미 팀이 있음" in r


def test_주_역할이_중복되면_막힌다():
    s = 상태()
    apply_to_team(s, "1", 1)
    r = apply_to_team(s, "7", 1)  # 둘 다 주 역할이 기획자
    assert r.startswith("막힘") and "주 역할" in r


# --- 투표 -------------------------------------------------------------------


def test_모든_팀원이_찬성하면_승인():
    s = 상태()
    apply_to_team(s, "1", 1)
    apply_to_team(s, "2", 1)
    assert cast_vote(s, app_id(s, "2"), "1", VOTE_YES).startswith("승인")
    assert s.teams[1] == ["1", "2"]


def test_한_명이라도_거부하면_즉시_거절():
    s = 상태()
    apply_to_team(s, "1", 1)
    apply_to_team(s, "2", 1)
    cast_vote(s, app_id(s, "2"), "1", VOTE_YES)  # 승인되어 팀원 2명
    apply_to_team(s, "3", 1)
    aid = app_id(s, "3")
    assert cast_vote(s, aid, "1", VOTE_YES).startswith("대기")
    assert cast_vote(s, aid, "2", VOTE_NO).startswith("거절")


def test_투표는_바꿀_수_없다():
    s = 상태()
    apply_to_team(s, "1", 1)
    apply_to_team(s, "2", 1)
    aid = app_id(s, "2")
    cast_vote(s, aid, "1", VOTE_YES)
    assert cast_vote(s, aid, "1", VOTE_NO).startswith("막힘")


def test_팀원이_아니면_투표할_수_없다():
    s = 상태()
    apply_to_team(s, "1", 1)
    apply_to_team(s, "2", 1)
    assert cast_vote(s, app_id(s, "2"), "3", VOTE_YES).startswith("막힘")


def test_나중에_승인된_팀원도_내_지원에_투표한다():
    """분모는 저장된 값이 아니라 판정 시점의 팀원 수다."""
    s = 상태()
    apply_to_team(s, "1", 1)       # 팀1 = [1]
    apply_to_team(s, "2", 1)       # 2 대기
    apply_to_team(s, "3", 1)       # 3 대기
    cast_vote(s, app_id(s, "2"), "1", VOTE_YES)   # 2 승인 → 팀1 = [1, 2]
    aid3 = app_id(s, "3")
    assert cast_vote(s, aid3, "1", VOTE_YES).startswith("대기")  # 2의 투표가 남음
    assert cast_vote(s, aid3, "2", VOTE_YES).startswith("승인")


def test_승인_직전_재검사로_거절():
    """앞의 지원이 먼저 승인되어 정원이 차면 뒤의 지원은 거절된다."""
    s = 상태()
    apply_to_team(s, "1", 1)
    for no in ("2", "3"):
        apply_to_team(s, no, 1)
        aid = app_id(s, no)
        for voter in list(s.teams[1]):
            cast_vote(s, aid, voter, VOTE_YES)
    assert s.teams[1] == ["1", "2", "3"]

    apply_to_team(s, "4", 1)   # 대기
    apply_to_team(s, "5", 1)   # 대기
    aid4, aid5 = app_id(s, "4"), app_id(s, "5")
    for voter in ("1", "2", "3"):
        cast_vote(s, aid4, voter, VOTE_YES)
    assert s.teams[1] == ["1", "2", "3", "4"]

    results = [cast_vote(s, aid5, v, VOTE_YES) for v in ("1", "2", "3", "4")]
    assert results[-1].startswith("거절")
    assert "꽉" in results[-1]


# --- 마감 -------------------------------------------------------------------


def test_마감하면_대기_지원은_거절되고_1명_팀은_해산():
    s = 상태()
    apply_to_team(s, "1", 1)   # 팀1에 1명
    apply_to_team(s, "2", 1)   # 대기
    close_recruiting(s)
    assert s.teams[1] == []
    assert {st.student_no for st in unassigned(s)} == {"1", "2", "3", "4", "5", "6", "7"}


def test_2명_이상인_팀은_마감해도_남는다():
    s = 상태()
    apply_to_team(s, "1", 1)
    apply_to_team(s, "2", 1)
    cast_vote(s, app_id(s, "2"), "1", VOTE_YES)
    close_recruiting(s)
    assert s.teams[1] == ["1", "2"]


def test_마감_뒤_지원은_막힌다():
    s = 상태()
    close_recruiting(s)
    assert apply_to_team(s, "1", 1).startswith("막힘")


def test_마감_뒤_투표도_막힌다():
    s = 상태()
    apply_to_team(s, "1", 1)
    apply_to_team(s, "2", 1)
    aid = app_id(s, "2")
    close_recruiting(s)
    assert cast_vote(s, aid, "1", VOTE_YES).startswith("막힘")
