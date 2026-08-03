#!/usr/bin/env python3
from __future__ import annotations

import math

import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq

_MIN_T = 1e-8
_MIN_SIGMA = 1e-6
_MAX_SIGMA = 5.0
_IV_PRICE_FLOOR = 1e-12


def _intrinsic(S, K, side="call"):
    if side == "call":
        return max(S - K, 0.0)
    return max(K - S, 0.0)


def _discounted_bounds(S, K, T, r, q, side="call"):
    df_r = math.exp(-r * T)
    df_q = math.exp(-q * T)
    fwd_s = S * df_q
    df_k = K * df_r
    if side == "call":
        lo = max(fwd_s - df_k, 0.0)
        hi = fwd_s
    else:
        lo = max(df_k - fwd_s, 0.0)
        hi = df_k
    return lo, hi


def bs_price(S, K, T, r, sigma, side="call", q=0.0):
    try:
        if S <= 0 or K <= 0:
            return 0.0
        if T <= 0:
            return _intrinsic(S, K, side)
        if sigma <= 0:
            lo, _ = _discounted_bounds(S, K, T, r, q, side)
            return lo

        sqrt_T = math.sqrt(T)
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T
        df_q = math.exp(-q * T)
        df_r = math.exp(-r * T)

        if side == "call":
            p = S * df_q * norm.cdf(d1) - K * df_r * norm.cdf(d2)
        else:
            p = K * df_r * norm.cdf(-d2) - S * df_q * norm.cdf(-d1)
        return max(p, 0.0)
    except Exception:
        return 0.0


def _expiry_greeks(S, K, side="call"):
    if S > K:
        delta = 1.0 if side == "call" else 0.0
    elif S < K:
        delta = 0.0 if side == "call" else -1.0
    else:
        delta = 0.5 if side == "call" else -0.5
    return {"delta": delta, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}


def bs_greeks_vectorized(S, K, T, r, sigma, side="call", q=0.0):
    K = np.asarray(K, dtype=np.float64)
    sigma = np.asarray(sigma, dtype=np.float64)
    shape = K.shape if K.ndim else sigma.shape

    if float(np.max(np.asarray(T))) <= _MIN_T or float(np.min(np.asarray(S))) <= 0:
        S_arr = np.broadcast_to(np.asarray(S, dtype=np.float64), shape)
        K_safe = np.maximum(K, 1e-10)
        if side == "call":
            delta = np.where(S_arr > K_safe, 1.0, np.where(S_arr < K_safe, 0.0, 0.5))
        else:
            delta = np.where(S_arr < K_safe, -1.0, np.where(S_arr > K_safe, 0.0, -0.5))
        z = np.zeros(shape, dtype=np.float64)
        return {
            "delta": np.round(delta, 4),
            "gamma": z,
            "theta": z.copy(),
            "vega": z.copy(),
            "rho": z.copy(),
        }

    K = np.maximum(K, 1e-10)
    sigma = np.maximum(sigma, _MIN_SIGMA)
    T_safe = np.maximum(np.asarray(T, dtype=np.float64), _MIN_T)
    S_safe = np.maximum(np.asarray(S, dtype=np.float64), 1e-10)

    sqrt_T = np.sqrt(T_safe)
    d1 = (np.log(S_safe / K) + (r - q + 0.5 * sigma ** 2) * T_safe) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    d1 = np.clip(d1, -50.0, 50.0)
    d2 = np.clip(d2, -50.0, 50.0)

    N_d1 = norm.cdf(d1)
    N_d2 = norm.cdf(d2)
    n_d1 = norm.pdf(d1)
    discount = np.exp(-r * T_safe)
    div_adj = np.exp(-q * T_safe)
    S_adj = S_safe * div_adj

    if side == "call":
        delta = div_adj * N_d1
        theta = (
            -(S_adj * n_d1 * sigma) / (2.0 * sqrt_T)
            + q * S_adj * N_d1
            - r * K * discount * N_d2
        ) / 365.0
        rho = K * T_safe * discount * N_d2 / 100.0
    else:
        delta = div_adj * (N_d1 - 1.0)
        theta = (
            -(S_adj * n_d1 * sigma) / (2.0 * sqrt_T)
            - q * S_adj * norm.cdf(-d1)
            + r * K * discount * norm.cdf(-d2)
        ) / 365.0
        rho = -K * T_safe * discount * norm.cdf(-d2) / 100.0

    gamma = div_adj * n_d1 / (S_safe * sigma * sqrt_T)
    vega = S_adj * n_d1 * sqrt_T / 100.0

    result = {
        "delta": np.round(delta, 4),
        "gamma": np.round(gamma, 6),
        "theta": np.round(theta, 4),
        "vega": np.round(vega, 4),
        "rho": np.round(rho, 4),
    }
    for key in result:
        result[key] = np.nan_to_num(result[key], nan=0.0, posinf=0.0, neginf=0.0)
    return result


