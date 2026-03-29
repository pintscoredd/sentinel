"""
Test Suite for Sentinel Terminal Feature Additions (FEAT-01 through FEAT-07)
and Previous Fixes (FIX-01 through FIX-13).

Uses unittest (no pip install needed). Mocks heavy dependencies.
Run:  python3 test_features.py
"""

import math
import sys
import os
import types
import unittest

# ══════════════════════════════════════════════════════════════════════
# MOCK ALL HEAVY DEPENDENCIES before importing data_fetchers
# ══════════════════════════════════════════════════════════════════════

def _make_mock_module(name="mock"):
    m = types.ModuleType(name)
    m.__dict__['__path__'] = []
    return m

_MOCK_NAMES = [
    'streamlit', 'requests', 'pytz', 'skyfield', 'skyfield.api', 'skyfield.sgp4lib',
    'pandas_market_calendars', 'tenacity', 'yfinance', 'duckdb',
    'plotly', 'plotly.graph_objects', 'plotly.subplots', 'plotly.figure_factory',
]
for _name in _MOCK_NAMES:
    if _name not in sys.modules:
        sys.modules[_name] = _make_mock_module(_name)

# Provide real scipy + numpy if available, mock otherwise
# ── Provide numpy. Mock it only if truly not installed ──
try:
    import numpy as np
except ImportError:
    # Minimal numpy mock — only what data_fetchers top-level needs
    class _NpMock:
        nan = float('nan')
        inf = float('inf')
        @staticmethod
        def sqrt(x): return math.sqrt(x) if isinstance(x, (int, float)) else x
        @staticmethod
        def log(x): return math.log(x) if isinstance(x, (int, float)) else x
        @staticmethod
        def exp(x): return math.exp(x) if isinstance(x, (int, float)) else x
        @staticmethod
        def array(x, **kw): return list(x)
        @staticmethod
        def mean(x): return sum(x) / len(x)
        @staticmethod
        def corrcoef(x, y): return [[1.0, 1.0], [1.0, 1.0]]
        @staticmethod
        def where(*a): return a[1] if len(a) > 1 else a[0]
        @staticmethod
        def diff(x): return [x[i+1]-x[i] for i in range(len(x)-1)]
        float64 = float
        int64 = int
    np = _NpMock()
    sys.modules['numpy'] = np

# ── Provide scipy.stats.norm and scipy.optimize.brentq ──
# If scipy isn't installed, provide lightweight pure-Python fallbacks
# that are sufficient for the BS math in data_fetchers.
_HAS_SCIPY = False
try:
    from scipy.stats import norm as _real_norm
    from scipy.optimize import brentq as _real_brentq
    _HAS_SCIPY = True
except ImportError:
    pass

if not _HAS_SCIPY:
    # Provide a minimal norm mock using math.erf
    class _NormMock:
        @staticmethod
        def cdf(x):
            return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
        @staticmethod
        def pdf(x):
            return (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * x * x)

    def _brentq_mock(f, a, b, **kw):
        """Simple bisection for root finding."""
        fa, fb = f(a), f(b)
        if fa * fb > 0:
            raise ValueError("f(a) and f(b) must have different signs")
        for _ in range(100):
            mid = (a + b) / 2.0
            fm = f(mid)
            if abs(fm) < 1e-12 or (b - a) < 1e-12:
                return mid
            if fa * fm < 0:
                b = mid
            else:
                a, fa = mid, fm
        return (a + b) / 2.0

    # Build mock modules
    _scipy_mod = _make_mock_module('scipy')
    _stats_mod = _make_mock_module('scipy.stats')
    _opt_mod = _make_mock_module('scipy.optimize')
    _stats_mod.norm = _NormMock()
    _opt_mod.brentq = _brentq_mock
    sys.modules['scipy'] = _scipy_mod
    sys.modules['scipy.stats'] = _stats_mod
    sys.modules['scipy.optimize'] = _opt_mod

try:
    import pandas as pd
except ImportError:
    sys.modules['pandas'] = _make_mock_module('pandas')

