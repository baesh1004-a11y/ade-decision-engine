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
  --ade-bg:#eef3f8;
  --ade-panel:#ffffff;
  --ade-panel-soft:#f6f9fc;
  --ade-panel-strong:#eaf1f8;
  --ade-ink:#11263d;
  --ade-muted:#72849a;
  --ade-line:#dce6f0;
  --ade-blue:#2f78d6;
  --ade-blue-deep:#19559a;
  --ade-cyan:#49a8dc;
  --ade-green:#198761;
  --ade-amber:#b67818;
  --ade-red:#ba4a4a;
  --ade-shadow:0 18px 48px rgba(38,65,94,.11);
  --ade-shadow-soft:0 10px 28px rgba(38,65,94,.08);
}
*{box-sizing:border-box}
html,body,[data-testid="stAppViewContainer"],.stApp{background:var(--ade-bg);color:var(--ade-ink)}
.stApp{
  background:
    radial-gradient(circle at 8% -6%,rgba(80,155,226,.22),transparent 27%),
    radial-gradient(circle at 92% 4%,rgba(94,199,211,.15),transparent 25%),
    linear-gradient(145deg,#f8fbfe 0%,#edf3f8 48%,#f7fafc 100%);
}
.block-container{max-width:1680px;padding:1rem 1.3rem 4rem}
[data-testid="stHeader"]{background:transparent}
[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#0d2034 0%,#102b45 52%,#0b2137 100%);
  border-right:1px solid rgba(255,255,255,.07);
}
[data-testid="stSidebar"] *{color:#eaf4ff!important}
[data-testid="stSidebar"] [data-testid="stSidebarNav"]{padding-top:14px}
[data-testid="stSidebar"] a{border-radius:14px!important;margin:3px 8px!important;font-weight:720!important;padding-top:10px!important;padding-bottom:10px!important}
[data-testid="stSidebar"] a[aria-current="page"]{
  background:linear-gradient(135deg,rgba(87,170,255,.28),rgba(255,255,255,.08))!important;
  box-shadow:inset 0 0 0 1px rgba(139,205,255,.24),0 8px 22px rgba(0,0,0,.16)
}
.ade-shell{
  display:flex;justify-content:space-between;align-items:flex-end;gap:24px;
  padding:28px 30px;border-radius:28px;
  background:
    linear-gradient(135deg,rgba(255,255,255,.99),rgba(240,247,253,.96)),
    linear-gradient(90deg,rgba(47,120,214,.06),transparent);
  border:1px solid rgba(124,155,185,.22);box-shadow:var(--ade-shadow);margin-bottom:18px;
  position:relative;overflow:hidden;
}
.ade-shell:after{content:"";position:absolute;right:-70px;top:-70px;width:210px;height:210px;border-radius:50%;background:radial-gradient(circle,rgba(73,168,220,.18),transparent 68%)}
.ade-shell>div{position:relative;z-index:1}
.ade-eyebrow{font-size:11px;letter-spacing:.17em;font-weight:900;color:#3379ba;text-transform:uppercase}
.ade-shell h1{margin:7px 0 8px;font-size:38px;line-height:1.05;letter-spacing:-.048em;color:var(--ade-ink)}
.ade-shell p{margin:0;color:var(--ade-muted);font-size:14px;line-height:1.6}
.ade-shell-meta{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.ade-pill,.ade-badge{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:8px 12px;font-size:12px;font-weight:820;border:1px solid var(--ade-line);background:rgba(255,255,255,.9);color:#385872}
.ade-badge.good,.ade-badge.success{color:var(--ade-green);background:#edf9f4;border-color:#cce8dc}
.ade-badge.warn,.ade-badge.warning{color:var(--ade-amber);background:#fff6e6;border-color:#edd9af}
.ade-badge.bad,.ade-badge.error{color:var(--ade-red);background:#fff0f0;border-color:#edcccc}
.ade-badge.info{color:var(--ade-blue-deep);background:#edf5ff;border-color:#cee1f5}
.ade-section{display:flex;justify-content:space-between;align-items:end;gap:18px;margin:26px 0 12px}
.ade-section h2{font-size:21px;margin:0;letter-spacing:-.035em;color:var(--ade-ink)}
.ade-section span{color:var(--ade-muted);font-size:13px}
.ade-card,.ade-kpi,.ade-panel,.action-card,.market-card,.system-card,.flow,.ops-card{
  background:rgba(255,255,255,.94);border:1px solid var(--ade-line);border-radius:20px;box-shadow:var(--ade-shadow-soft);
}
.ade-card{padding:18px 19px}.ade-panel{padding:19px}.ade-kpi{padding:17px;min-height:116px}
.ade-kpi span,.ade-kpi small{display:block;color:var(--ade-muted)}
.ade-kpi strong{display:block;margin:9px 0 5px;font-size:28px;letter-spacing:-.045em;color:var(--ade-ink)}
.ade-card h3,.ade-panel h3{margin:0 0 8px;font-size:17px}.ade-card p,.ade-panel p{margin:5px 0;color:var(--ade-muted);font-size:13px;line-height:1.55}
.ade-step{display:flex;gap:11px;align-items:flex-start;padding:14px 15px;border:1px solid var(--ade-line);border-radius:17px;background:linear-gradient(135deg,#fff,#f1f7fc);box-shadow:var(--ade-shadow-soft)}
.ade-step>span{display:flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:11px;background:linear-gradient(135deg,var(--ade-blue),var(--ade-cyan));color:white;font-weight:900;box-shadow:0 8px 18px rgba(47,120,214,.25)}
.ade-step b{display:block;color:#145f9f;font-size:16px}.ade-step small{display:block;color:var(--ade-muted);margin-top:3px}
.ade-action{padding:16px 17px;border-radius:18px;border:1px solid var(--ade-line);background:linear-gradient(135deg,#fff,#f5f9fd);min-height:110px;box-shadow:var(--ade-shadow-soft)}
.ade-action strong{display:block;color:#1b65aa;margin-bottom:5px}.ade-action span{display:block;color:var(--ade-muted);font-size:13px}
.ade-empty{padding:24px;border-radius:19px;border:1px dashed #b8cde1;background:rgba(248,252,255,.92);color:var(--ade-muted);text-align:center}
.ade-divider{height:1px;background:var(--ade-line);margin:16px 0}
.ade-status-row{display:flex;justify-content:space-between;gap:15px;align-items:center;padding:12px 13px;border-radius:14px;background:#f8fbfd;border:1px solid var(--ade-line);margin:8px 0}
.ade-status-row span{color:var(--ade-muted);font-size:13px}
div[data-testid="stMetric"]{background:rgba(255,255,255,.95);border:1px solid var(--ade-line);padding:16px 17px;border-radius:20px;box-shadow:var(--ade-shadow-soft)}
div[data-testid="stMetricLabel"]{font-weight:740;color:var(--ade-muted)}
div[data-testid="stMetricValue"]{font-size:1.76rem;font-weight:880;color:var(--ade-ink)}
div[data-testid="stDataFrame"],div[data-testid="stPlotlyChart"]{border:1px solid var(--ade-line);border-radius:18px;overflow:hidden;background:white;box-shadow:var(--ade-shadow-soft)}
.stButton>button,.stLinkButton>a,[data-testid="stPageLink-NavLink"]{min-height:46px;border-radius:14px!important;font-weight:800!important;border:1px solid #cfdeeb!important;box-shadow:none!important}
.stButton>button:hover,.stLinkButton>a:hover,[data-testid="stPageLink-NavLink"]:hover{transform:translateY(-1px);box-shadow:0 8px 18px rgba(48,84,119,.11)!important}
[data-testid="stExpander"]{border:1px solid var(--ade-line)!important;border-radius:18px!important;background:rgba(255,255,255,.9)!important;box-shadow:var(--ade-shadow-soft)}
[data-baseweb="select"]>div,[data-baseweb="input"]>div,input,textarea{border-radius:14px!important}
[data-testid="stTabs"] [role="tablist"]{gap:7px}
[data-testid="stTabs"] button[role="tab"]{border-radius:12px;padding:0 14px}

@media(max-width:900px){
  .block-container{padding:.8rem .9rem 3rem}
  .ade-shell{display:block;padding:23px}
  .ade-shell h1{font-size:32px}
  .ade-shell-meta{justify-content:flex-start;margin-top:15px}
  .ade-section{align-items:flex-start}
}

@media(max-width:640px){
  :root{
    color-scheme:light;
    --ade-bg:#ffffff;
    --ade-panel:#ffffff;
    --ade-panel-soft:#f8fafc;
    --ade-panel-strong:#f1f5f9;
    --ade-ink:#111827;
    --ade-muted:#64748b;
    --ade-line:#dbe3ec;
    --ade-blue:#2563eb;
    --ade-blue-deep:#1d4ed8;
    --ade-cyan:#0ea5e9;
    --ade-green:#15803d;
    --ade-amber:#a16207;
    --ade-red:#b91c1c;
    --ade-shadow:none;
    --ade-shadow-soft:none;
    --background-color:#ffffff;
    --secondary-background-color:#ffffff;
    --text-color:#111827;
    --primary-color:#2563eb;
  }
  html,body,[data-testid="stAppViewContainer"],[data-testid="stMain"],.stApp,.main,.block-container{background:#fff!important;color:var(--ade-ink)!important}
  .stApp{background:#fff!important}
  [data-testid="stHeader"]{background:#fff!important;border-bottom:1px solid var(--ade-line)!important;backdrop-filter:none!important}
  [data-testid="stToolbar"],#MainMenu,footer{display:none!important}
  [data-testid="stAppViewContainer"] .main .block-container{max-width:none!important;padding:8px 12px 68px!important}
  [data-testid="stSidebar"]{background:#fff!important;border-right:1px solid var(--ade-line)!important}
  [data-testid="stSidebar"] *{color:var(--ade-ink)!important}
  [data-testid="stSidebar"] a{margin:1px 4px!important;border-radius:0!important}
  [data-testid="stSidebar"] a[aria-current="page"]{background:#eff6ff!important;box-shadow:none!important}
  h1,h2,h3,h4,h5,h6,p,label,span,small,div{letter-spacing:-.01em}
  [data-testid="stMarkdownContainer"],[data-testid="stMarkdownContainer"] p,[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] p{color:var(--ade-muted)!important;font-size:12px!important;line-height:1.45!important}
  .ade-shell{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:0 0 8px;padding:8px 0 9px;border-radius:0;background:transparent;border:0;border-bottom:1px solid var(--ade-line);box-shadow:none;overflow:visible}
  .ade-shell:after{display:none}
  .ade-shell>div:first-child{min-width:0}
  .ade-eyebrow,.ade-shell p{display:none}
  .ade-shell h1{margin:0;font-size:18px;line-height:1.2;letter-spacing:-.025em;color:var(--ade-ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .ade-shell-meta{justify-content:flex-end;align-items:center;margin:0;gap:4px;flex-wrap:nowrap}
  .ade-pill,.ade-badge{padding:3px 6px;border-radius:999px;background:#f1f5f9;border-color:#dbe3ec;color:#475569;font-size:10px;white-space:nowrap}
  .ade-badge.good,.ade-badge.success{background:#ecfdf3;border-color:#bbf7d0;color:#166534}
  .ade-badge.warn,.ade-badge.warning{background:#fffbeb;border-color:#fde68a;color:#92400e}
  .ade-badge.bad,.ade-badge.error{background:#fef2f2;border-color:#fecaca;color:#991b1b}
  .ade-badge.info{background:#eff6ff;border-color:#bfdbfe;color:#1d4ed8}
  .ade-section{display:block;margin:14px 0 6px;padding:0 0 5px;border-bottom:1px solid var(--ade-line)}
  .ade-section h2{font-size:15px;color:var(--ade-ink)}
  .ade-section span{display:none}
  .ade-step{align-items:center;gap:7px;padding:7px 0;margin:10px 0 4px;border:0;border-bottom:1px solid var(--ade-line);border-radius:0;background:transparent;box-shadow:none}
  .ade-step>span{width:20px;height:20px;border-radius:50%;font-size:10px;box-shadow:none;background:var(--ade-blue)}
  .ade-step b{font-size:14px;line-height:1.2;color:var(--ade-ink)}
  .ade-step small{display:none}
  .ade-card,.ade-kpi,.ade-panel,.action-card,.market-card,.system-card,.flow,.ops-card{
    background:transparent!important;border:0!important;border-radius:0!important;box-shadow:none!important;
    padding:10px 0!important;min-height:auto!important;margin:0!important;border-bottom:1px solid var(--ade-line)!important;
  }
  .ade-kpi span,.ade-kpi small,.ade-card p,.ade-panel p,.action-card p,.market-card p,.system-card p,.flow span,.ops-card span,.ops-card small{color:var(--ade-muted)!important;font-size:11px!important;line-height:1.35!important}
  .ade-card h3,.ade-panel h3,.action-card h3,.market-card h3,.system-card h3,.ops-card h3{font-size:14px!important;line-height:1.2!important;margin:0 0 3px!important;color:var(--ade-ink)!important}
  .ade-kpi strong{font-size:20px;color:var(--ade-ink);margin:4px 0 2px!important}
  .ade-action,.ade-empty,.ade-status-row{background:transparent!important;border:0!important;border-bottom:1px solid var(--ade-line)!important;border-radius:0!important;box-shadow:none!important;padding:10px 0!important;margin:0!important;min-height:auto!important}
  .ade-action strong{font-size:13px!important;margin-bottom:3px!important}.ade-action span,.ade-status-row span{font-size:11px!important}
  .ade-empty{font-size:11px!important;text-align:left!important}
  .ade-divider{margin:8px 0!important}
  div[data-testid="stHorizontalBlock"]{gap:8px!important}
  div[data-testid="stMetric"]{background:transparent!important;border:0!important;border-bottom:1px solid var(--ade-line)!important;border-radius:0!important;padding:10px 0!important;box-shadow:none!important}
  div[data-testid="stMetricLabel"]{color:var(--ade-muted)!important;font-size:11px!important}
  div[data-testid="stMetricValue"]{color:var(--ade-ink)!important;font-size:1.2rem!important}
  div[data-testid="stMetricDelta"]{font-size:10px!important}
  div[data-testid="stDataFrame"],div[data-testid="stPlotlyChart"]{background:#fff!important;border:1px solid var(--ade-line)!important;border-radius:0!important;box-shadow:none!important;overflow:auto!important}
  [data-testid="stDataFrame"]{max-width:100%!important}
  .stButton>button,.stLinkButton>a,[data-testid="stPageLink-NavLink"]{width:100%!important;min-height:40px!important;border-radius:8px!important;background:#fff!important;border:1px solid var(--ade-line)!important;color:var(--ade-ink)!important;font-size:13px!important;font-weight:750!important;box-shadow:none!important;padding:0 10px!important}
  .stButton>button[kind="primary"],.stLinkButton>a[kind="primary"]{background:#2563eb!important;border-color:#2563eb!important;color:#fff!important}
  [data-testid="stExpander"],[data-testid="stExpander"] details,[data-testid="stExpanderDetails"]{background:#fff!important;color:var(--ade-ink)!important}
  [data-testid="stExpander"]{border:0!important;border-bottom:1px solid var(--ade-line)!important;border-radius:0!important;box-shadow:none!important;overflow:hidden!important}
  [data-testid="stExpander"] summary{min-height:40px!important;background:#fff!important;color:var(--ade-ink)!important;padding:0!important;font-size:13px!important}
  [data-testid="stExpander"] summary *{color:var(--ade-ink)!important;font-size:13px!important}
  [data-baseweb="select"]>div,[data-baseweb="input"]>div,input,textarea{background:#fff!important;border-color:var(--ade-line)!important;color:var(--ade-ink)!important;border-radius:8px!important}
  [data-testid="stNumberInput"] label,[data-testid="stNumberInput"] p,[data-testid="stNumberInput"] span{color:#475569!important;font-size:11px!important;line-height:1.25!important}
  [data-testid="stNumberInput"] [data-baseweb="input"]>div{background:#fff!important;border-color:var(--ade-line)!important;min-height:38px!important}
  [data-testid="stNumberInput"] input{background:#fff!important;color:var(--ade-ink)!important;-webkit-text-fill-color:var(--ade-ink)!important;caret-color:var(--ade-ink)!important;font-size:13px!important;padding:0 9px!important}
  [data-testid="stNumberInput"] button{background:#fff!important;color:var(--ade-ink)!important;border-color:var(--ade-line)!important;min-width:36px!important;height:38px!important}
  [data-testid="stNumberInput"] button svg{fill:var(--ade-ink)!important;color:var(--ade-ink)!important;width:13px!important;height:13px!important}
  [data-testid="stSelectbox"],[data-testid="stMultiSelect"],[data-testid="stTextInput"],[data-testid="stTextArea"],[data-testid="stDateInput"],[data-testid="stTimeInput"],[data-testid="stFileUploader"],[data-testid="stRadio"],[data-testid="stCheckbox"]{font-size:12px!important}
  [data-baseweb="select"]>div,[data-baseweb="input"]>div{min-height:38px!important;font-size:13px!important}
  [data-testid="stSegmentedControl"] button{min-height:36px!important;font-size:12px!important;padding:0 8px!important;border-radius:8px!important}
  [data-testid="stToggle"] label,[data-testid="stCheckbox"] label,[data-testid="stRadio"] label{font-size:12px!important;line-height:1.2!important}
  [data-testid="stSlider"]{padding:5px 1px!important}
  [data-testid="stTabs"] [role="tablist"]{gap:0!important;overflow-x:auto!important;white-space:nowrap!important;border-bottom:1px solid var(--ade-line)!important}
  [data-testid="stTabs"] button[role="tab"]{min-height:36px!important;border-radius:0!important;background:#fff!important;color:#64748b!important;border:0!important;border-bottom:2px solid transparent!important;padding:0 10px!important;font-size:12px!important}
  [data-testid="stTabs"] button[role="tab"][aria-selected="true"]{background:#fff!important;color:#1d4ed8!important;border-bottom-color:#2563eb!important}
  [data-testid="stAlert"]{border-radius:0!important;background:#fff!important;border:0!important;border-left:3px solid var(--ade-blue)!important;color:var(--ade-ink)!important;padding:9px 10px!important}
  [data-testid="stAlert"] *{color:var(--ade-ink)!important;font-size:12px!important;line-height:1.35!important}
  [data-testid="stProgress"]{margin:6px 0!important}
  [data-testid="stProgress"] p{font-size:11px!important}
  [data-testid="stFileUploaderDropzone"]{min-height:72px!important;padding:10px!important;border-radius:8px!important}
  [data-testid="stFileUploaderDropzone"] *{font-size:11px!important}
  [data-testid="stForm"]{padding:0!important;border:0!important;border-radius:0!important}
  [data-testid="stFormSubmitButton"] button{min-height:40px!important}
  [data-testid="stJson"],[data-testid="stCode"]{font-size:11px!important}
  table{font-size:11px!important}
  hr{border-color:var(--ade-line)!important;margin:8px 0!important}
}
</style>
"""


def apply_design_system() -> None:
    st.markdown(BASE_CSS, unsafe_allow_html=True)


def apply_global_style(streamlit_module=None) -> None:
    target = streamlit_module or st
    target.markdown(BASE_CSS, unsafe_allow_html=True)


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


def page_hero(streamlit_module, title: str, subtitle: str, eyebrow: str = "ADE · INVESTMENT OPERATIONS", badge: str | None = None) -> None:
    target = streamlit_module or st
    meta = f'<span class="ade-pill">{html.escape(badge)}</span>' if badge else f'<span class="ade-pill">{datetime.now():%Y-%m-%d %H:%M}</span>'
    target.markdown(
        f"""
        <div class="ade-shell">
          <div>
            <div class="ade-eyebrow">{html.escape(eyebrow)}</div>
            <h1>{html.escape(title)}</h1>
            <p>{html.escape(subtitle)}</p>
          </div>
          <div class="ade-shell-meta">{meta}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section(title: str, caption: str = "") -> None:
    st.markdown(
        f'<div class="ade-section"><h2>{html.escape(title)}</h2><span>{html.escape(caption)}</span></div>',
        unsafe_allow_html=True,
    )


def section_header(streamlit_module, title: str, caption: str = "") -> None:
    target = streamlit_module or st
    target.markdown(
        f'<div class="ade-section"><h2>{html.escape(title)}</h2><span>{html.escape(caption)}</span></div>',
        unsafe_allow_html=True,
    )


def status_badge(label: str, tone: str = "neutral") -> str:
    normalized = {"success": "success", "warning": "warning", "error": "error", "danger": "error"}.get(tone, tone)
    return f'<span class="ade-badge {html.escape(normalized)}">{html.escape(label)}</span>'


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
