# 팀 편성 웹 앱

학생이 지원과 투표로 팀을 편성하고, 마감 뒤 남은 학생은 AI 가 배정하되 앱이 그 배정을 규칙으로 검사한다.

작성자: 김지호

---

## 1. 배포 주소

https://team-former-2601936.streamlit.app

## 2. PRD 와 구현 계획

- [`docs/PRD.md`](docs/PRD.md)
- [`docs/구현 계획.md`](docs/구현%20계획.md)

## 3. 고른 해결 방법

공고 3장 표의 일곱 가지를 **모두 어려운 해결**로 만들었다.

| 기능 | 고른 것 | 어떻게 |
| --- | --- | --- |
| 다른 사람의 변경 보기 | 어려운 해결 | `st.fragment(run_every=3)` 으로 팀 목록·투표 영역만 3초마다 자동 갱신. `refresh` 단추는 두지 않음 |
| 필수 포함 역할을 지킬 수 없는 팀 | 어려운 해결 | 지원 단계에서 막음. 기획자와 웹 프로그래머를 서로 다른 사람이 맡아야 하므로 최대 이분 매칭으로 채운 수를 세고, 지원자가 들어간 뒤 남는 자리가 못 채운 역할 수보다 적으면 막음 (`rules.apply_block_reason`) |
| 같은 팀에 대기 중인 지원이 여럿 | 어려운 해결 | 모든 팀원이 찬성한 순간 같은 트랜잭션 안에서 규칙을 다시 검사해 어기면 거절. 처리 순서는 지원 순서가 아니라 투표가 끝난 순서 (`engine.cast_vote`) |
| 마지막 자리에 두 명이 동시에 들어감 | 어려운 해결 | `tf_members` 의 기본 키 `(team_id, slot_no)` 와 `student_id` 유일성 제약으로 먼저 도착한 학생만 기록. 유일성 위반은 "막힘" 으로 돌려줌 |
| AI 응답이 늦을 때 | 어려운 해결 | 모델마다 벽시계로 전체 120초를 재서 끊고 다음 모델로 넘어감. `requests` 의 `timeout` 은 연결과 첫 바이트까지만 재므로 쓰지 않고 `ThreadPoolExecutor` + `future.result(timeout=120)` 으로 전체를 잼 (`assign_ai.run_assignment`) |
| 3차 모델까지 실패 | 어려운 해결 | 공고 2.5절 4항의 검사 다섯 가지를 모두 통과하는 배정을 가지치기 백트래킹으로 끝까지 찾음 (`assign_solver.solve`) |
| DB 가 일시정지되지 않게 | 어려운 해결 | GitHub Actions 예약 작업이 매일 한국 시각 정오에 DB 에 질의 ([`.github/workflows/keepalive.yml`](.github/workflows/keepalive.yml)) |

규칙을 지키는 배정이 아예 존재하지 않으면 AI 를 부르지 않고 `assign_status` 에 이유를 보여 준다 (공고 2.5절 8항). 무료 모델의 하루 호출 한도를 아끼는 효과도 있다.

## 4. 쓴 모델 3개

1. `cohere/north-mini-code:free`
2. `google/gemma-4-31b-it:free`
3. `xingchen-agi/xing4.0-29b-a4b:free`

2026-11-01 에 오픈라우터의 무료 모델 전부를 실제로 불러 보고 골랐다. 제공자를 서로 다르게 한 이유는 한 제공자가 HTTP 429 를 내도 나머지가 살아 있게 하기 위해서다. 실제로 구글 모델 두 개는 같은 시각에 함께 429 를 냈다.

무료 모델로 자동 연결하는 라우터(`openrouter/free`)는 쓰지 않았다.

## 5. 오픈라우터 AI 모델 호출 실패 사례

2026-11-01 에 무료 모델을 세 차례에 걸쳐 실제로 불러 봤다. **호출 23번 가운데 통과는 3번**이었다. 전체 기록은 [`docs/모델 시험 기록.md`](docs/모델%20시험%20기록.md) 에 있다.

**사례 1 — AI 가 낸 배정안이 규칙을 어겨 앱이 걸러 냄**

`cohere/north-mini-code:free` 가 39.2초 만에 배정안을 냈는데, **팀3에 6명**을 넣었다. 팀 인원은 2~4명이어야 하므로 앱의 검사(`rules.validate_assignment`)가 걸러 내고 실패로 처리했다.

