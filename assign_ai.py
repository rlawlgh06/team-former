"""오픈라우터로 배정안을 받는다 — 공고 2.5절 3~6항, 4.3절.

모델 3개를 1·2·3차로 쓰고, 앞 모델이 실패하면 다음 모델로 넘어간다.
시간 제한은 벽시계로 전체를 잰다. requests 의 timeout 은 연결과 첫 바이트
까지만 재므로 느리게 흘러드는 응답을 끊지 못한다 (공고 3장 어려운 해결).
"""

import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field

import requests

from domain import REQUIRED_ROLES, TEAM_MAX, TEAM_MIN, Student
from rules import validate_assignment

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_TIMEOUT = 120.0

OK = "성공"
TIMEOUT = "시간 초과"
ERROR = "오류"
EMPTY = "빈 응답"
UNPARSABLE = "응답을 읽을 수 없음"
INVALID = "규칙 위반"


@dataclass
class Attempt:
    tier: int
    model: str
    status: str
    elapsed_ms: int
    detail: str = ""


@dataclass
class Progress:
    """배정이 도는 동안 화면에 보여 줄 상태."""

    tier: int = 0
    model: str = ""
    started_at: float = field(default_factory=time.monotonic)
    finished: bool = False
    note: str = ""

    def elapsed(self) -> float:
        return time.monotonic() - self.started_at


# --- 프롬프트와 응답 ---------------------------------------------------------


def build_prompt(
    teams: Mapping[int, Sequence[Student]],
    unassigned: Sequence[Student],
) -> str:
    def 사람(s: Student) -> str:
        subs = ", ".join(s.sub_roles) if s.sub_roles else "없음"
        return f"- 학번 {s.student_no} {s.name}: 주 역할 {s.main_role}, 보조 역할 {subs}"

    팀_설명 = []
    for no in sorted(teams):
        ms = teams[no]
        몸통 = "\n".join(사람(m) for m in ms) if ms else "- (비어 있음)"
        팀_설명.append(f"팀{no} (현재 {len(ms)}명)\n{몸통}")

    first, second = REQUIRED_ROLES
    return f"""너는 팀 편성을 돕는다. 팀이 없는 학생을 팀에 배정해라.

[현재 팀 구성]
{chr(10).join(팀_설명)}

[팀이 없는 학생]
{chr(10).join(사람(s) for s in unassigned)}

[반드시 지킬 규칙]
1. 팀이 없는 학생을 빠짐없이 배정한다. 한 학생은 한 팀에만 넣는다.
2. 이미 팀에 있는 학생은 옮기지 않는다.
3. 배정이 끝난 뒤 모든 팀은 {TEAM_MIN}명 이상 {TEAM_MAX}명 이하여야 한다. 빈 팀이 있으면 안 된다.
4. 한 팀에 주 역할이 같은 학생이 2명 이상이면 안 된다.
5. 모든 팀에 {first}와 {second}가 서로 다른 사람으로 1명씩 있어야 한다.
   주 역할이든 보조 역할이든 맡을 수 있다. 한 학생이 둘 다 맡을 수는 없다.

[출력 형식]
설명 없이 JSON 객체 하나만 출력해라. 키는 팀이 없는 학생의 학번(문자열),
값은 배정할 팀 번호(정수)다.
예: {{"2026101": 1, "2026102": 3}}
"""


def parse_plan(text: str) -> dict[str, int] | None:
    """응답에서 배정안을 꺼낸다. 읽을 수 없으면 None.

    무료 모델은 JSON 앞뒤에 설명이나 코드 울타리를 자주 붙인다.
    """
    if not text or not text.strip():
        return None

    후보 = [text]
    fenced = re.findall(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    후보 = fenced + 후보
    braced = re.findall(r"\{.*\}", text, re.DOTALL)
    후보 = 후보 + braced

    for chunk in 후보:
        try:
            data = json.loads(chunk.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        plan = _as_plan(data)
        if plan:
            return plan
    return None


def _as_plan(data: object) -> dict[str, int] | None:
    if not isinstance(data, dict):
        return None

    # {"assignments": [{"student_no": "...", "team": 1}, ...]} 꼴도 받아 준다
    rows = data.get("assignments") if "assignments" in data else None
    if isinstance(rows, list):
        plan: dict[str, int] = {}
        for row in rows:
            if not isinstance(row, dict):
                return None
            no = row.get("student_no") or row.get("학번")
            team = row.get("team") or row.get("team_no") or row.get("팀")
            if no is None or team is None:
                return None
            try:
                plan[str(no).strip()] = int(team)
            except (TypeError, ValueError):
                return None
        return plan or None

    plan = {}
    for no, team in data.items():
        try:
            plan[str(no).strip()] = int(team)
        except (TypeError, ValueError):
            return None
    return plan or None


# --- 호출 -------------------------------------------------------------------


def openrouter_call(model: str, prompt: str, *, api_key: str, timeout: float) -> str:
    """오픈라우터를 한 번 부른다. 본문 텍스트를 돌려준다."""
    response = requests.post(
        ENDPOINT,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            # 추론 모델이 생각하는 데 한도를 다 써서 빈 응답을 내는 일을 줄인다
            "reasoning": {"effort": "low"},
            "max_tokens": 4000,
            "temperature": 0.2,
        },
        timeout=timeout,
    )
    if response.status_code != 200:
        # 키가 섞여 들어가지 않도록 상태 코드와 짧은 본문만 남긴다
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")

    body = response.json()
    choices = body.get("choices") or []
    if not choices:
        return ""
    return (choices[0].get("message") or {}).get("content") or ""


def run_assignment(
    models: Sequence[str],
    teams: Mapping[int, Sequence[Student]],
    unassigned: Sequence[Student],
    *,
    call: Callable[..., str],
    on_progress: Callable[[int, str], None] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[dict[str, int] | None, list[Attempt]]:
    """1·2·3차 모델을 차례로 불러 검사를 통과한 배정안을 얻는다."""
    prompt = build_prompt(teams, unassigned)
    attempts: list[Attempt] = []

    for tier, model in enumerate(models, start=1):
        if on_progress:
            on_progress(tier, model)

        started = time.monotonic()
        status, detail, text = OK, "", ""

        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(call, model, prompt, timeout=timeout)
            text = future.result(timeout=timeout)
        except FutureTimeout:
            status, detail = TIMEOUT, f"{timeout:.0f}초 안에 응답하지 않음"
        except Exception as exc:  # 네트워크 오류, HTTP 오류, 잘못된 JSON 본문
            status, detail = ERROR, str(exc)[:200]
        finally:
            executor.shutdown(wait=False)

        elapsed_ms = int((time.monotonic() - started) * 1000)

        if status == OK:
            if not text.strip():
                status, detail = EMPTY, "본문이 비어 있음"
            else:
                plan = parse_plan(text)
                if plan is None:
                    status, detail = UNPARSABLE, text.strip()[:200]
                else:
                    violations = validate_assignment(teams, unassigned, plan)
                    if violations:
                        status, detail = INVALID, "; ".join(violations)[:300]
                    else:
                        attempts.append(Attempt(tier, model, OK, elapsed_ms))
                        return plan, attempts

        attempts.append(Attempt(tier, model, status, elapsed_ms, detail))

    return None, attempts
