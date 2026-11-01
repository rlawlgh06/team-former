"""팀 편성 웹 앱 — 화면.

요소의 key 는 keys.py 에서만 가져온다. 자동 채점 프로그램이 그 key 로
요소를 찾으므로 공고 2.7절 표와 글자 하나까지 같아야 한다.
"""

import os
import threading
import time
from datetime import datetime, timedelta, timezone

import streamlit as st

import assign_ai
import auth
import db
import engine
import keys
from assign_solver import infeasible_reason, solve
from domain import APPROVED, BLOCKED, VOTE_NO, VOTE_YES
from roster import parse_roster
from rules import validate_assignment

KST = timezone(timedelta(hours=9))
# AI 배정 전체 상한. 넘기면 앱이 스스로 배정한다 (공고 6.3절 18번)
TOTAL_BUDGET = 400.0


def models() -> list[str]:
    raw = db._secret("OPENROUTER_MODELS")
    if raw:
        picked = [m.strip() for m in raw.split(",") if m.strip()]
        if picked:
            return picked
    return list(assign_ai.DEFAULT_MODELS)


def now_kst() -> str:
    """배포 서버는 UTC 로 돌아가므로 한국 시각으로 바꿔 보여 준다."""
    return datetime.now(KST).strftime("%H:%M:%S")


@st.cache_resource(show_spinner=False)
def boot() -> bool:
    db.ensure_schema()
    admin_password = db._secret("ADMIN_PASSWORD")
    if not admin_password:
        raise RuntimeError("ADMIN_PASSWORD 가 없음 (.env 또는 Streamlit Secrets 를 확인)")
    db.ensure_admin(admin_password, auth.hash_password)
    return True


def say(message: str) -> None:
    st.session_state["result"] = message


def draw_result() -> None:
    with st.container(key=keys.RESULT, border=True):
        st.write(st.session_state.get("result", ""))


# --- 로그인 -----------------------------------------------------------------


def login_view() -> None:
    with st.form("login_form"):
        student_no = st.text_input("학번", key=keys.LOGIN_STUDENT_NO)
        password = st.text_input("비밀번호", type="password", key=keys.LOGIN_PASSWORD)
        submitted = st.form_submit_button("로그인", key=keys.LOGIN_SUBMIT)

    if submitted:
        account = auth.login(student_no, password)
        if account is None:
            say(f"{BLOCKED}: 학번이나 비밀번호가 맞지 않음")
        else:
            st.session_state["account"] = account
            say(f"{APPROVED}: {account.name}으로 로그인함")
            st.rerun()

    draw_result()


# --- 학생 화면 ---------------------------------------------------------------


@st.fragment(run_every=3)
def student_view(account: auth.Account) -> None:
    """바뀐 부분만 3초마다 다시 그린다 (공고 3장 어려운 해결)."""
    state = db.load_state()
    me = account.student_no
    my_team = engine.team_of(state, me)
    pending_mine = engine.pending_application_of(state, me)

    draw_result()

    if state.closed:
        st.info("모집이 마감되었습니다.")
    elif my_team is None:
        st.write("아직 팀이 없음")

    for team_no in sorted(state.teams):
        members = engine.members(state, team_no)
        with st.container(key=keys.team_key(team_no), border=True):
            label = f"팀{team_no} ({len(members)}/4)"
            if my_team == team_no:
                label += " — 내 팀"
            st.subheader(label)

            if members:
                for m in members:
                    st.write(f"{m.name} · {m.roles_text}")
            else:
                st.write("(비어 있음)")

            can_apply = (
                not state.closed
                and my_team is None
                and pending_mine is None
                and len(members) < 4
            )
            if can_apply and st.button(f"팀{team_no}에 지원", key=keys.apply_key(team_no)):
                say(db.do_apply(me, team_no))
                st.rerun(scope="fragment")

            if my_team == team_no:
                _draw_votes(state, team_no, me)


