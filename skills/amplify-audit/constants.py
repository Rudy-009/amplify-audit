"""Shared constants for amplify-audit."""

from __future__ import annotations

LABELS = {
    "ambiguous": ("Ambiguous", "판정이 성립하지 않음"),
    "steer": ("Steer", "통제하며 이끌기"),
    "ground": ("Ground", "모르는 걸 파악하기"),
    "deepen": ("Deepen", "오래 남게 연습"),
    "expand": ("Expand", "가능성 넓히기"),
    "offload": ("Offload", "인지 작업 위임"),
    "ceded_decisions": ("Ceded Decisions", "판단권을 넘김"),
    "skipped_verification": ("Skipped Verification", "검증을 생략"),
    "illusion_of_competence": ("Illusion of Competence", "이해했다는 착각"),
    "capability_not_formed": ("Capability Not Formed", "역량이 형성되지 않음"),
    "none": ("Neutral", "기계적 요청"),
}

AMP = ["steer", "ground", "deepen", "expand"]
BYP = ["ceded_decisions", "skipped_verification", "illusion_of_competence",
       "capability_not_formed"]

GATES = [
    ("understood", "상황 이해", "결과를 이해 가능한 형태로 받았는가"),
    ("relieved", "여력 확보", "인지 부담이 정말 감소했는가"),
    ("eligible", "위임 적격", "반복이 내 역량이 될 것은 아니었는가"),
]

# 색 계열: Amplify=파랑, Offload=초록, Bypass=빨강
VERDICT_VAR = {
    "amplify": "--blue",
    "offload": "--green",
    "bypass": "--red",
    "neutral": "--gray3",
    "ambiguous": "--gray3",
}

TAG_VAR = {
    "steer": "--blue",
    "ground": "--teal",
    "deepen": "--indigo",
    "expand": "--cyan",
    "offload": "--green",
    "ceded_decisions": "--orange",
    "skipped_verification": "--red",
    "illusion_of_competence": "--pink",
    "capability_not_formed": "--purple",
    "none": "--gray",
}

AMBIGUITY = {"context": "맥락 부족", "prompt": "프롬프트 자체"}

JUDGEMENT_FIELDS = ("verdict", "tag", "gates", "ambiguity", "reason")