```
cohere/north-mini-code:free    규칙위반  39.2s  팀3: 인원이 6명 (2~4명이어야 함)
```

같은 모델이 바로 앞 시험에서는 39.3초에 올바른 배정안을 냈다. 무료 모델은 같은 요청에도 결과가 달라진다.

**사례 2 — 모델이 120초를 넘겨 앱이 끊음**

`nvidia/nemotron-3-ultra-550b-a55b:free` 는 같은 프롬프트에 81.5초 → **226.8초** → 99.5초가 걸렸다. 226.8초는 앱의 120초 제한에 걸려 끊기고 2차 모델로 넘어간다. `requests` 의 `timeout` 만 썼다면 끊지 못했을 경우다. 그래서 `ThreadPoolExecutor` + `future.result(timeout=120)` 으로 벽시계 전체를 잰다.

**사례 3 — 빈 응답과 HTTP 오류**

`nvidia/nemotron-3.5-lightning:free` 와 `nemotron-3-nano-omni-reasoning:free` 는 HTTP 200 을 주고도 본문이 비어 있었다(72.7초, 89.5초). 추론에 길이 한도를 다 쓴 것으로 보인다. 구글 모델 두 개와 xingchen 은 **같은 시각에 함께 HTTP 429** 를 냈고, `thinkingmachines/inkling-small:free` 는 HTTP 403(유료 플랜 전용)을 냈다. 앱은 이 모두를 실패로 보고 다음 모델로 넘어간다.

**사례 4 — JSON 대신 추론을 글로 씀**

1차 시험에서 nvidia 모델이 이렇게 답했다.

```
'We need to assign 8 unassigned students to teams 1-4, respecting const...'
```

이 일을 겪고 프롬프트에 "첫 글자는 `{` 이고 마지막 글자는 `}` 여야 한다" 를 넣고 `max_tokens` 를 8000 으로 늘렸으며, 글 속에 섞인 JSON 도 찾아내도록 파서를 고쳤다(`assign_ai._balanced_objects`, 커밋 `2b15436`). 고친 뒤 같은 모델이 3차 시험에서 통과했다.

**배포한 앱에서의 화면**

![AI 대기 중](img/ai-waiting.jpg)

`assign_status` 에 **몇 차 모델을 기다리는 중인지와 경과 시간**을 보여 준다(위 화면: `1차 모델 응답 대기 중 (14초) — cohere/north-mini-code:free`).

![AI 배정안이 검사를 통과함](img/ai-success.jpg)

끝나면 어느 모델이 어떻게 됐는지와 배정안을 보여 주고 확정을 기다린다.

## 6. 클로드가 잘못된 추론이나 답변을 한 사례

**사례 1 — 있지도 않은 모델 이름을 기본값으로 넣음 (커밋 `c0d6613`)**

클로드는 1·2·3차 모델의 기본값으로 `deepseek/deepseek-chat-v3.1:free`, `meta-llama/llama-3.3-70b-instruct:free`, `qwen/qwen3-235b-a22b:free` 를 적었다. 그럴듯해 보였지만 **셋 다 지금 오픈라우터의 무료 모델 목록에 없다.** 학습 당시의 기억으로 쓴 것이다.

오픈라우터의 `/api/v1/models` 를 직접 불러 무료 모델이 14개뿐이고 이름이 전혀 다르다는 것을 확인해 알아챘다. 그대로 두었다면 채점 때 세 모델 모두 404 를 내고 AI 배정이 한 번도 성공하지 못했을 것이다. 실제로 불러 본 결과로 교체했다.

**사례 2 — 쓸 수 없는 DB 라이브러리를 지정함 (커밋 `8b77ddc`)**

클로드는 `requirements.txt` 에 `psycopg2-binary` 를 적었다. 이 PC 의 파이썬은 3.14 인데 `psycopg2-binary` 는 3.14 용 wheel 이 없어 설치가 소스 빌드로 넘어가며 실패했다. 설치 오류를 보고 알아챘고 `psycopg[binary]`(psycopg3)로 바꿨다.

나중에 배포하면서 이 교체가 로컬만 살린 것이 아님을 알았다. Streamlit Community Cloud 의 빌드 로그에 `Using Python 3.14.10 environment` 라고 찍혔다. 그대로 두었다면 배포도 같은 이유로 실패했을 것이다.