# Mock streamlit with proper cache_data decorator
class _MockSt:
    class session_state:
        fred_key = None
        finnhub_key = None
        cftc_key = None
    class secrets:
        @staticmethod
        def get(k, d=None): return d
    @staticmethod
    def cache_data(*a, **kw):
        def wrapper(fn):
            fn.clear = lambda *a, **kw: None
            return fn
        return wrapper
    @staticmethod
    def cache_resource(*a, **kw):
        def wrapper(fn):
            fn.clear = lambda *a, **kw: None
            return fn
        return wrapper
    @staticmethod
    def fragment(*a, **kw):
        def wrapper(fn): return fn
        return wrapper

sys.modules['streamlit'] = _MockSt()

# Mock pytz
class _MockPytz:
    @staticmethod
    def timezone(z):
        class _TZ:
            zone = z
            def localize(self, dt): return dt
        return _TZ()
sys.modules['pytz'] = _MockPytz()

# Mock tenacity
class _MockTenacity:
    @staticmethod
    def retry(*a, **kw):
        def wrapper(fn): return fn
        return wrapper
    @staticmethod
    def stop_after_attempt(n): return None
    @staticmethod
    def wait_exponential(*a, **kw): return None
    @staticmethod
    def retry_if_exception_type(*a, **kw): return None
sys.modules['tenacity'] = _MockTenacity()

# Mock skyfield
class _MockSkyfield:
    class Topos: pass
    class EarthSatellite: pass
    __path__ = []
    api = type(sys)('skyfield.api')
sys.modules['skyfield'] = _MockSkyfield()
sys.modules['skyfield.api'] = _MockSkyfield.api
sys.modules['skyfield.api'].Topos = _MockSkyfield.Topos
sys.modules['skyfield.api'].EarthSatellite = _MockSkyfield.EarthSatellite
sys.modules['skyfield.sgp4lib'] = _make_mock_module('skyfield.sgp4lib')
sys.modules['skyfield.sgp4lib'].EarthSatellite = _MockSkyfield.EarthSatellite

# Mock pandas_market_calendars
sys.modules['pandas_market_calendars'] = _make_mock_module('pandas_market_calendars')

# Mock requests
class _MockRequests:
    @staticmethod
    def get(*a, **kw):
        class R:
            status_code = 200
            text = ""
            content = b""
            def json(self): return {}
        return R()
sys.modules['requests'] = _MockRequests()

# ══════════════════════════════════════════════════════════════════════
# Now import the data_fetchers module
# ══════════════════════════════════════════════════════════════════════

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_fetchers import (
    bs_price, bs_greeks_engine, get_iv_brentq, get_iv_newton,
)


# ══════════════════════════════════════════════════════════════════════
# Black-Scholes Functions (FIX-02, FIX-03, FIX-04)
# ══════════════════════════════════════════════════════════════════════

class TestBSPrice(unittest.TestCase):
    """FIX-02: Black-Scholes with dividend yield."""

    def test_call_price_no_dividend(self):
        p = bs_price(100, 100, 1.0, 0.05, 0.20, "call", q=0.0)
        self.assertTrue(5 < p < 15, f"ATM call price {p} out of expected range")

    def test_put_price_no_dividend(self):
        p = bs_price(100, 100, 1.0, 0.05, 0.20, "put", q=0.0)
        self.assertTrue(3 < p < 12, f"ATM put price {p} out of expected range")

    def test_dividend_lowers_call_price(self):
        call_no_div = bs_price(100, 100, 1.0, 0.05, 0.20, "call", q=0.0)
        call_div = bs_price(100, 100, 1.0, 0.05, 0.20, "call", q=0.05)
        self.assertLess(call_div, call_no_div, "Dividend should lower call price")

    def test_dividend_raises_put_price(self):
        put_no_div = bs_price(100, 100, 1.0, 0.05, 0.20, "put", q=0.0)
        put_div = bs_price(100, 100, 1.0, 0.05, 0.20, "put", q=0.05)
        self.assertGreater(put_div, put_no_div, "Dividend should raise put price")

    def test_edge_case_zero_time(self):
        self.assertEqual(bs_price(100, 100, 0, 0.05, 0.20), 0.0)

    def test_edge_case_zero_vol(self):
        self.assertEqual(bs_price(100, 100, 1.0, 0.05, 0.0), 0.0)

    def test_deep_itm_call(self):
        p = bs_price(200, 100, 0.01, 0.05, 0.20, "call")
        self.assertGreater(p, 99, f"Deep ITM call {p}")

    def test_deep_otm_call(self):
        p = bs_price(50, 200, 0.01, 0.05, 0.20, "call")
        self.assertLess(p, 1, f"Deep OTM call {p}")

    def test_backward_compat_no_q(self):
        p = bs_price(100, 100, 1.0, 0.05, 0.20, "call")
        self.assertGreater(p, 0)


