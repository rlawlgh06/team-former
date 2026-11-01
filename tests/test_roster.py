"""명단 CSV 파싱 — 공고 2.6절."""

from pathlib import Path

import pytest

from roster import parse_roster

HERE = Path(__file__).parent


def test_BOM이_붙은_CSV를_읽는다():
    raw = "﻿student_no,name,main_role,sub_roles\n2026001,가나다,기획자,\n".encode()
    students = parse_roster(raw)
    assert students[0].student_no == "2026001"
    assert students[0].name == "가나다"


def test_보조역할이_빈칸이면_0개():
    raw = b"student_no,name,main_role,sub_roles\n2026002,\xeb\x9d\xbc,\xec\x9b\xb9 \xed\x94\x84\xeb\xa1\x9c\xea\xb7\xb8\xeb\x9e\x98\xeb\xa8\xb8,\n"
    assert parse_roster(raw)[0].sub_roles == ()


def test_보조역할_2개는_세미콜론으로_나눈다():
    raw = "student_no,name,main_role,sub_roles\n2026003,사아자,테스터,기획자;발표자\n"
    assert parse_roster(raw)[0].sub_roles == ("기획자", "발표자")


def test_칸_앞뒤_공백을_없앤다():
    raw = "student_no,name,main_role,sub_roles\n 2026001 , 가나다 , 기획자 , 보고서 작성자 \n"
    s = parse_roster(raw)[0]
    assert (s.student_no, s.main_role, s.sub_roles) == ("2026001", "기획자", ("보고서 작성자",))


def test_역할_밖의_값은_오류():
    raw = "student_no,name,main_role,sub_roles\n2026001,가나다,디자이너,\n"
    with pytest.raises(ValueError, match="역할 6개"):
        parse_roster(raw)


def test_학번이_중복되면_오류():
    raw = (
        "student_no,name,main_role,sub_roles\n"
        "2026001,가나다,기획자,\n"
        "2026001,라마바,테스터,\n"
    )
    with pytest.raises(ValueError, match="두 번"):
        parse_roster(raw)


def test_마지막_쉼표를_지우면_오류():
    raw = "student_no,name,main_role,sub_roles\n2026002,라마바,테스터\n"
    with pytest.raises(ValueError, match="열이"):
        parse_roster(raw)


def test_첫_줄이_다르면_오류():
    with pytest.raises(ValueError, match="첫 줄"):
        parse_roster("no,name,role\n1,가,기획자\n")


def test_나눠_준_명단_3개를_읽는다():
    assert len(parse_roster(( HERE / "쉬움.csv").read_bytes())) == 8
    assert len(parse_roster((HERE / "중간.csv").read_bytes())) == 12
    assert len(parse_roster((HERE / "어려움.csv").read_bytes())) == 16