바꾸면서 생긴 문제도 하나 있었다. psycopg3 은 같은 질의를 다섯 번 쓰면 자동으로 prepared statement 를 만드는데, Supabase 의 transaction pooler 는 이를 지원하지 않는다. 로컬에서는 질의 수가 적어 드러나지 않고 채점 중에 터졌을 문제라, `prepare_threshold=None` 으로 꺼 두었다 (커밋 `30019a7`).

## 7. 본인이 제출한 앱에서 발견한 문제점

**문제 1 — AI 배정 중 관리자 화면이 멈춘 것처럼 보임**

부록 3(어려움) 15단계(관리자가 배정)에서 발견했다. 위 `img/ai-waiting.jpg` 가 그 순간이다. `assign_status` 에 경과 시간이 갱신되기는 하지만, **화면의 나머지가 흐려지고 다른 단추가 눌리지 않는다.** 배정을 기다리는 반복문이 Streamlit 의 스크립트 실행을 붙잡고 있기 때문이다.

세 모델이 모두 느리게 실패하면 최악의 경우 6분까지 이 상태가 이어질 수 있다. 전체 상한을 400초로 두어 그 이상은 넘어가지 않게 했지만, 근본적으로는 배정을 백그라운드 작업으로 돌리고 화면은 상태만 읽어 가는 구조로 바꿔야 한다.

**문제 2 — 투표 한 번에 모든 팀을 잠금**

`db.do_vote` 는 어느 팀의 투표인지 트랜잭션을 열기 전에는 알 수 없어서 모든 팀 행을 잠근다. 그래서 서로 다른 팀의 투표가 동시에 들어와도 차례로 처리된다. 학생 16명 규모에서는 동작당 55ms 라 문제가 드러나지 않지만, 규모가 커지면 병목이 된다. 지원자 학번으로 팀을 먼저 찾고 그 팀만 잠그면 해결된다.

## 8. 직접 확인한 것

| 확인 | 방법 | 결과 |
| --- | --- | --- |
| 규칙·엔진·파서 단위 테스트 | `py -m pytest tests/` | 90개 통과 |
| 부록 시나리오 3개 (메모리) | `tests/test_scenarios.py` | 모든 단계의 첫 단어가 공고의 기대와 일치 |
| 부록 시나리오 3개 (실제 Supabase) | 명단 올리기부터 확정까지 | 55개 동작 전부 일치, 확정 결과 규칙 위반 없음 |
| 화면 요소 `key` 17개 | `streamlit.testing.v1.AppTest` | 전부 존재 |
| 틀린 비밀번호·학번만 로그인 | 같음 | 거부됨 |
| 커밋 기록의 비밀 값 | `git log --all -p` 검색 | 키·DB 주소·관리자 비밀번호 없음 |
| 배포한 앱이 로그인 없이 열리는지 | 쿠키 없는 새 세션으로 접속 | HTTP 200, 로그인 요구 없음 |
| DB 일시정지 방지 | GitHub Actions 를 수동 실행 | `살아 있음. 학생 수: 17` |
| 배포한 앱의 AI 배정 | 어려움 14단계 상태에서 실행 | 1차 모델 성공, 검사 통과, 확정 가능 |
| 동시 지원 | 같은 팀에 두 학생이 동시 지원 3회 | 한 명만 들어가고 뒤는 `막힘` |

## 9. 테이블

테이블 이름은 모두 `tf_` 로 시작한다. DDL 은 [`schema.sql`](schema.sql) 에 있고 앱이 시작할 때 그대로 실행하므로 앱이 쓰는 것과 같다.

`tf_students`, `tf_student_sub_roles`, `tf_teams`, `tf_members`, `tf_applications`, `tf_votes`, `tf_settings`, 그리고 AI 호출 기록을 남기는 `tf_ai_logs`.

비밀번호는 bcrypt 해시로만 저장한다 (`tf_students.password_hash`).

## 10. 직접 돌려 보려면

```
py -m pip install -r requirements.txt
py -m pytest tests/ -q
py -m streamlit run streamlit_app.py
```

`.env` 에 `OPENROUTER_API_KEY`, `DATABASE_URL`, `ADMIN_PASSWORD` 가 있어야 한다. 양식은 [`.env.example`](.env.example) 참고. 배포할 때는 같은 이름으로 Streamlit Secrets 에 넣는다.
