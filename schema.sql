-- 팀 편성 웹 앱 테이블 — 공고 5장
--
-- 6장 실습 테이블과 같은 Supabase 프로젝트를 쓰므로 이름 앞에 tf_ 를 붙여 구분한다.
-- 앱이 시작할 때 이 파일을 그대로 실행하므로, 앱이 실제로 쓰는 테이블·열·제약과 같다.

CREATE TABLE IF NOT EXISTS tf_students (
    id            SERIAL PRIMARY KEY,
    student_no    TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    main_role     TEXT NOT NULL,
    password_hash TEXT NOT NULL,          -- bcrypt 해시. 평문을 저장하지 않는다
    is_admin      BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT tf_students_main_role_check CHECK (
        main_role IN ('기획자', '웹 프로그래머', '프론트엔드 디자이너',
                      '테스터', '보고서 작성자', '발표자')
    )
);

CREATE TABLE IF NOT EXISTS tf_student_sub_roles (
    student_id INTEGER NOT NULL REFERENCES tf_students(id) ON DELETE CASCADE,
    role       TEXT NOT NULL,
    PRIMARY KEY (student_id, role),
    CONSTRAINT tf_sub_roles_role_check CHECK (
        role IN ('기획자', '웹 프로그래머', '프론트엔드 디자이너',
                 '테스터', '보고서 작성자', '발표자')
    )
);

CREATE TABLE IF NOT EXISTS tf_teams (
    id      SERIAL PRIMARY KEY,
    team_no INTEGER NOT NULL UNIQUE,      -- 화면의 팀1, 팀2 … 와 시나리오의 팀 번호
    name    TEXT NOT NULL UNIQUE
);

-- (team_id, slot_no) 를 기본 키로 두고 slot_no 를 1~4 로 제한하면,
-- 마지막 자리에 두 명이 동시에 들어가려 할 때 먼저 도착한 학생만 기록된다.
-- student_id 의 유일성 제약은 한 학생이 한 팀에만 속하게 한다.
CREATE TABLE IF NOT EXISTS tf_members (
    team_id    INTEGER NOT NULL REFERENCES tf_teams(id) ON DELETE CASCADE,
    slot_no    INTEGER NOT NULL,
    student_id INTEGER NOT NULL UNIQUE REFERENCES tf_students(id) ON DELETE CASCADE,
    PRIMARY KEY (team_id, slot_no),
    CONSTRAINT tf_members_slot_no_check CHECK (slot_no BETWEEN 1 AND 4)
);

CREATE TABLE IF NOT EXISTS tf_applications (
    id         SERIAL PRIMARY KEY,
    team_id    INTEGER NOT NULL REFERENCES tf_teams(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES tf_students(id) ON DELETE CASCADE,
    status     TEXT NOT NULL DEFAULT '대기',
    reason     TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT tf_applications_status_check CHECK (status IN ('대기', '승인', '거절'))
);

CREATE INDEX IF NOT EXISTS tf_applications_team_idx ON tf_applications (team_id, status);

-- 한 번 투표하면 바꿀 수 없다
CREATE TABLE IF NOT EXISTS tf_votes (
    application_id INTEGER NOT NULL REFERENCES tf_applications(id) ON DELETE CASCADE,
    voter_id       INTEGER NOT NULL REFERENCES tf_students(id) ON DELETE CASCADE,
    vote           TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (application_id, voter_id),
    CONSTRAINT tf_votes_vote_check CHECK (vote IN ('찬성', '거부'))
);

CREATE TABLE IF NOT EXISTS tf_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- AI 호출 기록. README 의 실패 사례를 적을 때 근거로 쓴다
CREATE TABLE IF NOT EXISTS tf_ai_logs (
    id         SERIAL PRIMARY KEY,
    tier       INTEGER NOT NULL,
    model      TEXT NOT NULL,
    status     TEXT NOT NULL,
    elapsed_ms INTEGER NOT NULL,
    detail     TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
