from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import streamlit as st


@dataclass(frozen=True)
class StatusBadge:
    label: str
    tone: str = "neutral"


BASE_CSS = """
<style>
:root{
  --ade-bg:#f4f7fb;
  --ade-panel:#ffffff;
  --ade-panel-soft:#f8fbff;
  --ade-ink:#10243a;
  --ade-muted:#6f8194;
  --ade-line:#dce6ef;
  --ade-blue:#2d78d4;
  --ade-blue-deep:#194f8f;
  --ade-green:#1f8b62;
  --ade-amber:#b97816;
  --ade-red:#ba4949;
  --ade-shadow:0 14px 38px rgba(32,66,101,.09);
}
.stApp{
  background:
    radial-gradient(circle at 10% 0%,rgba(96,169,244,.15),transparent 30%),
    linear-gradient(135deg,#f8fbfe 0%,#eef4fa 54%,#f9fcff 100%);
  color:var(--ade-ink);
}
.block-container{max-width:1880px;padding-top:.75rem;padding-bottom:3rem}
[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#0b2742,#0e365a 58%,#0a2948);
  border-right:1px solid rgba(255,255,255,.08)
}
[data-testid="stSidebar"] *{color:#edf7ff!important}
[data-testid="stSidebar"] a{border-radius:12px!important;margin:2px 7px!important;font-weight:720!important}
[data-testid="stSidebar"] a[aria-current="page"]{
  background:linear-gradient(135deg,rgba(97,176,255,.28),rgba(255,255,255,.08))!important;
  box-shadow:inset 0 0 0 1px rgba(142,204,255,.24)
}
.ade-shell{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;padding:25px 29px;border-radius:25px;background:linear-gradient(135deg,rgba(255,255,255,.98),rgba(239,247,255,.92));border:1px solid rgba(119,157,194,.24);box-shadow:var(--ade-shadow);margin-bottom:16px}
.ade-eyebrow{font-size:11px;letter-spacing:.18em;font-weight:900;color:#2d72b5;text-transform:uppercase}
.ade-shell h1{margin:6px 0 7px;font-size:35px;line-height:1.08;letter-spacing:-.045em}
.ade-shell p{margin:0;color:var(--ade-muted);font-size:14px}
.ade-shell-meta{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.ade-pill,.ade-badge{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:8px 11px;font-size:12px;font-weight:820;border:1px solid var(--ade-line);background:rgba(255,255,255,.86);color:#34536e}
.ade-badge.good{color:var(--ade-green);background:#eefaf5;border-color:#cdeadd}
.ade-badge.warn{color:var(--ade-amber);background:#fff7e8;border-color:#f0ddb4}
.ade-badge.bad{color:var(--ade-red);background:#fff0f0;border-color:#efcdcd}
.ade-badge.info{color:var(--ade-blue-deep);background:#edf5ff;border-color:#cfe2f7}
.ade-section{display:flex;justify-content:space-between;align-items:center;gap:18px;margin:21px 0 10px}
.ade-section h2{font-size:20px;margin:0;letter-spacing:-.03em}
.ade-section span{color:var(--ade-muted);font-size:13px}
.ade-card,.ade-kpi,.ade-panel{background:rgba(255,255,255,.92);border:1px solid var(--ade-line);border-radius:18px;box-shadow:0 10px 30px rgba(48,84,119,.07)}
.ade-card{padding:17px 18px}.ade-panel{padding:18px}.ade-kpi{padding:15px 16px;min-height:112px}
.ade-kpi span,.ade-kpi small{display:block;color:var(--ade-muted)}
.ade-kpi strong{display:block;margin:8px 0 5px;font-size:26px;letter-spacing:-.04em}
.ade-card h3,.ade-panel h3{margin:0 0 8px;font-size:17px}.ade-card p,.ade-panel p{margin:5px 0;color:var(--ade-muted);font-size:13px}
.ade-step{display:flex;gap:10px;align-items:flex-start;padding:13px 14px;border:1px solid var(--ade-line);border-radius:15px 15px 0 0;background:linear-gradient(135deg,#fff,#f1f7fc)}
.ade-step>span{display:flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:9px;background:var(--ade-blue);color:white;font-weight:900}
.ade-step b{display:block;color:#145f9f;font-size:16px}.ade-step small{display:block;color:var(--ade-muted);margin-top:2px}
.ade-action{padding:15px 16px;border-radius:16px;border:1px solid var(--ade-line);background:linear-gradient(135deg,#fff,#f6faff);min-height:108px}
.ade-action strong{display:block;color:#1b65aa;margin-bottom:5px}.ade-action span{display:block;color:var(--ade-muted);font-size:13px}
.ade-empty{padding:22px;border-radius:17px;border:1px dashed #bdd1e4;background:rgba(248,252,255,.9);color:var(--ade-muted);text-align:center}
.ade-divider{height:1px;background:var(--ade-line);margin:14px 0}
.ade-status-row{display:flex;justify-content:space-between;gap:15px;align-items:center;padding:11px 12px;border-radius:12px;background:#f9fbfd;border:1px solid var(--ade-line);margin:7px 0}
.ade-status-row span{color:var(--ade-muted);font-size:13px}
div[data-testid="stMetric"]{background:rgba(255,255,255,.93);border:1px solid var(--ade-line);padding:15px 16px;border-radius:17px;box-shadow:0 10px 30px rgba(48,84,119,.07)}
div[data-testid="stMetricLabel"]{font-weight:740;color:var(--ade-muted)}div[data-testid="stMetricValue"]{font-size:1.72rem;font-weight:880;color:var(--ade-ink)}
div[data-testid="stDataFrame"],div[data-testid="stPlotlyChart"]{border:1px solid var(--ade-line);border-radius:15px;overflow:hidden;background:white;box-shadow:0 8px 24px rgba(48,84,119,.05)}
.stButton>button,.stLinkButton>a{border-radius:12px!important;font-weight:780!important}
[data-testid="stExpander"]{border:1px solid var(--ade-line)!important;border-radius:15px!important;background:rgba(255,255,255,.88)!important}
@media(max-width:900px){.block-container{padding:.65rem}.ade-shell{display:block;padding:21px}.ade-shell h1{font-size:30px}.ade-shell-meta{justify-content:flex-start;margin-top:14px}.ade-section{align-items:flex-start}}
</style>
"""


