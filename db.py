"""DB 계층 — 연결을 한 번만 만들고, 판정은 engine 에 맡긴다.

동작마다 트랜잭션 안에서 팀 행을 잠그고 → 상태를 읽고 → engine 이 판정하고
→ 바뀐 것만 기록한다. 규칙은 engine 과 rules 에만 있고 여기에는 없다.
"""

import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
import streamlit as st
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool

import engine
from domain import BLOCKED, Student
from engine import State

load_dotenv()   # 로컬에서 돌릴 때 .env 를 읽는다. 배포에서는 Streamlit Secrets 를 쓴다

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
STUDENT_PASSWORD = "1234"
ADMIN_NO = "admin"
CLOSED_KEY = "closed"


def _secret(name: str) -> str | None:
    """Streamlit Secrets → 환경변수 순으로 찾는다. 값은 절대 출력하지 않는다."""
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.environ.get(name)


@st.cache_resource(show_spinner=False)
def get_pool() -> ConnectionPool:
    """연결 풀을 한 번만 만든다. 질의마다 연결을 새로 만들면 화면이 느려진다."""
    url = _secret("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL 이 없음 (.env 또는 Streamlit Secrets 를 확인)")
    try:
        pool = ConnectionPool(
            url,
            min_size=1,
            max_size=8,
            timeout=15,
            open=False,
            # Supabase 의 transaction pooler 는 prepared statement 를 지원하지 않는다.
            # psycopg3 은 같은 질의를 다섯 번 쓰면 자동으로 prepare 하므로 꺼 둔다.
            kwargs={"prepare_threshold": None, "connect_timeout": 10},
        )
        pool.open(wait=True, timeout=20)
        return pool
    except Exception as exc:
        # 접속 주소에는 비밀번호가 들어 있으므로 메시지에 넣지 않는다
        raise RuntimeError(f"DB 에 연결하지 못함: {type(exc).__name__}") from None


@contextmanager
def tx():
    """트랜잭션 하나. 빠져나올 때 commit 하고, 예외가 나면 되돌린다."""
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            yield cur


# --- 적재 -------------------------------------------------------------------


@dataclass
class Maps:
    sid_of: dict[str, int] = field(default_factory=dict)      # 학번 -> tf_students.id
    no_of: dict[int, str] = field(default_factory=dict)       # id -> 학번
    tid_of: dict[int, int] = field(default_factory=dict)      # 팀 번호 -> tf_teams.id
    tno_of: dict[int, int] = field(default_factory=dict)      # id -> 팀 번호
    slots: dict[int, dict[str, int]] = field(default_factory=dict)  # 팀 번호 -> {학번: 자리}


# 상태 전체를 한 번의 왕복으로 읽는다. 표마다 따로 물으면 왕복이 일곱 번이 되어
# 화면 한 번 그리는 데 그만큼 늦어진다.
_READ_SQL = """
SELECT
  coalesce((SELECT json_agg(json_build_array(id, student_no, name, main_role))
            FROM tf_students WHERE NOT is_admin), '[]') AS students,
  coalesce((SELECT json_agg(json_build_array(student_id, role))
            FROM tf_student_sub_roles), '[]') AS subs,
  coalesce((SELECT json_agg(json_build_array(id, team_no) ORDER BY team_no)
            FROM tf_teams), '[]') AS teams,
  coalesce((SELECT json_agg(json_build_array(team_id, slot_no, student_id)
                            ORDER BY team_id, slot_no)
            FROM tf_members), '[]') AS members,
  coalesce((SELECT json_agg(json_build_array(id, team_id, student_id, status, reason)
                            ORDER BY id)
            FROM tf_applications), '[]') AS applications,
  coalesce((SELECT json_agg(json_build_array(application_id, voter_id, vote))
            FROM tf_votes), '[]') AS votes,
  (SELECT value FROM tf_settings WHERE key = %s) AS closed
"""