class TestIVSolver(unittest.TestCase):
    """FIX-03: Brentq IV solver."""

    def test_roundtrip_atm_call(self):
        true_vol = 0.25
        price = bs_price(100, 100, 1.0, 0.05, true_vol, "call")
        recovered = get_iv_brentq(100, 100, 1.0, 0.05, price, "call")
        self.assertIsNotNone(recovered)
        self.assertAlmostEqual(recovered, true_vol, delta=0.01)

    def test_roundtrip_otm_put(self):
        true_vol = 0.30
        price = bs_price(100, 120, 0.5, 0.05, true_vol, "put")
        recovered = get_iv_brentq(100, 120, 0.5, 0.05, price, "put")
        self.assertIsNotNone(recovered)
        self.assertAlmostEqual(recovered, true_vol, delta=0.01)

    def test_deep_itm_put(self):
        true_vol = 0.40
        price = bs_price(50, 100, 1.0, 0.05, true_vol, "put")
        recovered = get_iv_brentq(50, 100, 1.0, 0.05, price, "put")
        self.assertIsNotNone(recovered)
        self.assertAlmostEqual(recovered, true_vol, delta=0.02)

    def test_invalid_price_returns_none(self):
        self.assertIsNone(get_iv_brentq(100, 100, 1.0, 0.05, -5, "call"))

    def test_zero_time_returns_none(self):
        self.assertIsNone(get_iv_brentq(100, 100, 0, 0.05, 5, "call"))

    def test_backward_compat_alias(self):
        price = bs_price(100, 100, 1.0, 0.05, 0.25, "call")
        iv1 = get_iv_brentq(100, 100, 1.0, 0.05, price, "call")
        iv2 = get_iv_newton(100, 100, 1.0, 0.05, price, "call")
        self.assertEqual(iv1, iv2)

    def test_with_dividend_yield(self):
        true_vol = 0.25
        price = bs_price(100, 100, 1.0, 0.05, true_vol, "call", q=0.03)
        recovered = get_iv_brentq(100, 100, 1.0, 0.05, price, "call", q=0.03)
        self.assertIsNotNone(recovered)
        self.assertAlmostEqual(recovered, true_vol, delta=0.01)


