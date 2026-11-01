"""명단 CSV 파싱 — 공고 2.6절.

나눠 주는 CSV 는 엑셀에서 한글이 깨지지 않도록 BOM 이 붙은 UTF-8 이므로
utf-8-sig 로 읽는다.
"""

import csv
import io

from domain import ROLES, Student

HEADER = ("student_no", "name", "main_role", "sub_roles")


def parse_roster(raw: bytes | str) -> list[Student]:
    """명단 CSV 를 읽어 학생 목록을 돌려준다. 형식이 틀리면 ValueError."""
    text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw.lstrip("﻿")
    reader = csv.reader(io.StringIO(text))

    try:
        header = [c.strip() for c in next(reader)]
    except StopIteration:
        raise ValueError("명단이 비어 있음") from None
    if tuple(header[:4]) != HEADER:
        raise ValueError(f"첫 줄은 {','.join(HEADER)} 여야 함 (지금: {','.join(header)})")

    students: list[Student] = []
    seen: set[str] = set()
    for line_no, row in enumerate(reader, start=2):
        if not any(c.strip() for c in row):
            continue
        if len(row) < 4:
            raise ValueError(
                f"{line_no}번째 줄의 열이 {len(row)}개임. "
                "보조 역할이 없어도 마지막 쉼표를 남겨 4개여야 함"
            )

        student_no, name, main_role = (row[0].strip(), row[1].strip(), row[2].strip())
        sub_roles = tuple(r.strip() for r in row[3].split(";") if r.strip())

        if not student_no:
            raise ValueError(f"{line_no}번째 줄에 학번이 없음")
        if student_no in seen:
            raise ValueError(f"학번 {student_no}이(가) 두 번 나옴")
        if not name:
            raise ValueError(f"{line_no}번째 줄에 이름이 없음")
        if main_role not in ROLES:
            raise ValueError(f"{line_no}번째 줄의 주 역할 '{main_role}'은(는) 역할 6개에 없음")
        for r in sub_roles:
            if r not in ROLES:
                raise ValueError(f"{line_no}번째 줄의 보조 역할 '{r}'은(는) 역할 6개에 없음")
        if len(sub_roles) > 2:
            raise ValueError(f"{line_no}번째 줄의 보조 역할이 {len(sub_roles)}개임 (0~2개)")
        if main_role in sub_roles:
            raise ValueError(f"{line_no}번째 줄: 주 역할이 보조 역할에도 들어 있음")

        seen.add(student_no)
        students.append(Student(student_no, name, main_role, sub_roles))

    if not students:
        raise ValueError("명단에 학생이 없음")
    return students
