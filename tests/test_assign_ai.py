"""오픈라우터 3단 폴백 — 공고 2.5절 5항, 4.3절. 네트워크 없이 call 을 주입한다."""

import time

from assign_ai import EMPTY, INVALID, OK, TIMEOUT, UNPARSABLE, parse_plan, run_assignment
from domain import Student


def S(no, main, *subs):
    return Student(no, f"학생{no}", main, tuple(subs))


TEAMS = {1: [S("1", "기획자")], 2: [S("2", "웹 프로그래머")]}
LEFT = [S("3", "웹 프로그래머"), S("4", "기획자")]
GOOD = '{"3": 1, "4": 2}'
MODELS = ["모델1:free", "모델2:free", "모델3:free"]


def 고정응답(*answers):
    """차례로 미리 정한 답을 내놓는 가짜 call. 예외도 낼 수 있다."""
    남은 = list(answers)
    불린_모델 = []

    def call(model, prompt, *, timeout):
        불린_모델.append(model)
        answer = 남은.pop(0)
        if isinstance(answer, Exception):
            raise answer
        if callable(answer):
            return answer()
        return answer

    call.불린_모델 = 불린_모델
    return call


# --- parse_plan -------------------------------------------------------------


def test_맨몸_JSON을_읽는다():
    assert parse_plan('{"2026101": 2}') == {"2026101": 2}


def test_JSON_앞뒤에_설명이_붙어도_읽는다():
    text = '좋습니다! 아래가 배정안입니다.\n```json\n{"2026101": 2}\n```\n도움이 되었길.'
    assert parse_plan(text) == {"2026101": 2}


def test_assignments_목록_꼴도_읽는다():
    text = '{"assignments": [{"student_no": "2026101", "team": 3}]}'
    assert parse_plan(text) == {"2026101": 3}


def test_팀_번호가_문자열이어도_정수로_바꾼다():
    assert parse_plan('{"2026101": "2"}') == {"2026101": 2}


def test_빈_응답은_None():
    assert parse_plan("") is None
    assert parse_plan("   ") is None


def test_JSON이_아니면_None():
    assert parse_plan("죄송합니다, 배정할 수 없습니다.") is None


# --- run_assignment ---------------------------------------------------------


def test_1차가_성공하면_2차를_부르지_않는다():
    call = 고정응답(GOOD)
    plan, attempts = run_assignment(MODELS, TEAMS, LEFT, call=call)
    assert plan == {"3": 1, "4": 2}
    assert call.불린_모델 == ["모델1:free"]
    assert [a.status for a in attempts] == [OK]


def test_빈_응답이면_다음_모델로():
    call = 고정응답("", GOOD)
    plan, attempts = run_assignment(MODELS, TEAMS, LEFT, call=call)
    assert plan is not None
    assert [a.status for a in attempts] == [EMPTY, OK]


def test_오류를_내면_다음_모델로():
    call = 고정응답(RuntimeError("HTTP 429: rate limited"), GOOD)
    plan, attempts = run_assignment(MODELS, TEAMS, LEFT, call=call)
    assert plan is not None
    assert attempts[0].status == "오류"
    assert "429" in attempts[0].detail


def test_읽을_수_없는_응답이면_다음_모델로():
    call = 고정응답("배정이 어렵습니다", GOOD)
    plan, attempts = run_assignment(MODELS, TEAMS, LEFT, call=call)
    assert plan is not None
    assert [a.status for a in attempts] == [UNPARSABLE, OK]


def test_검사를_통과하지_못한_배정안은_실패로_보고_다음_모델로():
    # 학생4 를 빠뜨린 배정안
    call = 고정응답('{"3": 1}', GOOD)
    plan, attempts = run_assignment(MODELS, TEAMS, LEFT, call=call)
    assert plan == {"3": 1, "4": 2}
    assert attempts[0].status == INVALID


def test_규칙을_어긴_배정안도_걸러_낸다():
    # 팀1 에 기획자가 둘이 되는 배정안
    call = 고정응답('{"3": 2, "4": 1}', GOOD)
    plan, attempts = run_assignment(MODELS, TEAMS, LEFT, call=call)
    assert attempts[0].status == INVALID
    assert plan == {"3": 1, "4": 2}


def test_시간_제한을_넘기면_끊고_다음_모델로():
    call = 고정응답(lambda: (time.sleep(2), GOOD)[1], GOOD)
    plan, attempts = run_assignment(MODELS, TEAMS, LEFT, call=call, timeout=0.3)
    assert plan is not None
    assert attempts[0].status == TIMEOUT
    assert attempts[0].elapsed_ms < 1500   # 2초를 기다리지 않고 끊었다


def test_3차까지_실패하면_None_과_시도_3건():
    call = 고정응답("", "", "")
    plan, attempts = run_assignment(MODELS, TEAMS, LEFT, call=call)
    assert plan is None
    assert len(attempts) == 3
    assert call.불린_모델 == MODELS


def test_진행_안내는_몇_차_모델인지_알려_준다():
    본_것 = []
    call = 고정응답("", GOOD)
    run_assignment(MODELS, TEAMS, LEFT, call=call, on_progress=lambda t, m: 본_것.append((t, m)))
    assert 본_것 == [(1, "모델1:free"), (2, "모델2:free")]
