"""GEO page: 3D globe embed, live news networks, theater feed, commodity impact."""
from __future__ import annotations

import base64
import json
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pytz
import streamlit as st
import streamlit.components.v1 as components

from sentinel.config import GEO_FINANCIAL_NETWORKS, GEO_IMPACT_TICKERS, GEO_THEATERS
from sentinel.core.formatting import _esc, fmt_p
from sentinel.data.geo import (
    fetch_ais_vessels, fetch_conflict_feed, fetch_gdacs_alerts, fetch_military_aircraft_json,
    fetch_travel_advisories,
)
from sentinel.data.market import get_global_indices, multi_quotes
from sentinel.data.news import gdelt_news, newsapi_headlines
from sentinel.state import key
from sentinel.ui.components import divider, empty, gdelt_date, render_news_card, section, signed, table

_GLOBE = Path(__file__).parent / "assets" / "globe.html"


@st.cache_resource
def _globe_template() -> str:
    return _GLOBE.read_text(encoding="utf-8")


@st.cache_data(ttl=300, show_spinner=False)
def _globe_payload() -> str:
    """Server-side snapshot of keyless feeds, base64 JSON for safe injection."""
    # Satellites are propagated live in the browser (satellite.js + CelesTrak TLEs).
    jobs = {"planes": fetch_military_aircraft_json, "vessels": fetch_ais_vessels, "news": fetch_conflict_feed,
            "markets": get_global_indices, "advisories": fetch_travel_advisories, "disasters": fetch_gdacs_alerts}
    out = {}
    # Slow optional feeds get a short wait; their fetch keeps running in the background and
    # fills the cache for the next 5-minute snapshot instead of holding up the globe.
    waits = {"disasters": 12, "advisories": 15}
    pool = ThreadPoolExecutor(max_workers=6)
    futs = {k: pool.submit(fn) for k, fn in jobs.items()}
    for k, f in futs.items():
        try:
            out[k] = f.result(timeout=waits.get(k, 30))
        except Exception:
            out[k] = None
    pool.shutdown(wait=False)
    planes, vessels = (out["planes"] or [])[:400], (out["vessels"] or [])[:1200]
    markets = {}
    idx = out["markets"]
    if idx is not None and not getattr(idx, "empty", True):
        for r in idx.to_dict("records"):  # first listed index per country is the headline one
            cc = r.get("Flag")
            if cc and cc not in markets:
                markets[cc] = {"name": r["Index"], "price": r["Value"], "chg": r["% Chg"], "asof": r.get("AsOf", "")}
    data = {
        "planes": planes, "vessels": vessels, "markets": markets,
        "advisories": out["advisories"] or [], "disasters": out["disasters"] or [],
        "conflictItems": (out["news"] or {}).get("items", []),
        "conflicts": (out["news"] or {}).get("signals", []), "headlines": (out["news"] or {}).get("headlines", []),
        "meta": {"generatedAt": datetime.now(pytz.utc).isoformat(),
                 "counts": {"planes": len(planes), "vessels": len(vessels)}},
    }
    raw = json.dumps(_clean(data), default=str, ensure_ascii=True, allow_nan=False)
    return base64.b64encode(raw.encode()).decode("ascii")


def _clean(o):
    """Replace NaN/inf (pandas fills missing floats with NaN) so the JSON is valid."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def _network_html(net: dict) -> str:
    src = _esc(net["embed_url"])
    fallback = _esc(f"https://www.youtube.com/channel/{net['channel_id']}/live")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;background:#000;font:12px 'JetBrains Mono',ui-monospace,Menlo,monospace;color:#8C8C8C}}
.w{{position:relative;width:100%;padding-top:56.25%;background:#000;border:1px solid #1F1F1F;border-radius:10px;overflow:hidden}}
iframe{{position:absolute;inset:0;width:100%;height:100%;border:0}}
a{{color:#A3A3A3;text-decoration:none}}.m{{display:flex;justify-content:space-between;margin-top:6px}}</style></head>
<body><div class="w"><iframe src="{src}" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen
referrerpolicy="strict-origin-when-cross-origin"></iframe></div>
<div class="m"><span>{_esc(net['name'])} · YouTube live (muted)</span><a href="{fallback}" target="_blank" rel="noopener">Open on YouTube ↗</a></div>
</body></html>"""


def render_geo_tab():
    section("Global monitor", "3D globe · keyless public feeds, cached 5 min · click a country for profile, "
                              "a marker for details; toggle layers on the left; drag to rotate, scroll to zoom")
    with st.spinner("Loading live feeds…"):
        payload = _globe_payload()
    html = _globe_template().replace("<head>", f'<head>\n<script>window.__SENTINEL_DATA__ = JSON.parse(atob("{payload}"));</script>', 1)
    components.html(html, height=760, scrolling=False)
    st.caption("Globe: globe.gl. Sources: adsb.lol (ODbL), CelesTrak, Digitraffic AIS (Baltic), NASA EONET, USGS, "
               "GDELT, Natural Earth, Esri Dark Gray Canvas, Wikidata, World Bank. "
               "Public feeds can be delayed or incomplete — verify critical information.")

    divider()
    left, right = st.columns([3, 2], gap="large")
    with left:
        section("Theater feed", "GDELT · last 72 h")
        theater = st.selectbox("Theater", list(GEO_THEATERS) + ["Custom query…"], key="geo_theater",
                               label_visibility="collapsed")
        q = st.text_input("Query", key="geo_cq", placeholder="e.g. Panama canal drought") if theater == "Custom query…" \
            else GEO_THEATERS[theater]
        if q:
            arts = gdelt_news(q, 12)
            if arts:
                for a in arts:
                    st.markdown(render_news_card(a.get("title", ""), a.get("url"), a.get("domain", ""),
                                                 gdelt_date(a.get("seendate"))), unsafe_allow_html=True)
            else:
                empty("No GDELT articles for this query.")
            nk = key("newsapi_key")
            if nk:
                for a in [x for x in newsapi_headlines(nk, q) if "[Removed]" not in (x.get("title") or "")][:5]:
                    st.markdown(render_news_card(a.get("title", ""), a.get("url"), (a.get("source") or {}).get("name", ""),
                                                 (a.get("publishedAt") or "")[:10]), unsafe_allow_html=True)
    with right:
        section("Commodity & FX impact")
        qs = {q_["ticker"]: q_ for q_ in multi_quotes(tuple(GEO_IMPACT_TICKERS.values()))}
        rows = [[_esc(name), fmt_p(qs[t]["price"], t), signed(qs[t]["pct"], "{:+.2f}", "%", True)]
                for name, t in GEO_IMPACT_TICKERS.items() if t in qs]
        table(["Asset", "Last", "Day"], rows, empty_text="Quotes unavailable.")
        section("Live news networks")
        names = [n["name"] for n in GEO_FINANCIAL_NETWORKS]
        sel = st.selectbox("Network", names, key="geo_network_sel", label_visibility="collapsed")
        net = next(n for n in GEO_FINANCIAL_NETWORKS if n["name"] == sel)
        components.html(_network_html(net), height=300)