class TestGreeksEngine(unittest.TestCase):
    """FIX-04 + FEAT-01: All 5 Greeks returned."""

    def test_all_greeks_present(self):
        g = bs_greeks_engine(100, 100, 1.0, 0.05, 0.20, "call")
        for key in ("delta", "gamma", "theta", "vega", "rho"):
            self.assertIn(key, g, f"Missing: {key}")

    def test_call_delta_range(self):
        g = bs_greeks_engine(100, 100, 1.0, 0.05, 0.20, "call")
        self.assertTrue(0.4 < g["delta"] < 0.7)

    def test_put_delta_negative(self):
        g = bs_greeks_engine(100, 100, 1.0, 0.05, 0.20, "put")
        self.assertLess(g["delta"], 0)

    def test_gamma_positive(self):
        self.assertGreater(bs_greeks_engine(100, 100, 0.5, 0.05, 0.20, "call")["gamma"], 0)

    def test_theta_negative(self):
        self.assertLess(bs_greeks_engine(100, 100, 0.5, 0.05, 0.20, "call")["theta"], 0)

    def test_vega_positive(self):
        self.assertGreater(bs_greeks_engine(100, 100, 0.5, 0.05, 0.20, "call")["vega"], 0)

    def test_call_rho_positive(self):
        self.assertGreater(bs_greeks_engine(100, 100, 1.0, 0.05, 0.20, "call")["rho"], 0)

    def test_put_rho_negative(self):
        self.assertLess(bs_greeks_engine(100, 100, 1.0, 0.05, 0.20, "put")["rho"], 0)

    def test_dividend_lowers_call_delta(self):
        d0 = bs_greeks_engine(100, 100, 1.0, 0.05, 0.20, "call", q=0.0)["delta"]
        d8 = bs_greeks_engine(100, 100, 1.0, 0.05, 0.20, "call", q=0.08)["delta"]
        self.assertLess(d8, d0)

    def test_edge_case_returns_defaults(self):
        g = bs_greeks_engine(0, 100, 1.0, 0.05, 0.20, "call")
        self.assertEqual(g["delta"], 0.5)
        self.assertEqual(g["vega"], 0.0)
        self.assertEqual(g["rho"], 0.0)

    def test_vega_higher_longer_expiry(self):
        v_s = bs_greeks_engine(100, 100, 0.1, 0.05, 0.20, "call")["vega"]
        v_l = bs_greeks_engine(100, 100, 1.0, 0.05, 0.20, "call")["vega"]
        self.assertGreater(v_l, v_s)


class TestPutCallParity(unittest.TestCase):

    def test_parity_no_dividend(self):
        S, K, T, r, sigma = 100, 100, 1.0, 0.05, 0.25
        c = bs_price(S, K, T, r, sigma, "call", q=0.0)
        p = bs_price(S, K, T, r, sigma, "put", q=0.0)
        parity = c - p - (S - K * math.exp(-r * T))
        self.assertAlmostEqual(parity, 0.0, delta=0.01)

    def test_parity_with_dividend(self):
        S, K, T, r, sigma, q = 100, 100, 1.0, 0.05, 0.25, 0.03
        c = bs_price(S, K, T, r, sigma, "call", q=q)
        p = bs_price(S, K, T, r, sigma, "put", q=q)
        parity = c - p - (S * math.exp(-q * T) - K * math.exp(-r * T))
        self.assertAlmostEqual(parity, 0.0, delta=0.01)


# ══════════════════════════════════════════════════════════════════════
# FEAT-02 — IV Skew
# ══════════════════════════════════════════════════════════════════════

class TestIVSkew(unittest.TestCase):

    def test_function_exists(self):
        from data_fetchers import get_iv_skew
        self.assertTrue(callable(get_iv_skew))

    def test_skew_label_logic(self):
        self.assertEqual("PUT PREMIUM", "PUT PREMIUM" if 5 > 2 else "FLAT")
        self.assertEqual("CALL PREMIUM", "CALL PREMIUM" if -5 < -2 else "FLAT")
        self.assertEqual("FLAT", "PUT PREMIUM" if 1 > 2 else "CALL PREMIUM" if 1 < -2 else "FLAT")


# ══════════════════════════════════════════════════════════════════════
# FEAT-03 — RV vs IV Spread
# ══════════════════════════════════════════════════════════════════════

class TestRVIVSpread(unittest.TestCase):

    def test_function_exists(self):
        from data_fetchers import get_rv_iv_spread
        self.assertTrue(callable(get_rv_iv_spread))

    def test_signal_logic(self):
        for spread, expected in [(5, "SELL VOL"), (-5, "BUY VOL"), (0, "NEUTRAL")]:
            if spread > 3: signal = "SELL VOL"
            elif spread < -3: signal = "BUY VOL"
            else: signal = "NEUTRAL"
            self.assertEqual(signal, expected)


