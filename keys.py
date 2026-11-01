"""화면 요소의 Streamlit key.

자동 채점 프로그램이 이 key 로 요소를 찾으므로 공고 2.7절 표와 글자 하나까지
같아야 한다. key 문자열을 다른 파일에 직접 쓰지 않고 여기서만 가져다 쓴다.
"""

LOGIN_STUDENT_NO = "login_student_no"
LOGIN_PASSWORD = "login_password"
LOGIN_SUBMIT = "login_submit"
WHOAMI = "whoami"
RESULT = "result"

ADMIN_ROSTER_FILE = "admin_roster_file"
ADMIN_TEAM_COUNT = "admin_team_count"
ADMIN_START = "admin_start"
ADMIN_CLOSE = "admin_close"
UNASSIGNED = "unassigned"
ADMIN_ASSIGN = "admin_assign"
ASSIGN_STATUS = "assign_status"
ADMIN_CONFIRM = "admin_confirm"


def team_key(team_no: int) -> str:
    return f"team_{team_no}"


def apply_key(team_no: int) -> str:
    return f"apply_{team_no}"


def vote_yes_key(student_no: str) -> str:
    return f"vote_yes_{student_no}"


def vote_no_key(student_no: str) -> str:
    return f"vote_no_{student_no}"
