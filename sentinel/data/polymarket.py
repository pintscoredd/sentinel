"""Polymarket (Gamma API, keyless): open events/markets and a liquidity view."""
from __future__ import annotations

import logging
import math

from sentinel.core.cache import stale_cached_source
from sentinel.core.formatting import _safe_float
from sentinel.core.http import _fetch_robust_json, _json_loads

logger = logging.getLogger("sentinel.data")

_GAMMA = "https://gamma-api.polymarket.com"


@stale_cached_source(ttl=180, retry_ttl=45)
def polymarket_events(limit=60, order="volume24hr"):
    """Open events, most traded first (each event embeds its markets)."""
    data = _fetch_robust_json(f"{_GAMMA}/events", params={
        "limit": int(limit), "order": order, "ascending": "false", "active": "true", "closed": "false",
    }, timeout=12)
    return data if isinstance(data, list) else []


@stale_cached_source(ttl=180, retry_ttl=45)
def polymarket_markets(limit=100):
    """Open binary markets ordered by 24h volume."""
    data = _fetch_robust_json(f"{_GAMMA}/markets", params={
        "limit": int(limit), "order": "volume24hr", "ascending": "false", "active": "true", "closed": "false",
    }, timeout=12)
    return data if isinstance(data, list) else []


def _parse_poly_field(field):
    """Gamma returns some list fields as JSON strings."""
    if not field:
        return []
    if isinstance(field, str):
        try:
            v = _json_loads(field)
            return v if isinstance(v, list) else []
        except Exception:
            return []
    return field if isinstance(field, list) else []


def live_markets(evt):
    """Tradable sub-markets of an event.

    Polymarket pre-creates placeholder outcomes ("Team H", "Other") that are
    inactive with zero volume and a dummy 50/50 price; showing them is misleading.
    """
    out = []
    for m in evt.get("markets", []) or []:
        if m.get("closed") or m.get("active") is False:
            continue
        if _safe_float(m.get("volumeNum", m.get("volume"))) <= 0 and _safe_float(m.get("liquidityNum")) <= 0:
            continue
        out.append(m)
    return out


def _poly_liquidity_score(market):
    vol = _safe_float(market.get("volume", 0))
    liq = _safe_float(market.get("liquidity", 0))
    if vol > 1_000_000 and liq > 100_000:
        return 1.0
    if vol > 250_000 and liq > 30_000:
        return 0.8
    if vol > 50_000 and liq > 10_000:
        return 0.6
    if vol > 10_000 and liq > 2_000:
        return 0.4
    if vol > 1_000:
        return 0.2
    return 0.05


def score_poly_mispricing(markets, limit=15):
    """Rank open binary markets by how *unreliable* their quoted odds may be.

    Thin books are noisier, so the quoted YES price is shrunk toward 50% in
    proportion to liquidity ("liquidity-adjusted"). The gap is a reliability
    warning, not a forecast or a trading edge.
    """
    out = []
    for m in markets or []:
        if m.get("active") is False or _safe_float(m.get("volumeNum", m.get("volume"))) <= 0:
            continue
        title = m.get("question") or m.get("title") or ""
        prices = _parse_poly_field(m.get("outcomePrices"))
        if not title or len(prices) < 2:
            continue
        yes = _safe_float(prices[0], None)
        if yes is None or not (0 < yes < 1):
            continue
        liq = _poly_liquidity_score(m)
        reliability = 0.30 + 0.70 * liq ** 0.6
        adj = 0.5 + (yes - 0.5) * reliability
        vol, vol24 = _safe_float(m.get("volume")), _safe_float(m.get("volume24hr"))
        bid, ask = _safe_float(m.get("bestBid")), _safe_float(m.get("bestAsk"))
        spread = (ask - bid) if bid > 0 and ask > 0 else None
        gap = abs(yes - adj)
        activity = min(vol24 / vol, 1.0) if vol > 0 else 0.0
        weight = min(math.log1p(vol24) / math.log1p(1_000_000), 1.0) if vol24 > 0 else 0.0
        tier = "Deep" if liq >= 0.8 else "Medium" if liq >= 0.5 else "Thin" if liq >= 0.2 else "Illiquid"
        out.append({
            "title": title[:110], "slug": m.get("slug", ""), "event_slug": ((m.get("events") or [{}])[0] or {}).get("slug", ""),
            "yes_pct": yes * 100, "adj_pct": adj * 100, "gap_pts": gap * 100, "tier": tier,
            "spread_c": spread * 100 if spread is not None else None, "vol": vol, "vol24": vol24,
            "activity_pct": activity * 100, "score": gap * (1 + liq * activity) * weight,
            "end": (m.get("endDate") or "")[:10],
        })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:limit]
