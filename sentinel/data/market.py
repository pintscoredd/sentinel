"""Quotes, market status, sector/movers, global indices."""
from __future__ import annotations

import logging
import math
from datetime import datetime, time as dtime

import numpy as np
import pandas as pd
import pytz
import streamlit as st

from sentinel.core.http import (
    get_yf_ticker, _yf_semaphore, yf,
)
from sentinel.core.formatting import _safe_float

from sentinel.config import GLOBAL_INDICES, TRADING_DAYS_PER_YEAR, TZ_EASTERN


try:
    import pandas_market_calendars as mcal
except ImportError:  # pragma: no cover
    mcal = None

logger = logging.getLogger("sentinel.data")


@st.cache_resource
def _nyse_calendar():
    """Load NYSE calendar once per process — mcal.get_calendar is expensive."""
    if mcal is None:
        return None
    return mcal.get_calendar("NYSE")


@st.cache_data(ttl=30)
def is_market_open():
    """US equity session status (NYSE calendar). Cached 30s — was ~0.5–2.5s uncached."""
    try:
        ET = TZ_EASTERN
        now = datetime.now(ET)
        day = now.date()
        t = now.time()
        wd = now.weekday()

        nyse = _nyse_calendar()
        if nyse is not None:
            schedule = nyse.schedule(start_date=day, end_date=day)
            if schedule.empty:
                if wd == 6 and t >= dtime(18, 0):
                    return "FUTURES OPEN", "#BDBDBD", "US Equities Closed, Futures Live"
                return "CLOSED", "#F2555A", "Weekend / Holiday"
            market_open = schedule.iloc[0]["market_open"].astimezone(ET).time()
            market_close = schedule.iloc[0]["market_close"].astimezone(ET).time()
        else:
            # Fallback without pandas_market_calendars (weekends only; ignores holidays)
            if wd >= 5:
                if wd == 6 and t >= dtime(18, 0):
                    return "FUTURES OPEN", "#BDBDBD", "US Equities Closed, Futures Live"
                return "CLOSED", "#F2555A", "Weekend / Holiday"
            market_open, market_close = dtime(9, 30), dtime(16, 0)

        if market_open <= t <= market_close:
            return "OPEN", "#3FCF8E", "Regular Hours"
        if dtime(4, 0) <= t < market_open:
            return "PRE-MARKET", "#BDBDBD", "Pre-Market"
        if market_close < t <= dtime(20, 0):
            return "AFTER-HOURS", "#BDBDBD", "After-Hours"
        return "CLOSED", "#F2555A", "Markets Closed"
    except Exception as e:
        logger.error("is_market_open fallback: %s", e)
        return "UNKNOWN", "#6E6E6E", "Status Unknown"


def is_0dte_market_open():
    """Check if within regular US equity hours for Alpaca."""
    status, _, _ = is_market_open()
    if status == "OPEN":
        return True, "Market OPEN"
    return False, f"Market {status}"


_TICKER_ALIASES = {"DXY": "DX-Y.NYB", "$DXY": "DX-Y.NYB"}


_YIELD_TICKERS = frozenset({"^TNX", "^TYX", "^FVX", "^IRX", "^VIX"})


def _resolve_ticker(ticker: str) -> tuple[str, str]:
    """Return (display_key, yfinance_symbol)."""
    raw = (ticker or "").strip()
    if not raw:
        return "", ""
    up = raw.upper()
    yf_sym = _TICKER_ALIASES.get(up, _TICKER_ALIASES.get(raw, raw))
    return raw, yf_sym


def _quote_decimals(yf_sym: str, price: float) -> int:
    if yf_sym in _YIELD_TICKERS or (yf_sym.startswith("^") and yf_sym in _YIELD_TICKERS):
        return 3
    if abs(price) < 1 and not yf_sym.startswith("^"):
        return 4
    return 2


