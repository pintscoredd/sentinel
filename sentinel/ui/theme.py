"""Global CSS and Plotly chrome for the black & white theme."""
from __future__ import annotations

import copy

import streamlit as st

from sentinel.ui.palette import (
    ACCENT, BG, BORDER, BORDER_STRONG, DOWN, FLAT, FONT, MONO, PANEL, PANEL_2, SANS,
    TEXT, TEXT_DIM, TEXT_FAINT, TEXT_MUTED, UP,
)

try:
    import plotly.graph_objects as go
except ImportError:  # pragma: no cover
    go = None


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700;800&display=swap');
:root {{
  --bg:{BG}; --panel:{PANEL}; --panel2:{PANEL_2}; --border:{BORDER}; --border2:{BORDER_STRONG};
  --text:{TEXT}; --muted:{TEXT_MUTED}; --dim:{TEXT_DIM}; --faint:{TEXT_FAINT}; --accent:{ACCENT};
  --up:{UP}; --down:{DOWN}; --flat:{FLAT};
  --font:{FONT}; --mono:{MONO}; --sans:{SANS};
}}
*, *::before, *::after {{ box-sizing: border-box; }}
html, body, .stApp, [data-testid="stAppViewContainer"] {{
  background: var(--bg) !important; color: var(--text) !important; font-family: var(--font) !important;
}}
.stApp, .stMarkdown, .stMarkdown p, label, input, textarea, button, select {{ font-family: var(--font) !important; }}
[data-testid="stHeader"] {{ background: transparent !important; height: 0 !important; }}
div[data-testid="stDecoration"], footer, #MainMenu, [data-testid="stToolbar"], [data-testid="stStatusWidget"] {{ display: none !important; }}

/* Layout */
.block-container, [data-testid="stMainBlockContainer"] {{
  padding: .6rem 1rem 3.2rem !important; max-width: 1920px !important;
}}
[data-testid="stVerticalBlock"] {{ gap: 0.5rem; }}
[data-testid="stHorizontalBlock"] {{ gap: 0.75rem; }}
[data-testid="column"], [data-testid="stColumn"] {{ min-width: 0; }}
.stMarkdown, .stMarkdown > div {{ max-width: 100%; overflow-wrap: anywhere; }}
.stMarkdown p {{ margin-bottom: 0; }}
img, iframe, svg {{ max-width: 100%; }}

/* Sidebar */
[data-testid="stSidebar"] {{ background: var(--panel) !important; border-right: 1px solid var(--border) !important; }}
[data-testid="stSidebar"] * {{ font-size: 12px; }}
[data-testid="stSidebar"] label {{ color: var(--muted) !important; }}

/* Headings */
h1, h2, h3, h4 {{ color: var(--text) !important; font-family: var(--font) !important; letter-spacing: 0 !important; text-transform: none; }}