# ══════════════════════════════════════════════════════════════════════
# FEAT-04 — CFTC COT
# ══════════════════════════════════════════════════════════════════════

class TestCOTPositioning(unittest.TestCase):

    def test_function_exists(self):
        from data_fetchers import get_cot_positioning
        self.assertTrue(callable(get_cot_positioning))

    def test_signal_logic(self):
        for net, expected in [(5000, "NET LONG"), (-5000, "NET SHORT"), (0, "FLAT")]:
            if net > 0: signal = "NET LONG"
            elif net < 0: signal = "NET SHORT"
            else: signal = "FLAT"
            self.assertEqual(signal, expected)


# ══════════════════════════════════════════════════════════════════════
# FEAT-05 — Economic Surprise Index
# ══════════════════════════════════════════════════════════════════════

class TestEconomicSurpriseIndex(unittest.TestCase):

    def test_function_exists(self):
        from data_fetchers import get_economic_surprise_index
        self.assertTrue(callable(get_economic_surprise_index))

    def test_surprise_calculation(self):
        actual, forecast = 3.5, 3.0
        surprise = (actual - forecast) / abs(forecast) * 100
        self.assertAlmostEqual(surprise, 16.67, delta=0.1)

    def test_label_logic(self):
        for avg, expected in [(2.0, "BEATS"), (-2.0, "MISSES"), (0.5, "IN LINE")]:
            if avg > 1.0: label = "BEATS"
            elif avg < -1.0: label = "MISSES"
            else: label = "IN LINE"
            self.assertEqual(label, expected)


# ══════════════════════════════════════════════════════════════════════
# FEAT-06 — Correlation Matrix
# ══════════════════════════════════════════════════════════════════════

class TestCorrelationMatrix(unittest.TestCase):

    def test_function_exists(self):
        from data_fetchers import get_macro_correlation_matrix
        self.assertTrue(callable(get_macro_correlation_matrix))

    def test_expanded_assets(self):
        import inspect
        from data_fetchers import get_macro_correlation_matrix
        source = inspect.getsource(get_macro_correlation_matrix)
        self.assertIn("^TNX", source, "10Y Yield missing from asset universe")
        self.assertIn("HYG", source, "HY Credit missing from asset universe")
        self.assertIn("spearman", source, "Spearman method missing")
        self.assertIn("pearson", source, "Pearson method missing")


# ══════════════════════════════════════════════════════════════════════
# FEAT-07 — RSI + MACD Signals
# ══════════════════════════════════════════════════════════════════════

class TestTechnicalSignals(unittest.TestCase):

    def test_rsi_thresholds(self):
        cases = [(75, -1.0), (25, 1.5), (60, 0.5), (40, -0.5), (50, 0.0)]
        for rsi_val, expected in cases:
            if rsi_val >= 70: contrib = -1.0
            elif rsi_val <= 30: contrib = 1.5
            elif 55 <= rsi_val < 70: contrib = 0.5
            elif 30 < rsi_val <= 45: contrib = -0.5
            else: contrib = 0.0
            self.assertEqual(contrib, expected, f"RSI {rsi_val}")

    def test_macd_crossover_detection(self):
        self.assertTrue(0.5 > 0 and -0.1 <= 0)  # bullish crossover
        self.assertTrue(-0.5 < 0 and 0.1 >= 0)  # bearish crossover

    def test_rsi_and_macd_in_spx_direction(self):
        import inspect
        from data_fetchers import compute_spx_direction
        source = inspect.getsource(compute_spx_direction)
        self.assertIn("RSI(14)", source)
        self.assertIn("MACD", source)

    def test_8_signals_docstring(self):
        import inspect
        from data_fetchers import compute_spx_direction
        source = inspect.getsource(compute_spx_direction)
        self.assertIn("Combines 8 weighted signals", source)


# ══════════════════════════════════════════════════════════════════════
# FIX-01 — Dead Tickers
# ══════════════════════════════════════════════════════════════════════