def _build_quote(display: str, yf_sym: str, price, prev, vol=0,
                 day_open=None, day_high=None, day_low=None):
    """Assemble standard quote dict from raw levels."""
    if price is None or not math.isfinite(float(price)):
        return None
    price = float(price)
    if prev is None or not math.isfinite(float(prev)) or float(prev) == 0:
        prev = price
    else:
        prev = float(prev)
    chg = price - prev
    pct = (chg / prev * 100.0) if prev else 0.0
    d = _quote_decimals(yf_sym, price)
    out = {
        "ticker": display or yf_sym,
        "price": round(price, d),
        "change": round(chg, d),
        "pct": round(pct, 2),
        "volume": int(vol or 0),
        "prev_close": round(prev, d),
    }
    if day_open is not None and math.isfinite(float(day_open)):
        out["open"] = round(float(day_open), d)
    if day_high is not None and math.isfinite(float(day_high)):
        out["high"] = round(float(day_high), d)
    if day_low is not None and math.isfinite(float(day_low)):
        out["low"] = round(float(day_low), d)
    return out


def _extract_ohlcv_frames(data: "pd.DataFrame", symbols: list[str]):
    """Normalize yf.download MultiIndex into {sym: {Close,Volume,Open,High,Low} Series}.

    Handles both group_by='column' (field, ticker) and group_by='ticker' layouts.
    """
    out = {}
    if data is None or getattr(data, "empty", True):
        return out

    if not isinstance(data.columns, pd.MultiIndex):
        # Single-ticker flat frame
        sym = symbols[0] if symbols else "TICKER"
        out[sym] = data
        return out

    level0 = [str(x) for x in data.columns.get_level_values(0)]
    # Heuristic: if level0 has OHLCV names → group_by column
    ohlcv = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}
    if any(x in ohlcv for x in level0):
        for sym in symbols:
            try:
                if "Close" in data.columns.get_level_values(0):
                    # (field, ticker)
                    cols = {}
                    for field in ("Open", "High", "Low", "Close", "Volume"):
                        if (field, sym) in data.columns:
                            cols[field] = data[(field, sym)]
                        elif field == "Close" and ("Adj Close", sym) in data.columns:
                            cols["Close"] = data[("Adj Close", sym)]
                    if "Close" in cols:
                        out[sym] = pd.DataFrame(cols)
            except Exception:
                continue
        # Also try matching by level1 unique tickers when symbols differ slightly
        if not out:
            tickers = data.columns.get_level_values(1).unique()
            for sym in tickers:
                try:
                    frame = data.xs(sym, axis=1, level=1, drop_level=True)
                    if "Close" in frame.columns or "Adj Close" in frame.columns:
                        out[str(sym)] = frame
                except Exception:
                    continue
    else:
        # group_by ticker: (ticker, field)
        for sym in symbols:
            try:
                if sym in data.columns.get_level_values(0):
                    frame = data[sym]
                    if isinstance(frame, pd.Series):
                        continue
                    out[sym] = frame
            except Exception:
                continue
    return out


