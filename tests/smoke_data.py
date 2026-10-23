"""Live smoke test for every public data fetcher in ``sentinel/data``.

Calls each fetcher once with safe arguments and prints the time taken, the
result size, or the exception. Exits non-zero if any call raises or a core
feed (quotes, screener, Treasury curve, earnings week) comes back empty.
Other feeds may legitimately be empty (keyless, market closed, rate limited);
those are reported but do not fail the run.

    .venv/bin/python tests/smoke_data.py           # all checks
    .venv/bin/python tests/smoke_data.py market    # names containing "market"
    .venv/bin/python -m pytest tests/smoke_data.py # same checks under pytest

Needs network access. No API keys are used: keyed sources are called with
``None`` so the keyless fallbacks are exercised.
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from datetime import date, datetime, timedelta
from typing import Callable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Streamlit's caches warn about the missing script runtime on every call. The
# env var covers the reset Streamlit does when it parses its config lazily.
os.environ.setdefault("STREAMLIT_LOGGER_LEVEL", "error")
import streamlit.logger  # noqa: E402

streamlit.logger.set_log_level("error")

from sentinel.data import (  # noqa: E402
    breadth, cross_asset, crypto, exposure, fundamentals, funds, geo, hyperliquid, macro, market,
    news, options, polymarket, screener, sessions, zero_dte,
)


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _treasury_curve():
    today = date.today()
    df = macro.treasury_curve_year(today.year)
    # The first business days of January have no rows for the new year yet.
    if (df is None or df.empty) and today.month == 1:
        df = macro.treasury_curve_year(today.year - 1)
    return df


def _earnings_week():
    week = fundamentals.earnings_week(_monday(date.today()))
    # Thanksgiving / year-end weeks can be thin; fall back to next week.
    return week or fundamentals.earnings_week(_monday(date.today()) + timedelta(days=7))


def _screener_derived():
    df = screener.market_screener()
    return {"breadth": screener.breadth(df), "sectors": screener.sector_table(df),
            "large_caps": screener.large_caps(df), "movers": screener.movers(df)}


def _hl_summary():
    return hyperliquid.hl_summary(hyperliquid.hl_markets())


def _polymarket_scored():
    return polymarket.score_poly_mispricing(polymarket.polymarket_markets(limit=50))


def _cboe_gex():
    data = zero_dte.fetch_cboe_gex("SPX")
    if not data:
        return data
    spot, df = (data if isinstance(data, tuple) else (None, data))[:2]
    if spot is None or df is None:
        return data
    return {"profile": zero_dte.compute_cboe_gex_profile(spot, df),
            "total": zero_dte.compute_cboe_total_gex(spot, df),
            "pcr": zero_dte.compute_cboe_pcr(df)}


# (name, callable, core). Core feeds must return data; the rest may be empty.
def _poly_history():
    evts = polymarket.polymarket_events(5)
    for e in evts:
        for m in polymarket.live_markets(e):
            toks = polymarket.market_tokens(m)
            if toks:
                return polymarket.poly_price_history(toks[0][1], "1w")
    return []


CHECKS: list[tuple[str, Callable, bool]] = [
    # market
    ("market.multi_quotes", lambda: market.multi_quotes(("SPY", "QQQ", "AAPL", "^VIX", "BTC-USD")), True),
    ("market.yahoo_quote", lambda: market.yahoo_quote("AAPL"), True),
    ("market.is_market_open", market.is_market_open, False),
    ("market.get_futures", market.get_futures, False),
    ("market.get_spy_history", market.get_spy_history, False),
    ("market.get_tlt_history", market.get_tlt_history, False),
    ("market.get_vix_full", market.get_vix_full, False),
    ("market.sector_etfs", market.sector_etfs, False),
    ("market.top_movers", market.top_movers, False),
    ("market.calc_stock_fear_greed", market.calc_stock_fear_greed, False),
    ("market.market_snapshot_str", market.market_snapshot_str, False),
    ("market.get_ticker_exchange", lambda: market.get_ticker_exchange("AAPL"), False),
    ("market.get_global_indices", market.get_global_indices, False),
    # screener
    ("screener.market_screener", screener.market_screener, True),
    ("screener.derived", _screener_derived, False),
    # macro (no FRED key → Treasury.gov / BLS / NY Fed fallbacks)
    ("macro.treasury_curve_year", _treasury_curve, True),
    ("macro.fred_series DGS10", lambda: macro.fred_series("DGS10", None), False),
    ("macro.fred_series CPIAUCSL", lambda: macro.fred_series("CPIAUCSL", None), False),
    ("macro.fred_series UNRATE", lambda: macro.fred_series("UNRATE", None), False),
    ("macro.fred_series FEDFUNDS", lambda: macro.fred_series("FEDFUNDS", None), False),
    ("macro.get_risk_free_rate", lambda: macro.get_risk_free_rate(None), False),
    ("macro.get_macro_overview", lambda: macro.get_macro_overview(None), False),
    ("macro.get_macro_calendar", lambda: macro.get_macro_calendar(None), False),
    ("macro.get_net_liquidity", lambda: macro.get_net_liquidity(None), False),
    ("macro.get_yield_curve_history", lambda: macro.get_yield_curve_history(None), False),
    ("macro.get_economic_surprise_index", lambda: macro.get_economic_surprise_index(None), False),
    ("macro.get_central_bank_rates", lambda: macro.get_central_bank_rates(None), False),
    ("macro.get_yield_curve_inversions", lambda: macro.get_yield_curve_inversions(None), False),
    # fundamentals
    ("fundamentals.earnings_week", _earnings_week, True),
    ("fundamentals.nasdaq_earnings_day", lambda: fundamentals.nasdaq_earnings_day(date.today().isoformat()), False),
    ("fundamentals.get_earnings_calendar", lambda: fundamentals.get_earnings_calendar(date.today().isoformat()), False),
    ("fundamentals.get_finra_short_volume", lambda: fundamentals.get_finra_short_volume("AAPL"), False),
    ("fundamentals.get_full_financials", lambda: fundamentals.get_full_financials("AAPL"), False),
    ("fundamentals.get_earnings_matrix", lambda: fundamentals.get_earnings_matrix("AAPL"), False),
    ("fundamentals.get_profitability_metrics", lambda: fundamentals.get_profitability_metrics("AAPL"), False),
    ("fundamentals.get_balance_sheet_metrics", lambda: fundamentals.get_balance_sheet_metrics("AAPL"), False),
    # options
    ("options.options_expiries", lambda: options.options_expiries("SPY"), False),
    ("options.options_chain", lambda: options.options_chain("SPY"), False),
    ("options.get_iv_term_structure", lambda: options.get_iv_term_structure("SPY"), False),
    ("options.get_iv_skew", lambda: options.get_iv_skew("SPY"), False),
    ("options.get_rv_iv_spread", lambda: options.get_rv_iv_spread("SPY"), False),
    ("options.get_gamma_squeeze_scanner", options.get_gamma_squeeze_scanner, False),
    ("options.earnings_expected_move",
     lambda: options.earnings_expected_move("AAPL", (date.today() + timedelta(days=14)).isoformat()), False),
    # zero_dte (no Alpaca keys → snapshot/chain may be empty)
    ("zero_dte.fetch_vix_data", zero_dte.fetch_vix_data, False),
    ("zero_dte.get_spx_metrics", zero_dte.get_spx_metrics, False),
    ("zero_dte.get_stock_snapshot", lambda: zero_dte.get_stock_snapshot("SPY"), False),
    ("zero_dte.fetch_0dte_chain", lambda: zero_dte.fetch_0dte_chain("SPY"), False),
    ("zero_dte.fetch_cboe_gex", _cboe_gex, False),
    # cross_asset
    ("cross_asset.stat_arb_screener", cross_asset.stat_arb_screener, False),
    ("cross_asset.get_cross_asset_volatility", cross_asset.get_cross_asset_volatility, False),
    ("cross_asset.get_macro_correlation_matrix", cross_asset.get_macro_correlation_matrix, False),
    ("cross_asset.get_sector_rrg", cross_asset.get_sector_rrg, False),
    ("cross_asset.get_cot_positioning", cross_asset.get_cot_positioning, False),
    ("cross_asset.get_sovereign_10y_yields", lambda: cross_asset.get_sovereign_10y_yields(None), False),
    # crypto
    ("crypto.fear_greed_crypto", crypto.fear_greed_crypto, False),
    ("crypto.crypto_markets", crypto.crypto_markets, False),
    ("crypto.crypto_global", crypto.crypto_global, False),
    ("crypto.fetch_btc_etf_flows", crypto.fetch_btc_etf_flows, False),
    # hyperliquid
    ("hyperliquid.hl_perp_dexs", hyperliquid.hl_perp_dexs, False),
    ("hyperliquid.hl_markets", hyperliquid.hl_markets, False),
    ("hyperliquid.hl_summary", _hl_summary, False),
    ("hyperliquid.hl_candles", lambda: hyperliquid.hl_candles("BTC"), False),
    ("hyperliquid.hl_funding_history", lambda: hyperliquid.hl_funding_history("BTC"), False),
    ("hyperliquid.hl_order_book", lambda: hyperliquid.hl_order_book("BTC"), False),
    ("hyperliquid.hl_recent_trades", lambda: hyperliquid.hl_recent_trades("BTC"), False),
    # polymarket
    ("polymarket.polymarket_events", lambda: polymarket.polymarket_events(limit=20), False),
    ("polymarket.polymarket_markets", lambda: polymarket.polymarket_markets(limit=50), False),
    ("polymarket.score_poly_mispricing", _polymarket_scored, False),
    # news
    ("news.google_news", lambda: news.google_news("stock market"), False),
    ("news.gdelt_news", lambda: news.gdelt_news("stock market"), False),
    ("news.newsapi_headlines", lambda: news.newsapi_headlines(None), False),
    ("news.finnhub_news", lambda: news.finnhub_news(None), False),
    ("news.build_brief_context", news.build_brief_context, False),
    # geo
    ("geo.fetch_military_aircraft", geo.fetch_military_aircraft, False),
    ("geo.fetch_satellite_positions", geo.fetch_satellite_positions, False),
    ("geo.fetch_ais_vessels", geo.fetch_ais_vessels, False),
    ("geo.fetch_conflict_feed", geo.fetch_conflict_feed, False),
    # sessions
    ("sessions.exchange_status", sessions.exchange_status, False),
    # dealer exposure, crowding, breadth, 13F, Polymarket depth, country risk inputs
    ("exposure.exposure_chain[SPX]", lambda: exposure.exposure_chain("SPX")[1], False),
    ("hyperliquid.hl_cross_venue_funding", hyperliquid.hl_cross_venue_funding, False),
    ("breadth.breadth_history", breadth.breadth_history, False),
    ("funds.fund_report[Berkshire]", lambda: funds.fund_report(1067983).get("holdings"), False),
    ("polymarket.poly_leaderboard", polymarket.poly_leaderboard, False),
    ("polymarket.poly_price_history", _poly_history, False),
    ("geo.fetch_travel_advisories", geo.fetch_travel_advisories, False),
    ("geo.fetch_gdacs_alerts", geo.fetch_gdacs_alerts, False),
]


def _size(result) -> int:
    """Rows / items in *result*; 0 means empty."""
    if result is None:
        return 0
    if isinstance(result, tuple):
        return sum(_size(r) for r in result)
    if hasattr(result, "empty") and hasattr(result, "__len__"):  # DataFrame / Series
        return 0 if result.empty else len(result)
    if isinstance(result, (str, bytes, list, dict, set)):
        return len(result)
    return 1  # scalar / bool / number


def run_check(name: str, fn, core: bool) -> dict:
    streamlit.logger.set_log_level("error")  # re-apply: config parsing resets it
    t0 = time.perf_counter()
    try:
        result = fn()
    except Exception as e:
        return {"name": name, "core": core, "secs": time.perf_counter() - t0, "size": None,
                "error": f"{type(e).__name__}: {e}", "tb": traceback.format_exc()}
    return {"name": name, "core": core, "secs": time.perf_counter() - t0,
            "size": _size(result), "error": None, "kind": type(result).__name__}


def failure(r: dict) -> str | None:
    if r["error"]:
        return r["error"]
    if r["core"] and not r["size"]:
        return "core feed returned empty"
    return None


def main(argv: list[str]) -> int:
    pattern = argv[0].lower() if argv else ""
    checks = [c for c in CHECKS if pattern in c[0].lower()]
    print(f"Sentinel data smoke test — {datetime.now():%Y-%m-%d %H:%M:%S} — {len(checks)} checks\n")
    results = []
    for name, fn, core in checks:
        r = run_check(name, fn, core)
        results.append(r)
        bad = failure(r)
        status = "FAIL" if bad else ("ok" if r["size"] else "empty")
        detail = bad or f"{r['size']} ({r['kind']})"
        print(f"{status:>5}  {r['secs']:6.2f}s  {name:<42} {'*' if core else ' '} {detail}", flush=True)

    failed = [r for r in results if failure(r)]
    empty = [r for r in results if not failure(r) and not r["size"]]
    total = sum(r["secs"] for r in results)
    print(f"\n{len(results) - len(failed) - len(empty)} ok, {len(empty)} empty, {len(failed)} failed "
          f"in {total:.1f}s   (* = core feed)")
    for r in failed:
        if r.get("tb"):
            print(f"\n── {r['name']}\n{r['tb']}")
    return 1 if failed else 0


try:
    import pytest
except ImportError:  # plain-script use doesn't need pytest
    pytest = None

if pytest is not None:
    @pytest.mark.parametrize("name,fn,core", CHECKS, ids=[c[0] for c in CHECKS])
    def test_fetcher(name, fn, core):
        r = run_check(name, fn, core)
        bad = failure(r)
        assert bad is None, f"{name}: {bad}\n{r.get('tb', '')}"


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