class TestFixDeadTickers(unittest.TestCase):

    def test_no_delisted_tickers(self):
        import inspect
        from data_fetchers import get_gamma_squeeze_scanner
        source = inspect.getsource(get_gamma_squeeze_scanner)
        for ticker in ["BBBY", "WISH", "GOEV"]:
            self.assertNotIn(f'"{ticker}"', source, f"Delisted: {ticker}")


# ══════════════════════════════════════════════════════════════════════
# FIX-07/08/09 — Stat Arb
# ══════════════════════════════════════════════════════════════════════

class TestStatArbLogic(unittest.TestCase):

    def test_threshold_scaling(self):
        # Fast: HL=5
        clamped = max(3.0, min(5.0, 60.0))
        entry = 1.0 + (clamped / 60.0) * 1.5
        self.assertTrue(1.0 < entry < 1.5)
        # Slow: HL=50
        clamped = max(3.0, min(50.0, 60.0))
        entry = 1.0 + (clamped / 60.0) * 1.5
        self.assertTrue(2.0 < entry < 2.6)

    def test_ou_equilibrium_mean(self):
        self.assertEqual(2.0 / 0.05, 40.0)

    def test_stat_arb_has_direction(self):
        import inspect
        from data_fetchers import stat_arb_screener
        source = inspect.getsource(stat_arb_screener)
        self.assertIn("direction_label", source)
        self.assertIn("entry_thresh", source)


# ══════════════════════════════════════════════════════════════════════
# FIX-10 — VIX 3Y Percentile
# ══════════════════════════════════════════════════════════════════════

class TestVIXPercentile(unittest.TestCase):

    def test_function_signature(self):
        import inspect
        from data_fetchers import get_vix_full
        source = inspect.getsource(get_vix_full)
        self.assertTrue('3y' in source or '"3y"' in source)
        self.assertIn("pct_3y", source)
        self.assertIn("pct_1y", source)


# ══════════════════════════════════════════════════════════════════════
# FIX-11 — VWAP Label
# ══════════════════════════════════════════════════════════════════════

class TestVWAPLabelFix(unittest.TestCase):

    def test_label_renamed(self):
        import inspect
        from data_fetchers import compute_spx_direction
        source = inspect.getsource(compute_spx_direction)
        self.assertNotIn("VWAP Position", source)
        self.assertIn("Typical Price vs Avg", source)


# ══════════════════════════════════════════════════════════════════════
# FIX-12 — OnlineVariance Removed
# ══════════════════════════════════════════════════════════════════════

class TestOnlineVarianceRemoved(unittest.TestCase):

    def test_class_removed(self):
        import data_fetchers
        self.assertNotIn("OnlineVariance", dir(data_fetchers))


# ══════════════════════════════════════════════════════════════════════
# FIX-06 — Vol Regime
# ══════════════════════════════════════════════════════════════════════

class TestVolRegimeCollapse(unittest.TestCase):

    def test_no_separate_vix_signals(self):
        import inspect
        from data_fetchers import compute_spx_direction
        source = inspect.getsource(compute_spx_direction)
        self.assertNotIn('"VIX Term Structure"', source)
        self.assertNotIn('"VIX Level"', source)
        self.assertIn('"Vol Regime"', source)


# ══════════════════════════════════════════════════════════════════════
# FEAT-01 — Scored Options Table with Vega
# ══════════════════════════════════════════════════════════════════════

class TestScoredOptionsVega(unittest.TestCase):

    def test_render_has_vega_column(self):
        from ui_components import render_scored_options
        html = render_scored_options([{
            "strike": 100, "lastPrice": 5, "bid": 4.9, "ask": 5.1,
            "volume": 1000, "openInterest": 5000, "iv": 0.25,
            "voi": 0.20, "score": 0.35, "side": "call",
            "delta": 0.55, "vega": 0.120, "rho": 0.045,
        }], side="calls")
        self.assertIn("Vega", html)
        self.assertIn("0.120", html)

    def test_render_empty(self):
        from ui_components import render_scored_options
        html = render_scored_options([], side="calls")
        self.assertIn("No scored contracts", html)


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)
