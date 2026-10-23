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


# ── Market depth (CLOB + data API, keyless) ─────────────────────────────────
_CLOB = "https://clob.polymarket.com"
_DATA = "https://data-api.polymarket.com"
_FIDELITY = {"1d": 5, "1w": 60, "1m": 240, "max": 1440}  # minutes per point


def market_tokens(market) -> list[tuple[str, str]]:
    """[(outcome label, CLOB token id)] for a Gamma market dict."""
    outs = _parse_poly_field(market.get("outcomes")) or ["Yes", "No"]
    toks = _parse_poly_field(market.get("clobTokenIds"))
    return list(zip([str(o) for o in outs], [str(t) for t in toks]))


@stale_cached_source(ttl=300, retry_ttl=60)
def poly_price_history(token_id: str, interval: str = "1w"):
    """[(unix_ts, price 0–1)] for one outcome token."""
    data = _fetch_robust_json(f"{_CLOB}/prices-history", params={
        "market": token_id, "interval": interval, "fidelity": _FIDELITY.get(interval, 60)}, timeout=12)
    hist = (data or {}).get("history", []) if isinstance(data, dict) else []
    return [(int(h["t"]), float(h["p"])) for h in hist if "t" in h and "p" in h]


@stale_cached_source(ttl=300, retry_ttl=60)
def poly_holders(condition_id: str, limit: int = 10):
    """{outcome index: [holder dicts]} — largest positions per side."""
    data = _fetch_robust_json(f"{_DATA}/holders", params={"market": condition_id, "limit": int(limit)}, timeout=12)
    out = {}
    for block in data or []:
        for h in block.get("holders", []) or []:
            out.setdefault(int(h.get("outcomeIndex", 0)), []).append({
                "name": h.get("name") or h.get("pseudonym") or (h.get("proxyWallet") or "")[:10],
                "wallet": h.get("proxyWallet", ""), "amount": _safe_float(h.get("amount"))})
    return out


@stale_cached_source(ttl=60, retry_ttl=30)
def poly_trades(condition_id: str, limit: int = 25):
    data = _fetch_robust_json(f"{_DATA}/trades", params={"market": condition_id, "limit": int(limit)}, timeout=12)
    return [{"ts": int(t.get("timestamp") or 0), "side": t.get("side", ""), "outcome": t.get("outcome", ""),
             "price": _safe_float(t.get("price")), "size": _safe_float(t.get("size")),
             "name": t.get("name") or t.get("pseudonym") or (t.get("proxyWallet") or "")[:10],
             "wallet": t.get("proxyWallet", "")} for t in (data or []) if isinstance(t, dict)]


@stale_cached_source(ttl=900, retry_ttl=120)
def poly_leaderboard(period: str = "WEEK", order: str = "PNL", limit: int = 25):
    """Top traders for DAY/WEEK/MONTH/ALL by PNL or VOL."""
    data = _fetch_robust_json(f"{_DATA}/v1/leaderboard", params={
        "timePeriod": period, "orderBy": order, "limit": int(limit)}, timeout=12)
    rows = data if isinstance(data, list) else (data or {}).get("data", []) if isinstance(data, dict) else []
    return [{"rank": int(_safe_float(r.get("rank"), 0)), "name": r.get("userName") or r.get("user_name") or "",
             "wallet": r.get("proxyWallet") or r.get("user_id") or "", "pnl": _safe_float(r.get("pnl")),
             "volume": _safe_float(r.get("vol", r.get("volume")))} for r in rows]