def _quotes_from_batch_download(tickers: list[str]) -> dict[str, dict]:
    """One yf.download for many tickers → {display_ticker: quote_dict}.

    This is the main latency win vs N × Ticker.history calls.
    """
    if not tickers or yf is None:
        return {}

    # Map display → yf symbol (unique yf symbols for download)
    display_to_yf = {}
    yf_to_displays = {}
    for t in tickers:
        disp, yf_sym = _resolve_ticker(t)
        if not yf_sym:
            continue
        display_to_yf[disp] = yf_sym
        yf_to_displays.setdefault(yf_sym, []).append(disp)

    yf_syms = list(yf_to_displays.keys())
    if not yf_syms:
        return {}

    try:
        with _yf_semaphore:
            data = yf.download(
                yf_syms if len(yf_syms) > 1 else yf_syms[0],
                period="5d",
                progress=False,
                threads=True,
                auto_adjust=True,
                group_by="column",
                timeout=15,
            )
    except TypeError:
        # older yfinance without timeout=
        try:
            with _yf_semaphore:
                data = yf.download(
                    yf_syms if len(yf_syms) > 1 else yf_syms[0],
                    period="5d",
                    progress=False,
                    threads=True,
                    auto_adjust=True,
                    group_by="column",
                )
        except Exception as e:
            logger.debug("batch download failed: %s", e)
            return {}
    except Exception as e:
        logger.debug("batch download failed: %s", e)
        return {}

    frames = _extract_ohlcv_frames(data, yf_syms)
    # Single-ticker download returns flat columns
    if len(yf_syms) == 1 and not frames:
        if data is not None and not getattr(data, "empty", True):
            frames[yf_syms[0]] = data

    results = {}
    for yf_sym, displays in yf_to_displays.items():
        frame = frames.get(yf_sym)
        if frame is None:
            # try case-insensitive key match
            for k, v in frames.items():
                if str(k).upper() == yf_sym.upper():
                    frame = v
                    break
        if frame is None or getattr(frame, "empty", True):
            continue
        try:
            close_col = "Close" if "Close" in frame.columns else (
                "Adj Close" if "Adj Close" in frame.columns else None
            )
            if close_col is None:
                continue
            closes = frame[close_col].dropna()
            if len(closes) < 1:
                continue
            price = float(closes.iloc[-1])
            prev = float(closes.iloc[-2]) if len(closes) > 1 else price
            vol = 0
            if "Volume" in frame.columns:
                try:
                    vol = int(_safe_float(frame["Volume"].dropna().iloc[-1], 0))
                except Exception:
                    vol = 0
            o = h = l = None
            if "Open" in frame.columns:
                try:
                    o = float(frame["Open"].dropna().iloc[-1])
                except Exception:
                    pass
            if "High" in frame.columns:
                try:
                    h = float(frame["High"].dropna().iloc[-1])
                except Exception:
                    pass
            if "Low" in frame.columns:
                try:
                    l = float(frame["Low"].dropna().iloc[-1])
                except Exception:
                    pass
            for disp in displays:
                q = _build_quote(disp, yf_sym, price, prev, vol, o, h, l)
                if q:
                    results[disp] = q
        except Exception as e:
            logger.debug("batch parse %s: %s", yf_sym, e)
            continue
    return results


@st.cache_data(ttl=60)
def yahoo_quote(ticker: str):
    """Single-ticker quote. Prefer 5d history only (1 network call); fast_info fallback.

    Day change uses prior bar close (session proxy). For bulk, use multi_quotes.
    """
    disp, yf_sym = _resolve_ticker(ticker)
    if not yf_sym:
        return None
    try:
        # Fast path: tiny history window — one HTTP round-trip
        tk = get_yf_ticker(yf_sym)
        if tk is None:
            return None
        try:
            h = tk.history(period="5d", auto_adjust=True)
            if h is not None and not h.empty:
                price = float(h["Close"].iloc[-1])
                prev = float(h["Close"].iloc[-2]) if len(h) > 1 else price
                vol = int(_safe_float(h["Volume"].iloc[-1], 0)) if "Volume" in h.columns else 0
                o = float(h["Open"].iloc[-1]) if "Open" in h.columns else None
                hi = float(h["High"].iloc[-1]) if "High" in h.columns else None
                lo = float(h["Low"].iloc[-1]) if "Low" in h.columns else None
                return _build_quote(disp, yf_sym, price, prev, vol, o, hi, lo)
        except Exception as e:
            logger.debug("yahoo_quote history %s: %s", ticker, e)

        # Fallback: fast_info only if history failed
        try:
            fi = tk.fast_info
            price = _safe_float(getattr(fi, "last_price", None), None)
            prev = _safe_float(getattr(fi, "previous_close", None), None)
            vol = int(_safe_float(
                getattr(fi, "last_volume", 0) or getattr(fi, "three_month_average_volume", 0), 0
            ))
            return _build_quote(
                disp, yf_sym, price, prev, vol,
                _safe_float(getattr(fi, "open", None), None),
                _safe_float(getattr(fi, "day_high", None), None),
                _safe_float(getattr(fi, "day_low", None), None),
            )
        except Exception:
            return None
    except Exception as exc:
        logger.debug("yahoo_quote failed for %s: %s", ticker, exc)
        return None


