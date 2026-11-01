"""비밀번호 해시 — 공고 6.3절 10번(평문 저장은 감점)."""

from auth import hash_password, verify_password


def test_해시는_평문과_다르다():
    assert hash_password("1234") != "1234"


def test_같은_비밀번호를_두_번_해시하면_값이_다르다():
    assert hash_password("1234") != hash_password("1234")


def test_맞는_비밀번호는_통과():
    assert verify_password("1234", hash_password("1234"))


def test_틀린_비밀번호는_거부():
    assert not verify_password("4321", hash_password("1234"))


def test_빈_비밀번호는_거부():
    assert not verify_password("", hash_password("1234"))


def test_해시가_망가져_있어도_예외를_내지_않는다():
    assert not verify_password("1234", "해시가 아님")