/* Page navigation */
div[data-testid="stSegmentedControl"], div[data-testid="stButtonGroup"] {{ width: 100%; }}
div[data-testid="stButtonGroup"] button, div[data-testid="stSegmentedControl"] button {{
  background: transparent !important; color: var(--dim) !important; border: 1px solid var(--border) !important;
  border-radius:2px !important; font-size: 12px !important; font-weight: 700 !important; letter-spacing: .06em;
  transition: color .12s, background .12s, border-color .12s; text-transform: uppercase;
}}
div[data-testid="stButtonGroup"] button:hover {{ color: var(--text) !important; border-color: var(--border2) !important; }}
div[data-testid="stButtonGroup"] button[aria-checked="true"], div[data-testid="stButtonGroup"] button[kind*="Active"],
div[data-testid="stSegmentedControl"] [aria-checked="true"] {{
  background: var(--accent) !important; color: #000 !important; border-color: var(--accent) !important;
}}
div[data-testid="stButtonGroup"] button[aria-checked="true"] p,
div[data-testid="stButtonGroup"] button[kind*="Active"] p {{ color: #000 !important; }}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {{ gap: 4px; border-bottom: 1px solid var(--border) !important; }}
.stTabs [data-baseweb="tab"] {{ color: var(--dim) !important; font-weight: 600 !important; font-size: 12px !important; background: transparent !important; }}
.stTabs [aria-selected="true"] {{ color: var(--text) !important; }}
.stTabs [data-baseweb="tab-highlight"] {{ background: var(--accent) !important; }}

/* Metrics */
[data-testid="stMetric"] {{
  background: var(--panel) !important; border: 1px solid var(--border) !important;
  border-radius:2px !important; padding: 10px 12px !important;
}}
[data-testid="stMetricLabel"], [data-testid="stMetric"] label {{ color: var(--dim) !important; font-size: 11px !important; letter-spacing: .06em; text-transform: uppercase; }}
[data-testid="stMetricValue"] {{ color: var(--text) !important; font-size: 20px !important; font-weight: 600 !important; font-variant-numeric: tabular-nums; }}
[data-testid="stMetricDelta"] {{ font-size: 12px !important; }}

/* Buttons */
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {{
  background: var(--panel) !important; color: var(--text) !important; border: 1px solid var(--border2) !important;
  border-radius:2px !important; font-size: 12px !important; font-weight: 600 !important; padding: 6px 14px !important;
  transition: background .12s, color .12s;
}}
.stButton > button:hover, .stFormSubmitButton > button:hover {{ background: var(--accent) !important; color: #000 !important; border-color: var(--accent) !important; }}
.stButton > button p, .stFormSubmitButton > button p {{ font-size: 12px !important; }}

/* Inputs */
.stTextInput input, .stTextArea textarea, .stNumberInput input,
[data-baseweb="select"] > div, [data-baseweb="input"] {{
  background: var(--panel) !important; color: var(--text) !important; border-color: var(--border2) !important;
  border-radius:2px !important; font-size: 13px !important;
}}
[data-baseweb="popover"] li {{ font-size: 13px !important; }}
/* World exchange board */
.xg {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(132px,1fr)); gap:6px; }}
.xg .x {{ border:1px solid var(--border); border-radius:2px; padding:7px 10px; background:var(--panel); }}
.xg .x.open {{ border-color:rgba(63,207,142,.45); }}
.xg .x.lunch {{ border-color:var(--border2); }}
.xg .c {{ display:flex; justify-content:space-between; align-items:center; font-size:12px; font-weight:700; color:var(--text); letter-spacing:.03em; }}
.xg .s {{ font-size:10px; font-weight:700; letter-spacing:.06em; color:var(--dim); }}
.xg .open .s {{ color:var(--up); }}
.xg .m {{ font-size:11px; color:var(--dim); margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
/* Multiselect chips: primaryColor is white, so default chips are white-on-white. */
[data-baseweb="tag"], [data-testid="stMultiSelect"] [data-tag] {{ background: #1C1C1C !important; border: 1px solid var(--border2) !important; border-radius:2px !important; }}
[data-baseweb="tag"] span, [data-testid="stMultiSelect"] [data-tag] span, [data-testid="stMultiSelect"] [data-tag] button {{ color: var(--text) !important; }}
.stSlider [data-baseweb="slider"] div[role="slider"] {{ background: var(--accent) !important; border-color: var(--accent) !important; }}
[data-testid="stExpander"] {{ border: 1px solid var(--border) !important; border-radius:2px !important; background: var(--panel) !important; }}
[data-testid="stExpander"] summary {{ color: var(--text) !important; }}
[data-testid="stAlert"] {{ border-radius:2px !important; }}

/* Scrollbar */
::-webkit-scrollbar {{ width: 6px; height: 6px; }}
::-webkit-scrollbar-track {{ background: var(--bg); }}
::-webkit-scrollbar-thumb {{ background: var(--border2); border-radius: 3px; }}


/* ── Terminal chrome ── */
.t-bar {{ display:grid; grid-template-columns:auto 1fr auto; align-items:center; gap:14px; border:1px solid var(--border2);
  background:var(--panel); padding:6px 10px; font-size:12px; }}
.t-left {{ display:flex; align-items:center; gap:12px; white-space:nowrap; }}
.t-brand {{ font-weight:800; letter-spacing:.22em; color:#000; background:var(--accent); padding:2px 8px; font-size:13px; }}
.t-cursor {{ animation: tBlink 1.1s steps(1) infinite; margin-left:2px; }}
@keyframes tBlink {{ 50% {{ opacity:0; }} }}
.t-stat {{ display:inline-flex; align-items:center; gap:6px; color:var(--muted); font-weight:700; letter-spacing:.08em; font-size:11px; }}
.t-tape {{ overflow:hidden; white-space:nowrap; mask-image:linear-gradient(90deg,transparent,#000 4%,#000 96%,transparent); }}
.tape-track {{ display:inline-block; animation: tTape 70s linear infinite; }}
.t-tape:hover .tape-track {{ animation-play-state: paused; }}
@keyframes tTape {{ from {{ transform:translateX(0); }} to {{ transform:translateX(-50%); }} }}
.ti {{ margin-right:26px; color:var(--muted); font-variant-numeric:tabular-nums; }}
.ti b {{ color:var(--text); margin-right:4px; }}
.t-clocks {{ display:flex; gap:12px; color:var(--dim); font-size:11px; white-space:nowrap; }}
.t-clocks b {{ color:var(--text); font-weight:600; font-variant-numeric:tabular-nums; }}
.st-key-cmdbar {{ margin-top:-2px; }}
.st-key-cmdbar [data-testid="stForm"] {{ padding:0 !important; border:0 !important; }}
.st-key-cmdbar input {{ background:#000 !important; border:1px solid var(--border2) !important; color:var(--accent) !important;
  font-family:var(--font) !important; font-size:13px !important; letter-spacing:.03em; caret-color:var(--accent); }}
.st-key-cmdbar input:focus {{ border-color:var(--accent) !important; box-shadow:none !important; }}
.st-key-cmdbar input::placeholder {{ color:#5c5c5c !important; }}
.st-key-cmdbar [data-baseweb="input"] {{ border:0 !important; background:#000 !important; }}
.st-key-cmdbar button {{ background:var(--accent) !important; color:#000 !important; font-weight:800 !important; letter-spacing:.1em; }}
.st-key-cmdbar button p {{ color:#000 !important; font-weight:800 !important; }}
.st-key-cmdbar [data-testid="InputInstructions"] {{ display:none !important; }}
.t-msg {{ color:var(--down); font-size:12px; margin-top:-4px; }}
.t-help {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:2px 18px; border:1px solid var(--border2);
  background:var(--panel); padding:10px 12px; font-size:12px; }}
.t-help div {{ display:flex; gap:12px; }} .t-help b {{ color:var(--accent); min-width:150px; }}
.t-help span {{ color:var(--muted); }} .t-help .hint {{ grid-column:1/-1; color:var(--dim); margin-top:6px; }}
.st-key-main_nav_wrap button {{ min-height:30px !important; padding:2px 6px !important; }}
.st-key-hotkeys, .st-key-hotkeys iframe {{ height:0 !important; min-height:0 !important; margin:0 !important; overflow:hidden; }}
.t-foot {{ position:fixed; left:0; right:0; bottom:0; z-index:99; display:flex; gap:24px; align-items:center;
  background:var(--accent); color:#000; font-size:11px; font-weight:700; letter-spacing:.08em; padding:4px 14px; }}
.t-foot b {{ background:#000; color:var(--accent); padding:0 6px; }}
.t-foot-r {{ margin-left:auto; }}
@media (max-width: 900px) {{
  .t-bar {{ grid-template-columns:1fr; }} .t-clocks {{ display:none; }}
  .t-foot span:nth-child(2) {{ display:none; }}
}}

/* ── Sentinel components ── */
.up {{ color: var(--up) !important; }} .dn {{ color: var(--down) !important; }} .flat {{ color: var(--flat) !important; }}
.num {{ font-variant-numeric: tabular-nums; font-family: var(--mono); }}
.muted {{ color: var(--muted); }} .dim {{ color: var(--dim); }}

.s-topbar {{ display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap;
  padding: 10px 14px; border:1px solid var(--border); border-radius:2px; background:var(--panel); }}
.s-brand {{ font-weight:700; letter-spacing:.18em; font-size:14px; color:var(--accent); }}
.s-pill {{ display:inline-flex; align-items:center; gap:6px; font-size:11px; font-weight:600; letter-spacing:.06em;
  padding:3px 9px; border:1px solid var(--border2); border-radius:2px; color:var(--muted); white-space:nowrap; }}
.s-dot {{ width:6px; height:6px; border-radius:50%; display:inline-block; }}

.bb-ph {{ display:flex; align-items:center; gap:8px; color:var(--text); font-size:11px; font-weight:800;
  letter-spacing:.14em; text-transform:uppercase; padding:5px 8px; margin:8px 0 6px; background:var(--panel2);
  border:1px solid var(--border); border-left:3px solid var(--accent); }}
.bb-sub {{ color:var(--dim); font-size:11px; margin:-2px 0 8px; line-height:1.5; letter-spacing:.02em; }}
.bb-divider {{ border:0; border-top:1px solid var(--border); margin:18px 0 10px; }}
.s-panel {{ background:var(--panel); border:1px solid var(--border); border-radius:2px; padding:14px 16px; }}
.s-note {{ background:var(--panel); border:1px solid var(--border); border-left:3px solid var(--border2);
  border-radius:2px; padding:10px 14px; color:var(--muted); font-size:12px; line-height:1.6; font-family:var(--sans); }}
.s-note.warn {{ border-left-color: var(--accent); color: var(--text); }}
.s-note.up {{ border-left-color: var(--up); }} .s-note.dn {{ border-left-color: var(--down); }}
.s-empty {{ color:var(--dim); font-size:12px; padding:8px 0; }}

.s-card {{ background:var(--panel); border:1px solid var(--border); border-radius:2px; padding:12px 14px;
  min-height: 86px; display:flex; flex-direction:column; justify-content:space-between; }}
.s-card-lbl {{ color:var(--dim); font-size:10.5px; font-weight:600; letter-spacing:.08em; text-transform:uppercase;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.s-card-val {{ color:var(--text); font-size:19px; font-weight:700; line-height:1.25; margin-top:4px;
  font-variant-numeric:tabular-nums; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.s-card-sub {{ font-size:12px; font-weight:500; margin-top:2px; font-variant-numeric:tabular-nums; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.s-cards {{ display:grid; gap:10px; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }}

/* Data tables: one HTML table per section (aligned + horizontally scrollable) */
.s-tbl-wrap {{ width:100%; overflow-x:auto; border:1px solid var(--border); border-radius:2px; background:var(--panel); }}
.s-tbl {{ width:100%; border-collapse:collapse; font-size:12px; font-variant-numeric:tabular-nums; }}
.s-tbl th {{ position:sticky; top:0; background:var(--panel2); color:var(--dim); font-size:10.5px; font-weight:600;
  letter-spacing:.08em; text-transform:uppercase; padding:8px 10px; text-align:right; white-space:nowrap; border-bottom:1px solid var(--border); }}
.s-tbl td {{ padding:5px 10px; text-align:right; color:var(--text); border-bottom:1px solid var(--border); white-space:nowrap; }}
.s-tbl th.l, .s-tbl td.l {{ text-align:left; }}
.s-tbl th.c, .s-tbl td.c {{ text-align:center; }}
.s-tbl th, .s-tbl td, .opt-tbl th, .opt-tbl td, .em-table th, .em-table td {{ border-left:0 !important; border-right:0 !important; }}
.s-tbl, .opt-tbl, .em-table {{ margin:0 !important; border:0 !important; }}
.s-tbl td.wrap {{ white-space:normal; min-width:220px; }}
.s-tbl tr:last-child td {{ border-bottom:0; }}
.s-tbl tbody tr:nth-child(even) td {{ background: rgba(255,255,255,.015); }}
.s-tbl tbody tr:hover td {{ background: rgba(255,255,255,.05); }}
.s-tbl tr.hl td {{ background: rgba(255,255,255,.05); }}
.s-tbl tr.sec td {{ background:var(--panel2); color:var(--muted); font-size:10.5px; font-weight:700; letter-spacing:.1em; text-transform:uppercase; }}
.s-tbl a {{ color:var(--text); text-decoration:none; }} .s-tbl a:hover {{ text-decoration:underline; }}
.s-tkr {{ font-weight:700; color:var(--accent); }}
.s-bar {{ height:6px; background:var(--panel2); border-radius:3px; overflow:hidden; min-width:60px; }}
.s-bar > div {{ height:100%; background:var(--muted); border-radius:3px; }}

/* Options chain tables */
.opt-tbl {{ width:100%; border-collapse:collapse; font-size:12px; font-variant-numeric:tabular-nums; }}
.opt-tbl th {{ background:var(--panel2); color:var(--dim); padding:6px 8px; text-align:right; font-size:10.5px;
  letter-spacing:.06em; text-transform:uppercase; border-bottom:1px solid var(--border); white-space:nowrap; }}
.opt-tbl th:first-child, .opt-tbl td:first-child {{ text-align:left; }}
.opt-tbl td {{ padding:5px 8px; text-align:right; color:var(--text); border-bottom:1px solid var(--border); white-space:nowrap; }}
.opt-tbl tr:hover td {{ background: rgba(255,255,255,.03); }}
.opt-itm td {{ background: rgba(255,255,255,.035); }}
.opt-atm td {{ background: rgba(255,255,255,.09) !important; }}
.opt-hvol {{ font-weight:700; color:var(--accent) !important; }}

/* News */
.bb-news {{ background:var(--panel); border:1px solid var(--border); border-left:3px solid var(--border2);
  border-radius:2px; padding:10px 14px; margin:6px 0; }}
.bb-news:hover {{ border-left-color: var(--accent); }}
.bb-news a, .bb-news span.t {{ color:var(--text); text-decoration:none; font-size:14px; font-weight:600; line-height:1.45; font-family:var(--sans); }}
.bb-news a:hover {{ text-decoration:underline; }}
.bb-meta {{ color:var(--dim); font-size:11px; margin-top:4px; }}

/* Polymarket */
.poly-card {{ background:var(--panel); border:1px solid var(--border); border-radius:2px; padding:12px 14px; margin:8px 0; }}
.poly-card a {{ color:var(--text); text-decoration:none; font-weight:600; font-size:13.5px; }}
.poly-card a:hover {{ text-decoration:underline; }}
.poly-status {{ font-size:10px; font-weight:700; letter-spacing:.08em; padding:2px 7px; border-radius:2px; border:1px solid var(--border2); color:var(--muted); white-space:nowrap; }}
.poly-status.active {{ color:var(--accent); border-color:var(--accent); }}

/* Insider cards */
.ins-card {{ background:var(--panel); border:1px solid var(--border); border-left:3px solid var(--border2); border-radius:2px; padding:10px 14px; margin:6px 0; }}
.ins-card.buy {{ border-left-color: var(--up); }} .ins-card.sell {{ border-left-color: var(--down); }}
.ins-name {{ color:var(--text); font-weight:700; font-size:13.5px; }}
.ins-role {{ color:var(--muted); font-size:12px; }}
.ins-buy {{ color:var(--up); font-weight:700; font-size:12px; }} .ins-sell {{ color:var(--down); font-weight:700; font-size:12px; }}
.ins-meta {{ color:var(--dim); font-size:11.5px; }}

/* Chat */
.chat-user {{ background:var(--panel2); border:1px solid var(--border2); border-radius:2px; padding:10px 14px; margin:8px 0; font-size:13px; }}
.chat-ai {{ background:var(--panel); border:1px solid var(--border); border-radius:2px; padding:12px 16px; margin:8px 0;
  font-size:13px; line-height:1.65; color:var(--text); font-family:var(--mono); white-space:normal; overflow-x:auto; }}

/* Earnings matrix */
.em-container {{ background:var(--panel); border:1px solid var(--border); border-radius:2px; padding:14px; margin:10px 0; overflow-x:auto; }}
.em-header {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:12px; }}
.em-badge {{ background:var(--accent); color:#000; padding:2px 8px; border-radius:2px; font-size:10px; font-weight:700; letter-spacing:.06em; }}
.em-grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap:16px; }}
.em-cap {{ color:var(--dim); font-size:10.5px; letter-spacing:.08em; text-transform:uppercase; margin:8px 0 6px; font-weight:600; }}
.em-table {{ width:100%; border-collapse:collapse; font-size:12px; font-variant-numeric:tabular-nums; }}
.em-table th {{ color:var(--dim); font-size:10.5px; padding:5px 8px; text-align:right; border-bottom:1px solid var(--border2); font-weight:600; }}
.em-table th:first-child, .em-table td:first-child {{ text-align:left; }}
.em-table td {{ padding:5px 8px; text-align:right; border-bottom:1px solid var(--border); color:var(--text); }}
.em-table td:first-child {{ color:var(--muted); }}
.em-table .em-annual td {{ border-top:1px solid var(--border2); font-weight:700; }}
.em-sub {{ display:block; font-size:10px; color:var(--dim); }}

/* Alert fade */
@keyframes sFade {{ 0%,70% {{ opacity:1; max-height:120px; }} 100% {{ opacity:0; max-height:0; padding:0; margin:0; border:0; }} }}
.s-fade {{ animation: sFade 4s ease-out forwards; overflow:hidden; }}

@media (max-width: 900px) {{
  .block-container, [data-testid="stMainBlockContainer"] {{ padding: .75rem .75rem 2rem !important; }}
  .s-card-val {{ font-size:17px; }}
}}
</style>
"""


def inject_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


_AXIS = dict(
    gridcolor="#161616", color=TEXT_DIM, showgrid=True, zeroline=False,
    showline=True, linecolor=BORDER, tickfont=dict(size=10, color=TEXT_DIM),
)

CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=TEXT_MUTED, family=FONT, size=11),
    xaxis=dict(_AXIS),
    yaxis=dict(_AXIS, side="right"),
    showlegend=False,
    hovermode="x unified",
    hoverlabel=dict(bgcolor="#111111", bordercolor=BORDER_STRONG, font=dict(size=12, color=TEXT, family=FONT)),
    margin=dict(l=8, r=48, t=56, b=8),
    title=dict(font=dict(size=11, color=TEXT, family=FONT), x=0, xanchor="left", y=0.98, yanchor="top", pad=dict(t=6)),
    legend=dict(font=dict(size=10, color=TEXT_MUTED), bgcolor="rgba(0,0,0,0)", orientation="h",
                x=1, xanchor="right", y=1.0, yanchor="bottom"),
)

PLOTLY_CONFIG = {"displayModeBar": False, "displaylogo": False}


def chart_layout(**overrides) -> dict:
    """A fresh copy of the base layout merged with *overrides* (nested dicts merge)."""
    base = copy.deepcopy(CHART_LAYOUT)
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k].update(v)
        else:
            base[k] = v
    return base


def dark_fig(height=300, **overrides):
    fig = go.Figure()
    fig.update_layout(**chart_layout(height=height, **overrides))
    return fig


def plot(fig, key=None, config=None):
    """st.plotly_chart with the theme's config and full-width layout."""
    st.plotly_chart(fig, width="stretch", config=config or PLOTLY_CONFIG, key=key)
