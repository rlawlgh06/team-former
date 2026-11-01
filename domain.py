"""역할, 팀 상수, 학생 자료형."""

from dataclasses import dataclass, field

ROLES = (
    "기획자",
    "웹 프로그래머",
    "프론트엔드 디자이너",
    "테스터",
    "보고서 작성자",
    "발표자",
)

# 모든 팀에 서로 다른 사람으로 1명씩 있어야 하는 역할
REQUIRED_ROLES = ("기획자", "웹 프로그래머")

TEAM_MIN = 2
TEAM_MAX = 4

# 지원·투표 결과 안내의 첫 단어
APPROVED = "승인"
PENDING = "대기"
REJECTED = "거절"
BLOCKED = "막힘"

VOTE_YES = "찬성"
VOTE_NO = "거부"


@dataclass(frozen=True)
class Student:
    student_no: str
    name: str
    main_role: str
    sub_roles: tuple[str, ...] = field(default=())

    def can_take(self, role: str) -> bool:
        """주 역할이거나 보조 역할이면 그 역할을 맡을 수 있다."""
        return role == self.main_role or role in self.sub_roles

    @property
    def roles_text(self) -> str:
        if not self.sub_roles:
            return self.main_role
        return f"{self.main_role} (보조: {', '.join(self.sub_roles)})"
