from __future__ import annotations


def apply_premium_theme(st, *, page: str = "ADE") -> None:
    st.markdown(
        f"""
        <style>
        :root{{--ade-navy:#0a2340;--ade-blue:#2468d8;--ade-cyan:#dff2ff;--ade-ink:#17324d;--ade-muted:#6f8193;--ade-line:#dce7f1;--ade-soft:#f4f8fb;--ade-glass:rgba(255,255,255,.88);--ade-positive:#18765a;--ade-warning:#b16a18;--ade-danger:#b84646}}
        .stApp{{background:radial-gradient(circle at 86% 0%,rgba(188,226,255,.48),transparent 26%),linear-gradient(135deg,#fbfdff 0%,#f1f5f9 54%,#f9fcff 100%);color:var(--ade-ink)}}
        .block-container{{max-width:1880px;padding:1rem 1.3rem 3rem}}
        [data-testid="stSidebar"]{{background:linear-gradient(180deg,rgba(249,252,255,.98),rgba(235,244,252,.98));border-right:1px solid var(--ade-line)}}
        [data-testid="stSidebar"] a{{border-radius:12px!important;margin:2px 7px!important;font-weight:700!important;color:#334b61!important}}
        [data-testid="stSidebar"] a[aria-current="page"]{{background:linear-gradient(135deg,#dcecff,#eef6ff)!important;color:#1768bd!important;box-shadow:0 6px 18px rgba(36,104,216,.10)}}
        .ade-hero{{display:flex;justify-content:space-between;align-items:flex-end;gap:18px;padding:24px 28px;border-radius:26px;background:linear-gradient(135deg,rgba(255,255,255,.96),rgba(238,247,255,.88));border:1px solid var(--ade-line);box-shadow:0 18px 52px rgba(39,83,121,.10);margin-bottom:16px}}
        .ade-eyebrow{{font-size:11px;letter-spacing:.20em;font-weight:850;color:#4776a5}}.ade-hero h1{{margin:4px 0 6px;font-size:34px;letter-spacing:-.045em;color:var(--ade-navy)}}.ade-hero p{{margin:0;color:var(--ade-muted)}}
        .ade-chip{{padding:8px 12px;border-radius:999px;background:#e7f3ff;color:#246bb0;font-weight:850;font-size:11px;letter-spacing:.06em;white-space:nowrap}}
        .ade-section{{display:flex;justify-content:space-between;align-items:center;margin:22px 0 10px}}.ade-section h2{{margin:0;font-size:20px;letter-spacing:-.03em;color:var(--ade-navy)}}.ade-section span{{color:var(--ade-muted);font-size:12px}}
        .ade-card{{padding:17px 18px;border:1px solid var(--ade-line);border-radius:18px;background:var(--ade-glass);box-shadow:0 9px 28px rgba(44,85,122,.07)}}
        .ade-status-grid{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:1px;border:1px solid var(--ade-line);border-radius:16px;overflow:hidden;background:var(--ade-line);box-shadow:0 10px 30px rgba(24,62,98,.07);margin-bottom:14px}}.ade-status-grid>div{{padding:12px 14px;background:rgba(255,255,255,.92)}}.ade-status-grid span{{display:block;font-size:9px;letter-spacing:.14em;color:#8b9aaa;font-weight:850}}.ade-status-grid strong{{display:block;margin-top:4px;color:#18334f;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
        div[data-testid="stMetric"]{{background:rgba(255,255,255,.88);border:1px solid var(--ade-line);padding:15px 17px;border-radius:18px;box-shadow:0 9px 26px rgba(56,100,139,.07)}}
        div[data-testid="stMetricLabel"]{{font-weight:760;color:var(--ade-muted)}}div[data-testid="stMetricValue"]{{font-size:1.78rem;font-weight:900;letter-spacing:-.045em;color:#18334f}}
        div[data-testid="stDataFrame"],div[data-testid="stPlotlyChart"]{{border:1px solid var(--ade-line);border-radius:16px;overflow:hidden;background:white;box-shadow:0 9px 26px rgba(56,100,139,.06)}}
        div.stButton>button,div.stDownloadButton>button{{border-radius:12px;font-weight:800;min-height:42px;transition:.18s ease}}div.stButton>button:hover,div.stDownloadButton>button:hover{{transform:translateY(-1px);box-shadow:0 8px 22px rgba(36,104,216,.13)}}
        .ade-positive{{color:var(--ade-positive)}}.ade-warning{{color:var(--ade-warning)}}.ade-danger{{color:var(--ade-danger)}}
        @media(max-width:900px){{.block-container{{padding:.75rem}}.ade-hero{{display:block;padding:21px}}.ade-chip{{display:inline-block;margin-top:12px}}.ade-status-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero(st, title: str, subtitle: str, *, eyebrow: str = "ADE · PREMIUM TERMINAL", chip: str | None = None) -> None:
    chip_html = f'<div class="ade-chip">{chip}</div>' if chip else ""
    st.markdown(
        f"""
        <div class="ade-hero">
          <div><div class="ade-eyebrow">{eyebrow}</div><h1>{title}</h1><p>{subtitle}</p></div>
          {chip_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section(st, title: str, note: str = "") -> None:
    st.markdown(
        f'<div class="ade-section"><h2>{title}</h2><span>{note}</span></div>',
        unsafe_allow_html=True,
    )