@st.cache_data(ttl=120)
def get_futures():
    FUTURES = [
        ("ES=F", "S&P 500 Futures"), ("NQ=F", "Nasdaq 100 Futures"), ("YM=F", "Dow Jones Futures"),
        ("RTY=F", "Russell 2000 Futures"), ("ZN=F", "10-Year Treasury Bond"), ("CL=F", "WTI Crude Oil"),
        ("GC=F", "Gold Futures"), ("SI=F", "Silver Futures"), ("NG=F", "Natural Gas"),
        ("ZW=F", "Wheat Futures"), ("ZC=F", "Corn Futures"), ("DX-Y.NYB", "US Dollar Index"),
    ]
    rows = []
    try:
        tickers = [t[0] for t in FUTURES]
        batch = _quotes_from_batch_download(tickers)
        missing = [t for t in tickers if t not in batch]
        if missing:
            # sparse fallback for symbols batch missed
            for t in missing:
                q = yahoo_quote(t)
                if q:
                    batch[t] = q
        for ticker, name in FUTURES:
            q = batch.get(ticker)
            if q:
                rows.append({
                    "ticker": ticker, "name": name,
                    "price": q["price"], "change": q["change"], "pct": q["pct"],
                })
    except Exception as e:
        logger.debug("get_futures error: %s", e)
    return rows


@st.cache_data(ttl=60)
def multi_quotes(tickers):
    """Batch-fetch quotes in one yf.download (N symbols → 1 HTTP), not N histories."""
    if not tickers:
        return []
    seen = set()
    unique = []
    for t in tickers:
        if t and t not in seen:
            seen.add(t)
            unique.append(t)

    try:
        batch = _quotes_from_batch_download(unique)
        # Fill any gaps with single-ticker path (rare)
        if len(batch) < len(unique):
            for t in unique:
                if t not in batch:
                    q = yahoo_quote(t)
                    if q:
                        batch[t] = q
        # Preserve request order
        return [batch[t] for t in unique if t in batch]
    except Exception as e:
        logger.error("multi_quotes batch failed, sequential fallback: %s", e)
        ret = []
        for t in unique:
            res = yahoo_quote(t)
            if res:
                ret.append(res)
        return ret


@st.cache_data(ttl=300)
def get_spy_history():
    try:
        t = get_yf_ticker("SPY")
        return t.history(period="1y") if t else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def get_tlt_history():
    try:
        t = get_yf_ticker("TLT")
        return t.history(period="1y") if t else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def get_vix_full():
    """(VIX level, 1Y percentile rank, posture) — posture from the 1Y rank."""
    try:
        tk = get_yf_ticker("^VIX")
        if tk is None:
            return None, None, None
        h = tk.history(period="1y")
        if h is None or len(h) < 20:
            return None, None, None
        close = h["Close"].dropna()
        current = round(float(close.iloc[-1]), 2)
        pct_1y = float((close < current).mean() * 100)
        posture = "RISK-ON" if pct_1y < 30 else ("NEUTRAL" if pct_1y < 65 else "RISK-OFF")
        return current, round(pct_1y, 1), posture
    except Exception as e:
        logger.debug("get_vix_full: %s", e)
        return None, None, None


@st.cache_data(ttl=120, show_spinner=False)
def sector_etfs():
    """SPDR sector ETF day performance (one batched download)."""
    S = {"Technology": "XLK", "Financials": "XLF", "Energy": "XLE", "Healthcare": "XLV",
         "Consumer Staples": "XLP", "Utilities": "XLU", "Consumer Discretionary": "XLY", "Materials": "XLB",
         "Communication Services": "XLC", "Real Estate": "XLRE", "Industrials": "XLI"}
    name_by_tkr = {v: k for k, v in S.items()}
    quotes = multi_quotes(tuple(S.values()))
    rows = []
    for q in quotes:
        tkr = q.get("ticker", "")
        name = name_by_tkr.get(tkr, tkr)
        rows.append({"Sector": name, "ETF": tkr, "Price": q["price"], "Pct": q["pct"]})
    return pd.DataFrame(rows)