def _draw_votes(state: engine.State, team_no: int, me: str) -> None:
    waiting = engine.pending_applications_for(state, team_no)
    if not waiting:
        return

    st.divider()
    st.caption("들어온 지원")
    for app in waiting:
        applicant = state.students[app.student_no]
        st.write(f"{applicant.name} · {applicant.roles_text}")

        my_vote = state.votes.get((app.id, me))
        if my_vote is not None:
            st.write(f"내 투표: {my_vote}")
            continue

        yes, no = st.columns(2)
        if yes.button("찬성", key=keys.vote_yes_key(app.student_no)):
            say(db.do_vote(app.student_no, me, VOTE_YES))
            st.rerun(scope="fragment")
        if no.button("거부", key=keys.vote_no_key(app.student_no)):
            say(db.do_vote(app.student_no, me, VOTE_NO))
            st.rerun(scope="fragment")


# --- 관리자 화면 -------------------------------------------------------------


def admin_view() -> None:
    draw_result()
    st.subheader("명단 올리기")
    uploaded = st.file_uploader("명단 CSV", type="csv", key=keys.ADMIN_ROSTER_FILE)
    team_count = st.number_input("팀 수", min_value=1, max_value=20, value=3, step=1,
                                 key=keys.ADMIN_TEAM_COUNT)

    if st.button("명단으로 처음 상태 만들기", key=keys.ADMIN_START):
        if uploaded is None:
            say(f"{BLOCKED}: 명단 CSV 를 올려 주세요")
        else:
            try:
                students = parse_roster(uploaded.getvalue())
                db.reset_with_roster(students, int(team_count), auth.hash_password)
                st.session_state.pop("plan", None)
                say(f"{APPROVED}: 학생 {len(students)}명과 팀 {int(team_count)}개를 만듦")
            except ValueError as exc:
                say(f"{BLOCKED}: 명단을 읽을 수 없음 — {exc}")

    st.divider()
    if st.button("모집 마감", key=keys.ADMIN_CLOSE):
        say(db.do_close())

    _unassigned_box()

    st.divider()
    st.subheader("배정")
    if st.button("AI 배정", key=keys.ADMIN_ASSIGN):
        _run_assignment()
    else:
        _draw_assign_status()

    plan = st.session_state.get("plan")
    if plan:
        state = db.load_state()
        st.write("아래와 같이 배정합니다.")
        for no, team_no in sorted(plan.items(), key=lambda kv: (kv[1], kv[0])):
            s = state.students.get(no)
            if s:
                st.write(f"팀{team_no} ← {s.name} · {s.roles_text}")
        if st.button("배정안 확정", key=keys.ADMIN_CONFIRM):
            say(db.do_confirm(plan))
            st.session_state.pop("plan", None)
            st.rerun()


@st.fragment(run_every=3)
def _unassigned_box() -> None:
    state = db.load_state()
    with st.container(key=keys.UNASSIGNED, border=True):
        st.caption("팀이 없는 학생")
        left = engine.unassigned(state)
        if left:
            for s in left:
                st.write(f"{s.name} · {s.roles_text}")
        else:
            st.write("없음")


def _draw_assign_status() -> None:
    with st.container(key=keys.ASSIGN_STATUS, border=True):
        st.write(st.session_state.get("assign_status", ""))


def _set_status(message: str) -> None:
    st.session_state["assign_status"] = message


