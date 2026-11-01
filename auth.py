"""로그인 — 학번과 비밀번호. 비밀번호는 bcrypt 해시로만 저장한다.

구글 로그인(st.login)은 채점자가 학생 여러 명으로 로그인할 수 없으므로 쓰지 않는다.
"""

from dataclasses import dataclass

import bcrypt


@dataclass(frozen=True)
class Account:
    student_no: str
    name: str
    is_admin: bool


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


def login(student_no: str, password: str) -> Account | None:
    """학번과 비밀번호가 맞아야 들어온다. 학번만으로는 들어올 수 없다."""
    import db

    student_no = (student_no or "").strip()
    if not student_no or not password:
        return None

    with db.tx() as cur:
        cur.execute(
            "SELECT name, password_hash, is_admin FROM tf_students WHERE student_no = %s",
            (student_no,),
        )
        row = cur.fetchone()

    if row is None:
        return None
    name, password_hash, is_admin = row
    if not verify_password(password, password_hash):
        return None
    return Account(student_no, name, bool(is_admin))
