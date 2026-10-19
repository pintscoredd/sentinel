"""News feeds (GDELT, NewsAPI, Finnhub) and AI brief context."""
from __future__ import annotations

import logging

import streamlit as st

from sentinel.core.http import (
    _fetch_robust_json,
)
from sentinel.core.formatting import _is_english
from sentinel.core.secrets import unwrap_secret as _unwrap_secret

from sentinel.config import FINANCIAL_SOURCES as _FINANCIAL_SOURCES, FLUFF_KEYWORDS as _FLUFF_KEYWORDS, MARKET_KEYWORDS as _MARKET_KEYWORDS
from sentinel.core.cache import stale_cached_source
from sentinel.data.market import market_snapshot_str, multi_quotes

logger = logging.getLogger("sentinel.data")


@stale_cached_source(ttl=600, retry_ttl=60)
def gdelt_news(query, max_rec=15):
    """GDELT article list (last 72 h). One request; GDELT allows ~1 request / 5 s."""
    data = _fetch_robust_json("https://api.gdeltproject.org/api/v2/doc/doc", params={
        "query": f"{query} sourcelang:english", "mode": "artlist", "maxrecords": int(max_rec),
        "format": "json", "timespan": "72h", "sort": "datedesc"}, timeout=10)
    arts = (data or {}).get("articles", []) if isinstance(data, dict) else []
    return [a for a in arts if _is_english(a.get("title", ""))][:max_rec]


@st.cache_data(ttl=300)
def newsapi_headlines(key, query="stock market finance"):
    key = _unwrap_secret(key)
    if not key:
        return []
    try:
        data = _fetch_robust_json("https://newsapi.org/v2/everything",
            params={"q": query, "language": "en", "sortBy": "publishedAt", "pageSize": 10, "apiKey": key}, timeout=10)
        if not data:
            return []
        arts = data.get("articles", [])
        return arts if isinstance(arts, list) else []
    except Exception as exc:
        logger.debug(f"newsapi_headlines: {exc}")
        return []


@st.cache_data(ttl=300)
def finnhub_news(key):
    key = _unwrap_secret(key)
    if not key:
        return []
    try:
        data = _fetch_robust_json("https://finnhub.io/api/v1/news",
            params={"category": "general", "token": key}, timeout=10)
        if not isinstance(data, list):
            return []
        return data[:12]
    except Exception as exc:
        logger.debug(f"finnhub_news: {exc}")
        return []


def is_market_relevant(title, source=""):
    """Return True if a news headline is relevant to markets/geopolitics/macro.
    
    Uses a keyword-based classifier. Market-relevant titles get through;
    entertainment/lifestyle/sports fluff is filtered out.
    """
    if not title:
        return False
    t_lower = title.lower()

    for kw in _FLUFF_KEYWORDS:
        if kw in t_lower:
            return False

    for kw in _MARKET_KEYWORDS:
        if kw in t_lower:
            return True

    s_lower = (source or "").lower()
    for fs in _FINANCIAL_SOURCES:
        if fs in s_lower:
            return True

    if len(t_lower.split()) < 4:
        return False

    return True


@st.cache_data(ttl=300)
def build_brief_context(geo_watch=""):
    """Assembles the enriched context for /brief and /geo.
    
    Args:
        geo_watch: User's geo watch query string. Passed from caller
                   to avoid coupling the data layer to st.session_state.
    """
    PRIMARY_QUERY = geo_watch
    if not PRIMARY_QUERY:
        PRIMARY_QUERY = "war OR strike OR sanctions OR interest rate OR oil OR escalation OR ceasefire OR tariff"
        
    BROAD_QUERY = (
        "war OR strike OR attack OR sanctions OR geopolitical OR crisis "
        "OR central bank OR interest rate OR oil OR tariff OR embargo "
        "OR Israel OR Iran OR Hamas OR Hezbollah OR Ukraine OR Russia "
        "OR Taiwan OR China OR Red Sea OR Houthi OR Gaza OR nuclear "
        "OR missile OR airstrike OR invasion OR ceasefire OR blockade "
        "OR naval OR strait hormuz OR Persian Gulf OR Sudan OR India Pakistan"
    )

    def _fetch_geo(query):
        lines, seen = [], set()
        for a in gdelt_news(query, 20):
            title = a.get("title", "").strip()
            if not title or title in seen:
                continue
            seen.add(title)
            sd = a.get("seendate", "")
            d = f"{sd[:4]}-{sd[4:6]}-{sd[6:8]}" if len(sd) >= 8 else ""
            lines.append(f"  • [{d}] {title} ({a.get('domain', '')})")
        return lines

    base = market_snapshot_str()
    geo_headlines = _fetch_geo(PRIMARY_QUERY)
    broad_headlines = _fetch_geo(BROAD_QUERY) if len(geo_headlines) < 5 else []

    if len(geo_headlines) < 5:
        if len(broad_headlines) > len(geo_headlines):
            geo_headlines = broad_headlines

    if geo_headlines:
        headlines_block = "LIVE GEOPOLITICAL & MACRO HEADLINES (last 72h, via GDELT):\n" + "\n".join(geo_headlines[:20])
    else:
        headlines_block = "LIVE GEO HEADLINES: unavailable (GDELT timeout — use model knowledge for recent conflicts)"

    try:
        macro_qs = multi_quotes(["^TNX", "^TYX", "DX-Y.NYB", "GC=F", "TLT", "UUP", "HYG", "LQD"])
        macro_lines = []
        labels = {"^TNX": "10Y Yield", "^TYX": "30Y Yield", "DX-Y.NYB": "DXY",
                  "GC=F": "Gold", "CL=F": "WTI Crude", "TLT": "TLT (20Y Bond)",
                  "GLD": "GLD ETF", "UUP": "Dollar ETF", "HYG": "HY Credit", "LQD": "IG Credit"}
        for q in macro_qs:
            lbl = labels.get(q["ticker"], q["ticker"])
            macro_lines.append(f"  {lbl}: {q['price']:,.2f} ({q['pct']:+.2f}%)")
        macro_block = "MACRO & RATES DATA (for trade context):\n" + "\n".join(macro_lines)
    except Exception:
        macro_block = ""

    sections = [base, headlines_block]
    if macro_block: sections.append(macro_block)
    return "\n\n".join(s for s in sections if s)