def apply_design_system() -> None:
    st.markdown(BASE_CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str, eyebrow: str = "ADE · INVESTMENT OPERATIONS", badges: Iterable[StatusBadge] = ()) -> None:
    badge_html = "".join(
        f'<span class="ade-badge {html.escape(item.tone)}">{html.escape(item.label)}</span>'
        for item in badges
    )
    st.markdown(
        f"""
        <div class="ade-shell">
          <div>
            <div class="ade-eyebrow">{html.escape(eyebrow)}</div>
            <h1>{html.escape(title)}</h1>
            <p>{html.escape(subtitle)}</p>
          </div>
          <div class="ade-shell-meta">{badge_html or f'<span class="ade-pill">{datetime.now():%Y-%m-%d %H:%M}</span>'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section(title: str, caption: str = "") -> None:
    st.markdown(
        f'<div class="ade-section"><h2>{html.escape(title)}</h2><span>{html.escape(caption)}</span></div>',
        unsafe_allow_html=True,
    )


def kpi_card(label: str, value: str, note: str = "") -> str:
    return (
        '<div class="ade-kpi">'
        f'<span>{html.escape(label)}</span><strong>{html.escape(value)}</strong><small>{html.escape(note)}</small>'
        '</div>'
    )


def step_header(number: int, title: str, description: str) -> None:
    st.markdown(
        f'<div class="ade-step"><span>{number}</span><div><b>{html.escape(title)}</b><small>{html.escape(description)}</small></div></div>',
        unsafe_allow_html=True,
    )