def _run_assignment() -> None:
    state = db.load_state()
    if not state.closed:
        _set_status("먼저 모집을 마감해 주세요")
        say(f"{BLOCKED}: 아직 마감하지 않음")
        _draw_assign_status()
        return

    teams = {no: engine.members(state, no) for no in state.teams}
    left = engine.unassigned(state)
    if not left:
        _set_status("팀이 없는 학생이 없습니다")
        say(f"{APPROVED}: 배정할 학생이 없음")
        _draw_assign_status()
        return

    # 규칙을 지키는 배정이 아예 없으면 AI 를 부르지 않는다 (공고 2.5절 8항).
    # 무료 모델의 하루 호출 한도를 아끼는 효과도 있다.
    fallback = solve(teams, left)
    if fallback is None:
        reason = infeasible_reason(teams, left)
        _set_status(f"규칙을 지키는 배정이 없음 — {reason}")
        say(f"{BLOCKED}: 규칙을 지키는 배정이 없음")
        _draw_assign_status()
        return

    api_key = db._secret("OPENROUTER_API_KEY")
    chosen = models()
    progress = {"tier": 0, "model": "", "since": time.monotonic()}
    outcome: dict = {}

    def on_progress(tier: int, model: str) -> None:
        progress.update(tier=tier, model=model, since=time.monotonic())

    def worker() -> None:
        try:
            plan, attempts = assign_ai.run_assignment(
                chosen,
                teams,
                left,
                call=lambda m, p, *, timeout: assign_ai.openrouter_call(
                    m, p, api_key=api_key, timeout=timeout
                ),
                on_progress=on_progress,
            )
            outcome["plan"] = plan
            outcome["attempts"] = attempts
        except Exception as exc:
            outcome["plan"] = None
            outcome["attempts"] = []
            outcome["error"] = f"{type(exc).__name__}: {exc}"[:200]

    box = st.container(key=keys.ASSIGN_STATUS, border=True)
    line = box.empty()

    if not api_key:
        line.write("오픈라우터 키가 없어 앱이 스스로 배정합니다")
        outcome = {"plan": None, "attempts": []}
    else:
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        started = time.monotonic()
        while thread.is_alive():
            if time.monotonic() - started > TOTAL_BUDGET:
                line.write("AI 배정이 너무 오래 걸려 앱이 스스로 배정합니다")
                outcome.setdefault("plan", None)
                outcome.setdefault("attempts", [])
                break
            tier, model = progress["tier"], progress["model"]
            if tier:
                waited = time.monotonic() - progress["since"]
                line.write(f"{tier}차 모델 응답 대기 중 ({waited:.0f}초) — {model}")
            else:
                line.write("AI 배정을 시작합니다")
            time.sleep(0.5)
        thread.join(timeout=1)

    attempts = outcome.get("attempts") or []
    if attempts:
        try:
            db.log_ai_attempts(attempts)
        except Exception:
            pass

    plan = outcome.get("plan")
    기록 = " / ".join(f"{a.tier}차 {a.model}: {a.status}" for a in attempts)

    if plan is None:
        plan = fallback
        꼬리 = "3차 모델까지 실패해 앱이 스스로 배정함"
    else:
        꼬리 = "AI 배정안이 검사를 통과함"

    assert validate_assignment(teams, left, plan) == []
    st.session_state["plan"] = plan
    _set_status(f"[{now_kst()}] {기록} → {꼬리}. 아래 배정안을 확인하고 확정하세요")
    line.write(st.session_state["assign_status"])
    say(f"{APPROVED}: 배정안을 만듦")
    st.rerun()


# --- 입구 -------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="팀 편성", layout="wide")
    # 제목을 먼저 그린다. 화면이 비어 있으면 스크립트가 아예 돌지 않은 것이고,
    # 제목만 보이면 그다음(DB 연결)에서 멈춘 것이라 원인을 구별할 수 있다.
    st.title("팀 편성")
    try:
        with st.spinner("DB 에 연결하는 중"):
            boot()
    except Exception as exc:
        st.error(f"앱을 시작하지 못했습니다 — {type(exc).__name__}: {exc}")
        st.stop()

    account = st.session_state.get("account")
    if account is None:
        login_view()
        return

    with st.container(key=keys.WHOAMI):
        st.write(f"{account.name} ({account.student_no})")
    if st.sidebar.button("로그아웃"):
        st.session_state.clear()
        st.rerun()

    if account.is_admin:
        admin_view()
    else:
        student_view(account)


main()