def _read(cur) -> tuple[State, Maps]:
    maps = Maps()
    state = State()

    cur.execute(_READ_SQL, (CLOSED_KEY,))
    students, subs_rows, teams, member_rows, apps, votes, closed = cur.fetchone()

    subs: dict[int, list[str]] = {}
    for sid, role in subs_rows:
        subs.setdefault(sid, []).append(role)

    for sid, no, name, main_role in students:
        maps.sid_of[no] = sid
        maps.no_of[sid] = no
        state.students[no] = Student(no, name, main_role, tuple(sorted(subs.get(sid, ()))))

    for tid, tno in teams:
        maps.tid_of[tno] = tid
        maps.tno_of[tid] = tno
        state.teams[tno] = []
        maps.slots[tno] = {}

    for tid, slot, sid in member_rows:
        no = maps.no_of.get(sid)
        if no is None:
            continue
        tno = maps.tno_of[tid]
        state.teams[tno].append(no)
        maps.slots[tno][no] = slot

    for aid, tid, sid, status, reason in apps:
        no = maps.no_of.get(sid)
        if no is None:
            continue
        state.applications[aid] = engine.Application(
            aid, maps.tno_of[tid], no, status, reason
        )

    for aid, vid, vote in votes:
        voter = maps.no_of.get(vid)
        if voter is not None:
            state.votes[(aid, voter)] = vote

    state.closed = closed == "1"
    state.next_app_id = max(state.applications, default=0) + 1
    return state, maps


def _snapshot(state: State) -> dict:
    return {
        "apps": {a.id: (a.status, a.reason) for a in state.applications.values()},
        "votes": set(state.votes),
        "teams": {tno: list(nos) for tno, nos in state.teams.items()},
        "closed": state.closed,
    }


def _write(cur, state: State, maps: Maps, before: dict) -> None:
    for app in state.applications.values():
        now = (app.status, app.reason)
        if app.id not in before["apps"]:
            cur.execute(
                "INSERT INTO tf_applications (team_id, student_id, status, reason) "
                "VALUES (%s, %s, %s, %s)",
                (maps.tid_of[app.team_id], maps.sid_of[app.student_no], *now),
            )
        elif before["apps"][app.id] != now:
            cur.execute(
                "UPDATE tf_applications SET status = %s, reason = %s WHERE id = %s",
                (*now, app.id),
            )

    for (aid, voter), vote in state.votes.items():
        if (aid, voter) not in before["votes"]:
            cur.execute(
                "INSERT INTO tf_votes (application_id, voter_id, vote) VALUES (%s, %s, %s)",
                (aid, maps.sid_of[voter], vote),
            )

    for tno, nos in state.teams.items():
        was = before["teams"][tno]
        if nos == was:
            continue
        for no in was:
            if no not in nos:
                cur.execute("DELETE FROM tf_members WHERE student_id = %s", (maps.sid_of[no],))
                maps.slots[tno].pop(no, None)
        for no in nos:
            if no in was:
                continue
            used = set(maps.slots[tno].values())
            slot = next(n for n in range(1, 5) if n not in used)
            cur.execute(
                "INSERT INTO tf_members (team_id, slot_no, student_id) VALUES (%s, %s, %s)",
                (maps.tid_of[tno], slot, maps.sid_of[no]),
            )
            maps.slots[tno][no] = slot

    if state.closed != before["closed"]:
        cur.execute(
            "INSERT INTO tf_settings (key, value) VALUES (%s, %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (CLOSED_KEY, "1" if state.closed else "0"),
        )


def _lock_all_teams(cur) -> None:
    cur.execute("SELECT id FROM tf_teams ORDER BY id FOR UPDATE")


# --- 공개 API ---------------------------------------------------------------


def _statements(sql: str) -> list[str]:
    """psycopg3 은 한 번에 한 문장만 보내므로 세미콜론으로 나눈다."""
    out = []
    for chunk in sql.split(";"):
        body = "\n".join(
            line for line in chunk.splitlines() if not line.strip().startswith("--")
        )
        if body.strip():
            out.append(chunk.strip())
    return out


def ensure_schema() -> None:
    with tx() as cur:
        for statement in _statements(SCHEMA_PATH.read_text(encoding="utf-8")):
            cur.execute(statement)


def ensure_admin(password: str, hasher) -> None:
    """관리자 계정을 만들거나 비밀번호를 갱신한다. 명단을 다시 올려도 남는다."""
    with tx() as cur:
        cur.execute(
            "INSERT INTO tf_students (student_no, name, main_role, password_hash, is_admin) "
            "VALUES (%s, '관리자', '기획자', %s, TRUE) "
            "ON CONFLICT (student_no) DO UPDATE SET password_hash = EXCLUDED.password_hash",
            (ADMIN_NO, hasher(password)),
        )