@st.cache_data(ttl=300)
def top_movers():
    """Find top gainers/losers from a universe of ~120 stocks via bulk download."""
    UNIVERSE = [
        "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AVGO","ORCL","CRM",
        "AMD","INTC","QCOM","TXN","ADI","AMAT","LRCX","KLAC","MRVL","SNPS","CDNS",
        "ADBE","INTU","NOW","PANW","CRWD","ZS","FTNT","ANSS","EPAM",
        "JPM","BAC","WFC","GS","MS","BLK","C","AXP","COF","PGR",
        "ICE","CME","SPGI","MCO","V","MA","PYPL","FIS","FISV","WEX",
        "UNH","JNJ","LLY","ABBV","MRK","TMO","ABT","PFE","DHR","BMY",
        "HD","MCD","NKE","LOW","BKNG","TJX","SBUX","MAR",
        "WMT","PG","KO","PEP","PM","MO","CL","GIS","KHC","KMB",
        "GE","RTX","CAT","HON","UNP","LMT","DE","WM","NSC","ITW",
        "XOM","CVX","COP","SLB","EOG","PSX","MPC","OXY","VLO","HAL",
        "LIN","APD","ECL","SHW","NEM","FCX","NUE","VMC","ALB","MOS",
        "PLD","AMT","CCI","EQIX","PSA","SPG","WELL","O","DLR","AVB",
        "NEE","DUK","SO","AEP","D","EXC","PCG","SRE","XEL","CEG",
    ]
    seen = set()
    UNIVERSE = [x for x in UNIVERSE if not (x in seen or seen.add(x))]

    try:
        with _yf_semaphore:
            data = yf.download(UNIVERSE, period="5d", progress=False, threads=True, auto_adjust=True)

        if isinstance(data.columns, pd.MultiIndex):
            if "Close" in data.columns.get_level_values(0):
                closes = data["Close"]
            else:
                closes = data.xs("Close", axis=1, level=0, drop_level=True)
            if "Volume" in data.columns.get_level_values(0):
                volumes = data["Volume"]
            else:
                volumes = None
        else:
            closes = data
            volumes = data["Volume"] if hasattr(data, "columns") and "Volume" in data.columns else None

        results = []
        for tkr in UNIVERSE:
            if tkr not in closes.columns:
                continue
            hist = closes[tkr].dropna()
            if len(hist) < 2:
                continue
            price = float(hist.iloc[-1])
            prev = float(hist.iloc[-2])
            chg = price - prev
            pct = (chg / prev) * 100 if prev else 0.0
            vol = 0
            if volumes is not None and tkr in volumes.columns:
                try:
                    vol = int(_safe_float(volumes[tkr].dropna().iloc[-1], 0))
                except Exception:
                    vol = 0
            results.append({
                "ticker": tkr, "price": round(price, 2),
                "change": round(chg, 2), "pct": round(pct, 2), "volume": vol,
            })

        ranked = sorted(results, key=lambda x: x["pct"], reverse=True)
        gainers = [q for q in ranked if q["pct"] > 0][:10]
        losers = [q for q in reversed(ranked) if q["pct"] < 0][:10]  # worst first
        return gainers, losers
    except Exception as e:
        logger.error("Top Movers Error: %s", e)
        return [], []


