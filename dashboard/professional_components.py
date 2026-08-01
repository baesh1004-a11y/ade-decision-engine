from __future__ import annotations

import html
from typing import Any, Iterable

import streamlit as st

from dashboard.ui_workspace import UIWorkspace


def _text(value: Any) -> str:
    return html.escape(str(value if value is not None else "-"))


def render_page_header(
    title: str,
    subtitle: str,
    *,
    eyebrow: str = "ADE PROFESSIONAL",
    badges: Iterable[str] = (),
) -> None:
    badge_html = "".join(f'<span class="ade-badge">{_text(item)}</span>' for item in badges)
    st.markdown(
        f"""
        <section class="ade-pro-header">
          <div>
            <div class="ade-pro-eyebrow">{_text(eyebrow)}</div>
            <h1>{_text(title)}</h1>
            <p>{_text(subtitle)}</p>
          </div>
          <div class="ade-pro-badges">{badge_html}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_workspace_intro() -> None:
    st.markdown(
        """
        <section class="ade-workspace-intro">
          <div class="ade-pro-eyebrow">ADE UI ENGINE</div>
          <h1>전문가 워크스페이스 선택</h1>
          <p>기능과 주문 안전장치는 동일하게 유지되며, 정보 배치와 시각 체계만 워크스페이스별로 달라집니다.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_workspace_card(workspace: UIWorkspace, *, selected: bool) -> None:
    strengths = "".join(f'<span>{_text(item)}</span>' for item in workspace.strengths)
    selected_class = " selected" if selected else ""
    st.markdown(
        f"""
        <article class="ade-workspace-card{selected_class}">
          <div class="ade-workspace-number">{_text(workspace.short_name)}</div>
          <h3>{_text(workspace.name)}</h3>
          <p>{_text(workspace.description)}</p>
          <div class="ade-workspace-strengths">{strengths}</div>
        </article>
        """,
        unsafe_allow_html=True,
    )


def render_kpi_strip(items: Iterable[dict[str, Any]]) -> None:
    cards: list[str] = []
    for item in items:
        tone = str(item.get("tone") or "neutral")
        cards.append(
            f"""
            <article class="ade-kpi-card tone-{_text(tone)}">
              <span>{_text(item.get('label'))}</span>
              <strong>{_text(item.get('value'))}</strong>
              <small>{_text(item.get('detail'))}</small>
            </article>
            """
        )
    st.markdown(f'<section class="ade-kpi-strip">{"".join(cards)}</section>', unsafe_allow_html=True)


def render_section_header(title: str, description: str = "", *, tag: str | None = None) -> None:
    tag_html = f'<span class="ade-section-tag">{_text(tag)}</span>' if tag else ""
    st.markdown(
        f"""
        <div class="ade-section-head">
          <div>
            <h3>{_text(title)}</h3>
            <p>{_text(description)}</p>
          </div>
          {tag_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_status_chips(items: Iterable[tuple[str, str, str]]) -> None:
    chips = "".join(
        f'<span class="ade-status-chip tone-{_text(tone)}"><b>{_text(label)}</b>{_text(value)}</span>'
        for label, value, tone in items
    )
    st.markdown(f'<div class="ade-status-chips">{chips}</div>', unsafe_allow_html=True)


def recommendation_rows(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        score = float(record.get("score") or record.get("final_similarity") or 0)
        rows.append(
            {
                "순위": int(record.get("rank_no") or 0),
                "종목": str(record.get("symbol") or record.get("name") or record.get("ticker") or "-"),
                "코드": str(record.get("ticker") or "-"),
                "추천점수": round(score, 1),
                "판단": "강" if score >= 80 else ("중" if score >= 65 else "관찰"),
            }
        )
    return rows