def bs_greeks_engine(S, K, T, r, sigma, side="call", q=0.0):
    if S <= 0 or K <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}
    if T <= _MIN_T:
        g = _expiry_greeks(S, K, side)
        return {k: round(v, 6 if k == "gamma" else 4) for k, v in g.items()}
    if sigma <= 0:
        g = _expiry_greeks(S * math.exp(-q * T), K * math.exp(-r * T), side)
        return {k: round(v, 6 if k == "gamma" else 4) for k, v in g.items()}

    try:
        sqrt_T = math.sqrt(T)
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T
        N_d1 = norm.cdf(d1)
        N_d2 = norm.cdf(d2)
        n_d1 = norm.pdf(d1)
        discount = math.exp(-r * T)
        div_adj = math.exp(-q * T)
        S_adj = S * div_adj

        if side == "call":
            delta = div_adj * N_d1
            theta = (
                -(S_adj * n_d1 * sigma) / (2.0 * sqrt_T)
                + q * S_adj * N_d1
                - r * K * discount * N_d2
            ) / 365.0
            rho = K * T * discount * N_d2 / 100.0
        else:
            delta = div_adj * (N_d1 - 1.0)
            theta = (
                -(S_adj * n_d1 * sigma) / (2.0 * sqrt_T)
                - q * S_adj * norm.cdf(-d1)
                + r * K * discount * norm.cdf(-d2)
            ) / 365.0
            rho = -K * T * discount * norm.cdf(-d2) / 100.0

        gamma = div_adj * n_d1 / (S * sigma * sqrt_T)
        vega = S_adj * n_d1 * sqrt_T / 100.0

        return {
            "delta": float(round(delta, 4)),
            "gamma": float(round(gamma, 6)),
            "theta": float(round(theta, 4)),
            "vega": float(round(vega, 4)),
            "rho": float(round(rho, 4)),
        }
    except Exception:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}


def _bs_vega_raw(S, K, T, r, sigma, q=0.0):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrt_T)
    d1 = max(min(d1, 50.0), -50.0)
    return S * math.exp(-q * T) * norm.pdf(d1) * sqrt_T


def _iv_initial_guess(S, K, T, r, target_price, side="call", q=0.0):
    F = S * math.exp((r - q) * T)
    D = math.exp(-r * T)
    if F <= 0 or T <= 0:
        return 0.2
    try:
        if side == "put":
            c = target_price + D * (F - K)
        else:
            c = target_price
        c = max(c, _IV_PRICE_FLOOR)
        norm_c = c / (D * F) if D * F > 0 else 0.0
        norm_c = max(min(norm_c, 0.999), 1e-12)
        seed = math.sqrt(2.0 * math.pi / T) * norm_c
        log_m = abs(math.log(F / K)) if K > 0 else 0.0
        if log_m > 1e-8:
            seed = max(seed, math.sqrt(2.0 * log_m / T))
        return max(min(seed, _MAX_SIGMA), 0.01)
    except Exception:
        return 0.2


