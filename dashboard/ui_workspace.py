from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class UIWorkspace:
    key: str
    name: str
    short_name: str
    description: str
    strengths: tuple[str, ...]
    theme_class: str


WORKSPACES: Final[tuple[UIWorkspace, ...]] = (
    UIWorkspace(
        key="apple_glass",
        name="Apple Institutional Glass",
        short_name="Apple Glass",
        description="밝은 실버·하늘색 글래스와 넓은 여백을 사용하는 균형형 전문가 UI",
        strengths=("장시간 사용", "아이패드", "고급스러운 시각 계층"),
        theme_class="theme-apple-glass",
    ),
    UIWorkspace(
        key="factset_exec",
        name="FactSet Executive Intelligence",
        short_name="FactSet",
        description="포트폴리오 성과·리스크·예외사항을 우선하는 기관 운용형 UI",
        strengths=("리스크", "성과", "포트폴리오"),
        theme_class="theme-factset",
    ),
    UIWorkspace(
        key="koyfin_research",
        name="Koyfin Modular Research",
        short_name="Koyfin",
        description="차트·워치리스트·비교분석을 넓게 배치하는 모듈형 리서치 UI",
        strengths=("리서치", "비교", "확장성"),
        theme_class="theme-koyfin",
    ),
    UIWorkspace(
        key="bloomberg_lite",
        name="Bloomberg Lite Command Terminal",
        short_name="Bloomberg",
        description="다크 테마와 높은 정보 밀도를 사용하는 트레이더 중심 UI",
        strengths=("속도", "정보 밀도", "장중 매매"),
        theme_class="theme-bloomberg",
    ),
    UIWorkspace(
        key="ai_copilot",
        name="AI Research Copilot Workspace",
        short_name="AI Copilot",
        description="분석·근거·위험요인을 함께 보여주는 AI 판단 보조형 UI",
        strengths=("AI 해석", "추천 근거", "의사결정"),
        theme_class="theme-ai-copilot",
    ),
)

DEFAULT_WORKSPACE_KEY: Final[str] = "apple_glass"


def get_workspace(key: str | None) -> UIWorkspace:
    normalized = str(key or "").strip()
    for workspace in WORKSPACES:
        if workspace.key == normalized:
            return workspace
    return next(item for item in WORKSPACES if item.key == DEFAULT_WORKSPACE_KEY)


def workspace_options() -> dict[str, UIWorkspace]:
    return {item.key: item for item in WORKSPACES}