@st.cache_data(ttl=300)
def calc_stock_fear_greed():
    """5-signal Fear & Greed: VIX, Momentum, Safe Haven, PCR, Junk Demand."""
    try:
        scores = []

        vix_info = get_vix_full()
        if vix_info and vix_info[0] is not None:
            vix, pct_1y, _ = vix_info
            vix_score = 100 - pct_1y
            scores.append(("VIX", vix_score))

        try:
            h = get_spy_history().tail(130)
            if len(h) >= 125:
                current = float(h["Close"].iloc[-1])
                ma125 = float(h["Close"].tail(125).mean())
                pct_above = (current / ma125 - 1) * 100
                mom_score = max(0, min(100, 50 + pct_above * 5))
                scores.append(("Momentum", mom_score))
        except Exception as e:
            logger.debug(f"Error caught: {e}")
        try:
            tlt_hist = get_tlt_history().tail(21)
            spy_hist = get_spy_history().tail(21)
            if len(tlt_hist) >= 20 and len(spy_hist) >= 20:
                t_ret = (tlt_hist["Close"].iloc[-1] / tlt_hist["Close"].iloc[0] - 1) * 100
                s_ret = (spy_hist["Close"].iloc[-1] / spy_hist["Close"].iloc[0] - 1) * 100
                relative_20d = t_ret - s_ret
                sh_score = max(0, min(100, 50 - relative_20d * 5))
                scores.append(("SafeHaven", sh_score))
        except Exception as e:
            logger.debug(f"Error caught: {e}")
        try:
            t = get_yf_ticker("SPY")
            opts = t.options
            if opts:
                chain = t.option_chain(opts[0])
                call_vol = chain.calls["volume"].sum()
                put_vol = chain.puts["volume"].sum()
                pcr = put_vol / call_vol if call_vol > 0 else 1.0
                pcr_score = max(0, min(100, (1.5 - pcr) / 1.0 * 100))
                scores.append(("PCR", pcr_score))
        except Exception as e:
            logger.debug(f"Error caught: {e}")
        try:
            hyg = yahoo_quote("HYG")
            lqd = yahoo_quote("LQD")
            if hyg and lqd:
                spread = hyg["pct"] - lqd["pct"]
                junk_score = max(0, min(100, 50 + spread * 20))
                scores.append(("Junk", junk_score))
        except Exception as e:
            logger.debug(f"Error caught: {e}")
        if not scores:
            return None, None

        total = sum(s for _, s in scores) / len(scores)
        score = int(round(total))

        if score >= 75:   label = "Extreme Greed"
        elif score >= 55: label = "Greed"
        elif score >= 45: label = "Neutral"
        elif score >= 25: label = "Fear"
        else:             label = "Extreme Fear"

        return score, label
    except Exception:
        return None, None


@st.cache_data(ttl=60)
def market_snapshot_str():
    """Structured live tape for AI context — ET session + prior-close day changes."""
    try:
        et = TZ_EASTERN
        now_et = datetime.now(pytz.utc).astimezone(et)
        now_str = now_et.strftime("%A, %B %d, %Y %H:%M ET")
        mkt_st, _, mkt_det = is_market_open()
        tickers = ["^GSPC", "SPY", "QQQ", "IWM", "DX-Y.NYB", "GLD", "TLT",
                   "BTC-USD", "CL=F", "^VIX", "^TNX"]
        qs = multi_quotes(tickers)
        qmap = {q["ticker"]: q for q in qs} if qs else {}
        labels = {
            "^GSPC": "SPX", "DX-Y.NYB": "DXY", "BTC-USD": "BTC",
            "CL=F": "WTI", "^VIX": "VIX", "^TNX": "US10Y",
        }
        parts = []
        for t in tickers:
            q = qmap.get(t)
            if not q:
                continue
            lbl = labels.get(t, t)
            # Indices/yields: bare level; equities: $
            if t.startswith("^") or t in ("DX-Y.NYB",):
                px = f"{q['price']:,.2f}"
            else:
                px = f"${q['price']:,.2f}"
            parts.append(f"{lbl}: {px} ({q['pct']:+.2f}%)")

        vix_info = get_vix_full()
        posture = vix_info[2] if vix_info and len(vix_info) > 2 else None
        header = (
            f"CURRENT DATE/TIME: {now_str}\n"
            f"SESSION: {mkt_st} ({mkt_det})\n"
            f"LIVE MARKET DATA (vs prior regular close): " + " | ".join(parts)
        )
        if posture:
            header += f"\nVOL POSTURE: {posture}"
        return header
    except Exception:
        return ""