def _get_iv_brentq_fallback(S, K, T, r, target_price, side="call", q=0.0):
    if target_price <= 0 or S <= 0 or K <= 0 or T <= 0:
        return None

    lo_bound, hi_bound = _discounted_bounds(S, K, T, r, q, side)
    if target_price < lo_bound - 1e-8 or target_price > hi_bound + 1e-6 * max(S, 1.0):
        return None
    if target_price <= lo_bound + 1e-10 * max(S, 1.0):
        return float(_MIN_SIGMA)

    F = S * math.exp((r - q) * T)
    D = math.exp(-r * T)
    work_side = side
    work_price = target_price
    if side == "call" and K < F:
        work_price = target_price - D * (F - K)
        work_side = "put"
    elif side == "put" and K > F:
        work_price = target_price + D * (F - K)
        work_side = "call"
    if work_price <= max(_IV_PRICE_FLOOR, 1e-12 * S):
        return float(_MIN_SIGMA)

    def objective(sigma):
        return bs_price(S, K, T, r, sigma, work_side, q) - work_price

    try:
        lo_val = objective(_MIN_SIGMA)
        hi_val = objective(_MAX_SIGMA)
        if lo_val * hi_val > 0:
            if abs(lo_val) <= max(1e-12 * S, 1e-8 * max(work_price, 1e-8)):
                return float(_MIN_SIGMA)
            if abs(hi_val) <= max(1e-12 * S, 1e-8 * max(work_price, 1e-8)):
                return float(_MAX_SIGMA)
            return None
        iv = brentq(objective, _MIN_SIGMA, _MAX_SIGMA, xtol=1e-8, maxiter=100)
        return float(max(min(iv, _MAX_SIGMA), _MIN_SIGMA))
    except Exception:
        return None


def get_iv_newton(S, K, T, r, target_price, side="call", q=0.0):
    if S <= 0 or K <= 0 or T <= _MIN_T:
        return None
    price_floor = max(_IV_PRICE_FLOOR, 1e-12 * S)
    if target_price <= price_floor:
        return None

    lo_bound, hi_bound = _discounted_bounds(S, K, T, r, q, side)
    if target_price < lo_bound - 1e-8:
        return None
    if target_price > hi_bound + 1e-6 * max(S, 1.0):
        return None
    if target_price <= lo_bound + 1e-10 * max(S, 1.0):
        return float(_MIN_SIGMA)

    F = S * math.exp((r - q) * T)
    D = math.exp(-r * T)
    work_side = side
    work_price = target_price
    if side == "call" and K < F:
        work_price = target_price - D * (F - K)
        work_side = "put"
    elif side == "put" and K > F:
        work_price = target_price + D * (F - K)
        work_side = "call"

    if work_price <= price_floor:
        return float(_MIN_SIGMA)

    lo_w, hi_w = _discounted_bounds(S, K, T, r, q, work_side)
    if work_price < lo_w - 1e-8 or work_price > hi_w + 1e-6 * max(S, 1.0):
        return _get_iv_brentq_fallback(S, K, T, r, target_price, side, q)

    sigma = _iv_initial_guess(S, K, T, r, work_price, work_side, q)

    tol = max(1e-12 * S, 1e-8 * max(work_price, 1e-8))
    try:
        for _ in range(15):
            price = bs_price(S, K, T, r, sigma, work_side, q)
            diff = price - work_price
            if abs(diff) <= tol:
                return float(max(min(sigma, _MAX_SIGMA), _MIN_SIGMA))
            vega = _bs_vega_raw(S, K, T, r, sigma, q)
            if vega < 1e-14:
                break
            sigma -= diff / vega
            if sigma < _MIN_SIGMA:
                sigma = _MIN_SIGMA
            elif sigma > _MAX_SIGMA:
                sigma = _MAX_SIGMA
            if math.isnan(sigma):
                break
        price = bs_price(S, K, T, r, sigma, work_side, q)
        if abs(price - work_price) <= max(tol, 1e-4 * max(work_price, 1e-8)):
            return float(max(min(sigma, _MAX_SIGMA), _MIN_SIGMA))
    except Exception:
        pass

    return _get_iv_brentq_fallback(S, K, T, r, target_price, side, q)


def get_iv_explicit(S, K, T, r, target_price, side="call", q=0.0):
    return get_iv_newton(S, K, T, r, target_price, side, q)


def get_iv_brentq(S, K, T, r, target_price, side="call", q=0.0):
    return get_iv_newton(S, K, T, r, target_price, side, q)


def compute_max_pain(chain):
    if not chain:
        return None

    call_oi = {}
    put_oi = {}
    for opt in chain:
        k = opt["strike"]
        oi = opt.get("oi", 0) or 0
        if oi <= 0:
            continue
        if opt["type"] == "call":
            call_oi[k] = call_oi.get(k, 0) + oi
        else:
            put_oi[k] = put_oi.get(k, 0) + oi

    if not call_oi and not put_oi:
        return None

    strikes = sorted(set(call_oi) | set(put_oi))
    if not strikes:
        return None

    s0 = strikes[0]
    pain = 0.0
    for k, p in put_oi.items():
        if k > s0:
            pain += p * (k - s0)

    min_pain = pain
    mp_strike = s0
    cum_call = call_oi.get(s0, 0)
    total_put = sum(put_oi.values())
    cum_put = put_oi.get(s0, 0)

    for i in range(1, len(strikes)):
        gap = strikes[i] - strikes[i - 1]
        put_right = total_put - cum_put
        pain += gap * (cum_call - put_right)
        if pain < min_pain:
            min_pain = pain
            mp_strike = strikes[i]
        cum_call += call_oi.get(strikes[i], 0)
        cum_put += put_oi.get(strikes[i], 0)

    return mp_strike