def load_state() -> State:
    with tx() as cur:
        state, _ = _read(cur)
    return state


def is_closed() -> bool:
    return load_state().closed


def reset_with_roster(students, team_count: int, hasher) -> None:
    """명단으로 처음 상태를 만든다 — 공고 2.6절. 관리자 계정만 남긴다."""
    # 학생 비밀번호는 모두 같으므로 해시를 한 번만 만든다
    password_hash = hasher(STUDENT_PASSWORD)
    with tx() as cur:
        cur.execute("DELETE FROM tf_votes")
        cur.execute("DELETE FROM tf_applications")
        cur.execute("DELETE FROM tf_members")
        cur.execute("DELETE FROM tf_student_sub_roles")
        cur.execute("DELETE FROM tf_students WHERE NOT is_admin")
        cur.execute("DELETE FROM tf_teams")
        cur.execute("DELETE FROM tf_settings WHERE key = %s", (CLOSED_KEY,))

        for n in range(1, team_count + 1):
            cur.execute(
                "INSERT INTO tf_teams (team_no, name) VALUES (%s, %s)", (n, f"팀{n}")
            )
        for s in students:
            cur.execute(
                "INSERT INTO tf_students (student_no, name, main_role, password_hash) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (s.student_no, s.name, s.main_role, password_hash),
            )
            sid = cur.fetchone()[0]
            for role in s.sub_roles:
                cur.execute(
                    "INSERT INTO tf_student_sub_roles (student_id, role) VALUES (%s, %s)",
                    (sid, role),
                )


def _act(team_no: int | None, run) -> str:
    """팀 행을 잠그고 engine 의 판정을 기록한다."""
    try:
        with tx() as cur:
            if team_no is None:
                _lock_all_teams(cur)
            else:
                cur.execute("SELECT id FROM tf_teams WHERE team_no = %s FOR UPDATE", (team_no,))
                if cur.fetchone() is None:
                    return f"{BLOCKED}: 없는 팀"
            state, maps = _read(cur)
            before = _snapshot(state)
            message = run(state, maps)
            _write(cur, state, maps, before)
            return message
    except psycopg.errors.UniqueViolation:
        # 마지막 자리에 두 명이 동시에 들어가려 한 경우 — 먼저 도착한 학생만 남는다
        return f"{BLOCKED}: 다른 학생이 먼저 그 자리에 들어감"


def do_apply(student_no: str, team_no: int) -> str:
    return _act(team_no, lambda s, m: engine.apply_to_team(s, student_no, team_no))


def do_vote(applicant_no: str, voter_no: str, vote: str) -> str:
    def run(state: State, _maps: Maps) -> str:
        app = engine.pending_application_of(state, applicant_no)
        if app is None:
            return f"{BLOCKED}: {engine.NO_SUCH_APPLICATION}"
        return engine.cast_vote(state, app.id, voter_no, vote)

    return _act(None, run)


def do_close() -> str:
    def run(state: State, _maps: Maps) -> str:
        if state.closed:
            return f"{BLOCKED}: 이미 마감됨"
        engine.close_recruiting(state)
        return "승인: 모집을 마감함"

    return _act(None, run)


def do_confirm(plan: dict[str, int]) -> str:
    """배정안을 확정해 DB 에 저장한다."""

    def run(state: State, _maps: Maps) -> str:
        if not state.closed:
            return f"{BLOCKED}: 아직 마감하지 않음"
        for no, team_no in plan.items():
            if team_no not in state.teams:
                return f"{BLOCKED}: 없는 팀 {team_no}"
            if engine.team_of(state, no) is not None:
                return f"{BLOCKED}: 학번 {no}은(는) 이미 팀이 있음"
            state.teams[team_no].append(no)
        return "승인: 배정을 확정함"

    return _act(None, run)


def log_ai_attempts(attempts) -> None:
    with tx() as cur:
        for a in attempts:
            cur.execute(
                "INSERT INTO tf_ai_logs (tier, model, status, elapsed_ms, detail) "
                "VALUES (%s, %s, %s, %s, %s)",
                (a.tier, a.model, a.status, a.elapsed_ms, a.detail),
            )
