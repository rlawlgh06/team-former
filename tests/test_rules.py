"""팀 규칙 — 공고 2.3절, 2.4절, 3장(필수 포함 역할 자리)."""

import pytest

from domain import Student
from rules import (
    apply_block_reason,
    filled_required,
    main_role_conflict,
    validate_assignment,
    validate_teams,
)


def S(no, main, *subs):
    return Student(no, f"학생{no}", main, tuple(subs))


# --- filled_required: 최대 이분 매칭 ---------------------------------------


def test_아무도_필수역할을_못_맡으면_0():
    assert filled_required([S("1", "테스터"), S("2", "발표자")]) == 0


def test_한_사람이_두_필수역할을_겸하면_하나로_센다():
    # 공고 6쪽: 주 역할 기획자 + 보조 웹 프로그래머 혼자 있는 팀은 2개 중 1개만 채움
    assert filled_required([S("1", "기획자", "웹 프로그래머")]) == 1


def test_서로_다른_두_사람이_맡으면_둘_다_센다():
    assert filled_required([S("1", "기획자"), S("2", "웹 프로그래머")]) == 2


def test_보조역할로도_필수역할을_채운다():
    # 주 역할이 테스터이고 보조가 기획자인 학생이 그 팀의 기획자를 맡을 수 있음
    assert filled_required([S("1", "테스터", "기획자"), S("2", "웹 프로그래머")]) == 2


def test_겸직자와_전담자가_있으면_둘_다_채운다():
    # 겸직자가 기획자를 맡고 전담자가 웹 프로그래머를 맡으면 2
    assert filled_required([S("1", "기획자", "웹 프로그래머"), S("2", "웹 프로그래머")]) == 2


def test_빈_팀은_0():
    assert filled_required([]) == 0


# --- 주 역할 중복 -----------------------------------------------------------


def test_주_역할이_같으면_중복():
    assert main_role_conflict([S("1", "기획자")], S("2", "기획자")) is True


def test_보조_역할이_겹치는_것은_중복이_아니다():
    assert main_role_conflict([S("1", "테스터", "기획자")], S("2", "기획자")) is False


# --- apply_block_reason -----------------------------------------------------


def test_문제가_없으면_None():
    assert apply_block_reason([S("1", "기획자")], S("2", "웹 프로그래머")) is None


def test_정원이_차면_막는다():
    members = [S("1", "기획자"), S("2", "웹 프로그래머"), S("3", "테스터"), S("4", "발표자")]
    assert apply_block_reason(members, S("5", "보고서 작성자")) == "팀이 꽉 찼음"


def test_주_역할_중복이면_막는다():
    assert apply_block_reason([S("1", "기획자")], S("2", "기획자")) == "같은 주 역할의 팀원이 있음"


def test_남는_자리가_모자라면_막는다():
    # 공고 6쪽: 테스터와 발표자만 있는 2명 팀에 보고서 작성자가 지원하면
    # 남는 자리 1개로 필수 포함 역할 2개를 채울 수 없으므로 막음
    members = [S("1", "테스터"), S("2", "발표자")]
    assert apply_block_reason(members, S("3", "보고서 작성자")) == (
        "필수 포함 역할을 맡을 학생의 자리가 모자람"
    )


def test_필수역할을_채우는_지원은_막지_않는다():
    members = [S("1", "테스터"), S("2", "발표자")]
    assert apply_block_reason(members, S("3", "기획자", "웹 프로그래머")) is None


def test_겸직자_혼자인_팀에_셋째가_들어오면_막힌다():
    # 겸직자 + 테스터 + 지원자(발표자) → 남는자리 1, 못채운수 1 → 통과해야 함
    members = [S("1", "기획자", "웹 프로그래머"), S("2", "테스터")]
    assert apply_block_reason(members, S("3", "발표자")) is None
    # 한 명 더 차면 자리가 없어 막힌다
    members3 = [*members, S("3", "발표자")]
    assert apply_block_reason(members3, S("4", "보고서 작성자")) == (
        "필수 포함 역할을 맡을 학생의 자리가 모자람"
    )


# --- validate_teams ---------------------------------------------------------


def test_규칙을_지킨_팀은_위반이_없다():
    teams = {1: [S("1", "기획자"), S("2", "웹 프로그래머")]}
    assert validate_teams(teams) == []


def test_인원이_1명이면_위반():
    assert validate_teams({1: [S("1", "기획자", "웹 프로그래머")]}) != []


def test_빈_팀은_위반():
    assert validate_teams({1: [S("1", "기획자"), S("2", "웹 프로그래머")], 2: []}) != []


def test_필수역할이_없으면_위반():
    assert validate_teams({1: [S("1", "테스터"), S("2", "발표자")]}) != []


def test_주_역할_중복은_위반():
    assert validate_teams({1: [S("1", "기획자"), S("2", "기획자")]}) != []


# --- validate_assignment (공고 2.5절 4항 다섯 가지) ---------------------------


def test_올바른_배정안은_통과():
    teams = {1: [S("1", "기획자")], 2: [S("2", "웹 프로그래머")]}
    left = [S("3", "웹 프로그래머"), S("4", "기획자")]
    plan = {"3": 1, "4": 2}
    assert validate_assignment(teams, left, plan) == []


def test_배정되지_않은_학생이_있으면_위반():
    teams = {1: [S("1", "기획자")], 2: [S("2", "웹 프로그래머")]}
    left = [S("3", "웹 프로그래머"), S("4", "기획자")]
    assert validate_assignment(teams, left, {"3": 1}) != []


def test_없는_팀에_배정하면_위반():
    teams = {1: [S("1", "기획자")]}
    assert validate_assignment(teams, [S("3", "웹 프로그래머")], {"3": 9}) != []


def test_이미_팀이_있는_학생을_옮기면_위반():
    teams = {1: [S("1", "기획자")], 2: [S("2", "웹 프로그래머")]}
    left = [S("3", "웹 프로그래머")]
    assert validate_assignment(teams, left, {"3": 1, "1": 2}) != []