@st.cache_data(ttl=3600)
def get_ticker_exchange(ticker):
    EXCHANGE_MAP = {
        "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ", "NYQ": "NYSE",
        "ASE": "AMEX", "AMEX": "AMEX", "PCX": "AMEX", "PNK": "OTC", "OTC": "OTC",
        "BTT": "NYSE", "NYSEArca": "AMEX", "NasdaqCM": "NASDAQ", "NasdaqGS": "NASDAQ",
        "NasdaqGM": "NASDAQ", "NYSE": "NYSE", "NYSEMkt": "AMEX", "BATS": "BATS",
        "CBOE": "CBOE", "PINK": "OTC",
    }
    NYSE_KNOWN = {
        "JPM","BAC","WFC","GS","MS","C","AXP","V","MA","BRK-B","XOM","CVX","JNJ",
        "PG","KO","WMT","HD","UNH","MMM","IBM","GE","CAT","BA","RTX","LMT","HON",
        "DE","MCD","DIS","MO","PM","T","VZ","PFE","ABBV","BMY","MRK","LLY","ABT",
        "TMO","UNP","NSC","SHW","ECL","LIN","APD","NUE","FCX","CLF","X","DD",
        "DOW","NEM","FCX","PSX","MPC","VLO","OXY","COP","SLB","HAL","EOG","DVN",
        "PLD","AMT","CCI","PSA","SPG","O","DLR","WELL","AVB","EQR","NEE","DUK",
        "SO","AEP","D","EXC","PCG","SRE","XEL","CEG","WM","RSG","CMG","YUM",
        "DG","DLTR","TGT","KR","SYY","CLX","KMB","GIS","CPB","CAG","HRL",
    }
    if ticker.upper() in NYSE_KNOWN:
        return f"NYSE:{ticker.upper()}"
    try:
        tk = get_yf_ticker(ticker)
        info = tk.info if tk else {}
        exch = info.get("exchange", "") or info.get("fullExchangeName", "") or ""
        tv_prefix = EXCHANGE_MAP.get(exch, None)
        if tv_prefix and tv_prefix != "OTC":
            return f"{tv_prefix}:{ticker}"
        exch_lower = exch.lower()
        if "nasdaq" in exch_lower: return f"NASDAQ:{ticker}"
        if "nyse" in exch_lower or "new york" in exch_lower: return f"NYSE:{ticker}"
        if "amex" in exch_lower or "arca" in exch_lower: return f"AMEX:{ticker}"
        market = info.get("market", "")
        if market in ("us_market",):
            qt = info.get("quoteType", "")
            if qt == "EQUITY":
                clean = ticker.upper().replace("-","")
                if len(clean) >= 4 and clean.isalpha():
                    return f"NASDAQ:{ticker}"
                return f"NYSE:{ticker}"
    except Exception as e:
        logger.debug(f"Error caught: {e}")
    return f"NYSE:{ticker}"


@st.cache_data(ttl=900, show_spinner=False)
def get_global_indices():
    """Last, day change and annualized 10D/30D realized vol for world indices."""
    if yf is None:
        return pd.DataFrame()
    meta = {t: (region, name, cc) for region, items in GLOBAL_INDICES.items() for t, name, cc in items}
    tickers = list(meta)
    try:
        with _yf_semaphore:
            # 3 months of dailies: 30D vol needs >= 31 closes (35 calendar days was ~24).
            data = yf.download(tickers, period="3mo", progress=False, threads=True, auto_adjust=True)
    except Exception as e:
        logger.error("Global indices fetch failed: %s", e)
        return pd.DataFrame()
    frames = _extract_ohlcv_frames(data, tickers)
    rows = []
    for t in tickers:
        frame = frames.get(t)
        if frame is None or "Close" not in frame:
            continue
        close = frame["Close"].dropna()
        if len(close) < 2:
            continue
        cur, prev = float(close.iloc[-1]), float(close.iloc[-2])
        rets = np.log(close / close.shift(1)).dropna()

        def _vol(n):
            return float(rets.tail(n).std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100) if len(rets) >= n else None

        region, name, cc = meta[t]
        rows.append({
            "Region": region, "Flag": cc, "Index": name, "Ticker": t,
            "Value": cur, "Change": cur - prev, "% Chg": (cur / prev - 1) * 100 if prev else 0.0,
            "10D Vol": _vol(10), "30D Vol": _vol(30),
            "AsOf": close.index[-1].strftime("%b %d") if hasattr(close.index[-1], "strftime") else "",
        })
    return pd.DataFrame(rows)