def compute_pcr(chain, field="oi"):
    """Put/Call ratio from open interest (default) or volume.

    Parameters
    ----------
    chain : list[dict]
        Options with keys ``type`` and ``oi`` / ``volume``.
    field : str
        ``"oi"`` (sentiment via positioning) or ``"volume"`` (flow).
    """
    if not chain:
        return None
    call_tot = 0.0
    put_tot = 0.0
    key = "volume" if field == "volume" else "oi"
    for o in chain:
        qty = o.get(key, 0) or 0
        if o.get("type") == "call":
            call_tot += qty
        elif o.get("type") == "put":
            put_tot += qty
    if call_tot <= 0:
        return None
    return round(put_tot / call_tot, 2)


def year_fraction_to_expiry(expiry_date, now=None, close_hour_et: int = 16):
    """ACT/365 year fraction from *now* to equity option expiry (4pm ET).

    Equity options expire at the close on the expiry date. Using calendar
    days alone (and a fixed 0.5/365 for 0DTE) systematically misprices IV
    and Greeks near expiry.
    """
    from datetime import datetime, time, timezone, timedelta
    try:
        import pytz
        et = pytz.timezone("US/Eastern")
    except Exception:
        et = timezone(timedelta(hours=-5))

    if now is None:
        now = datetime.now(tz=et)
    elif getattr(now, "tzinfo", None) is None:
        now = et.localize(now) if hasattr(et, "localize") else now.replace(tzinfo=et)
    else:
        now = now.astimezone(et)

    if isinstance(expiry_date, str):
        exp_d = datetime.strptime(expiry_date[:10], "%Y-%m-%d").date()
    elif hasattr(expiry_date, "date") and not isinstance(expiry_date, datetime):
        exp_d = expiry_date
    elif isinstance(expiry_date, datetime):
        exp_d = expiry_date.date()
    else:
        exp_d = expiry_date

    exp_dt = datetime.combine(exp_d, time(close_hour_et, 0, 0))
    if hasattr(et, "localize"):
        exp_dt = et.localize(exp_dt)
    else:
        exp_dt = exp_dt.replace(tzinfo=et)

    secs = (exp_dt - now).total_seconds()
    if secs <= 0:
        return _MIN_T
    return max(secs / (365.0 * 24.0 * 3600.0), _MIN_T)


def realized_volatility(closes, window: int = 20, annualize: int = 252):
    """Annualized realized vol from close series (log returns, sample std).

    Returns float vol (e.g. 0.18 = 18%) or None if insufficient data.
    """
    if closes is None:
        return None
    arr = np.asarray(closes, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if arr.size < window + 1:
        return None
    log_ret = np.diff(np.log(arr[-(window + 1):]))
    if log_ret.size < 2:
        return None
    # ddof=1 sample stdev is standard for historical vol estimates
    return float(np.std(log_ret, ddof=1) * math.sqrt(annualize))


def rsi(closes, period: int = 14):
    """Wilder RSI (industry-standard smoothing, not plain SMA)."""
    arr = np.asarray(closes, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if arr.size < period + 1:
        return None
    deltas = np.diff(arr)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss <= 1e-15:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def macd(closes, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD line, signal line, histogram from close prices."""
    s = np.asarray(closes, dtype=np.float64)
    s = s[np.isfinite(s)]
    if s.size < slow + signal:
        return None, None, None
    # Use pandas-free EMA
    def _ema(x, span):
        alpha = 2.0 / (span + 1.0)
        out = np.empty_like(x)
        out[0] = x[0]
        for i in range(1, len(x)):
            out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
        return out
    ema_fast = _ema(s, fast)
    ema_slow = _ema(s, slow)
    line = ema_fast - ema_slow
    sig = _ema(line, signal)
    hist = line - sig
    return float(line[-1]), float(sig[-1]), float(hist[-1])
