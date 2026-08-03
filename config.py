#!/usr/bin/env python3
"""SENTINEL — Centralized Configuration

All magic numbers, constants, rate-limit defaults, and environment config
live here. Replaces hardcoded values scattered across data_fetchers.py.

Uses pydantic BaseSettings for type validation and env-var overrides.
"""

from __future__ import annotations
import os

try:
    from pydantic_settings import BaseSettings
    from pydantic import Field
except ImportError:
    from dataclasses import dataclass, field as _dc_field

    class _FakeBaseSettings:
        pass

    BaseSettings = _FakeBaseSettings
    Field = lambda default=None, **kw: default


TRADING_DAYS_PER_YEAR: int = 252
CALENDAR_DAYS_PER_YEAR: int = 365
DEFAULT_RISK_FREE_RATE: float = 0.045
BPS_FACTOR: float = 0.0001


# Higher concurrency + shorter gap: batch download does the heavy lifting;
# single-ticker path only fills gaps.
YF_MAX_CONCURRENT: int = 6
YF_MIN_GAP: float = 0.12
YF_CACHE_TTL: int = 180
YF_CACHE_MAX_SIZE: int = 300

YAHOO_USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]


HTTP_POOL_CONNECTIONS: int = 20
HTTP_POOL_MAXSIZE: int = 50
HTTP_RETRY_TOTAL: int = 2
HTTP_RETRY_BACKOFF: float = 0.5
HTTP_RETRY_STATUS_FORCELIST: list[int] = [429, 500, 502, 503, 504]

CIRCUIT_BREAKER_THRESHOLD: int = 3
CIRCUIT_BREAKER_RECOVERY_SECS: int = 300


API_RATE_LIMITS: dict[str, float] = {
    "api.gdeltproject.org": 1.0,
    "api.coingecko.com": 1.5,
    "gamma-api.polymarket.com": 1.0,
    "clob.polymarket.com": 1.0,
    "api.rainviewer.com": 2.0,
    "eonet.gsfc.nasa.gov": 2.0,
}
API_RATE_LIMIT_DEFAULT: float = 0.5


CACHE_TTL_QUOTE: int = 60
CACHE_TTL_MULTI_QUOTE: int = 60
CACHE_TTL_OPTIONS: int = 600
CACHE_TTL_SPY_HISTORY: int = 300
CACHE_TTL_VIX: int = 300
CACHE_TTL_FUTURES: int = 120
CACHE_TTL_HEATMAP: int = 900
CACHE_TTL_FINANCIALS: int = 1800
CACHE_TTL_FRED: int = 3600
CACHE_TTL_MACRO: int = 3600
CACHE_TTL_NEWS: int = 600
CACHE_TTL_GEO: int = 300
CACHE_TTL_CRYPTO: int = 600
CACHE_TTL_EARNINGS: int = 3600
CACHE_TTL_AI_HOTSPOTS: int = 43200
CACHE_TTL_SOVEREIGN: int = 300
CACHE_TTL_COT: int = 3600
CACHE_TTL_RISK_FREE: int = 3600


import pytz

TZ_PACIFIC = pytz.timezone("US/Pacific")
TZ_EASTERN = pytz.timezone("US/Eastern")
TZ_UTC = pytz.utc


OPTIONS_SCORE_W1: float = 0.40
OPTIONS_SCORE_W2: float = 0.30
OPTIONS_SCORE_W3: float = 0.30
OPTIONS_UNUSUAL_VOL_OI_RATIO: float = 3.0


ETF_TICKERS: list[str] = [
    "IBIT", "FBTC", "ARKB", "BITB", "GBTC",
    "HODL", "BRRR", "EZBC", "BTCO", "BTCW",
]

ETF_COLORS: dict[str, str] = {
    "IBIT": "#00CC44", "FBTC": "#00AA88", "ARKB": "#44BB66",
    "BITB": "#66CC88", "GBTC": "#FF4444", "HODL": "#55DD99",
    "BRRR": "#33CC77", "EZBC": "#77DDAA", "BTCO": "#88CCBB",
    "BTCW": "#99BBAA",
}


GLOBAL_INDICES: dict[str, list[tuple[str, str, str]]] = {
    "Americas": [
        ("^GSPC", "S&P 500", "🇺🇸"),
        ("^DJI", "Dow Jones", "🇺🇸"),
        ("^IXIC", "Nasdaq Composite", "🇺🇸"),
        ("^RUT", "Russell 2000", "🇺🇸"),
        ("^GSPTSE", "TSX Composite", "🇨🇦"),
        ("^BVSP", "Bovespa", "🇧🇷"),
    ],
    "EMEA": [
        ("^FTSE", "FTSE 100", "🇬🇧"),
        ("^GDAXI", "DAX", "🇩🇪"),
        ("^FCHI", "CAC 40", "🇫🇷"),
        ("^STOXX50E", "Euro Stoxx 50", "🇪🇺"),
        ("^AEX", "AEX", "🇳🇱"),
        ("^TA125.TA", "TA-125", "🇮🇱"),
    ],
    "APAC": [
        ("^N225", "Nikkei 225", "🇯🇵"),
        ("^HSI", "Hang Seng", "🇭🇰"),
        ("000001.SS", "Shanghai Comp", "🇨🇳"),
        ("^KS11", "KOSPI", "🇰🇷"),
        ("^AXJO", "ASX 200", "🇦🇺"),
        ("^BSESN", "Sensex", "🇮🇳"),
    ],
}


YIELD_MATURITIES: list[tuple[str, str]] = [
    ("DGS1MO", "1M"), ("DGS3MO", "3M"), ("DGS6MO", "6M"),
    ("DGS1", "1Y"), ("DGS2", "2Y"), ("DGS3", "3Y"),
    ("DGS5", "5Y"), ("DGS7", "7Y"), ("DGS10", "10Y"),
    ("DGS20", "20Y"), ("DGS30", "30Y"),
]

MATURITY_NUM_MAP: dict[str, float] = {
    "1M": 1/12, "3M": 0.25, "6M": 0.5, "1Y": 1, "2Y": 2,
    "3Y": 3, "5Y": 5, "7Y": 7, "10Y": 10, "20Y": 20, "30Y": 30,
}


GEO_FINANCIAL_NETWORKS: list[dict] = [
    {"name": "Bloomberg",  "channel_id": "UCIALMKvObZNtJ6AmdCLP7Lg", "embed_url": "https://www.youtube.com/embed/iEpJwprxDdk?autoplay=1&mute=1"},
    {"name": "CNBC",       "channel_id": "UCvJJ_dzjViJCoLf5uKUTwoA", "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCvJJ_dzjViJCoLf5uKUTwoA&autoplay=1&mute=1"},
    {"name": "Euronews",   "channel_id": "UCW2QcKZiU8aUGg4yxCIditg", "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCW2QcKZiU8aUGg4yxCIditg&autoplay=1&mute=1"},
    {"name": "France 24",  "channel_id": "UCQfwfsi5VrQ8yKZ-UWmAoBw", "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCQfwfsi5VrQ8yKZ-UWmAoBw&autoplay=1&mute=1"},
    {"name": "Al Jazeera", "channel_id": "UCNye-wNBqNL5ZzHSJj3l8Bg", "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCNye-wNBqNL5ZzHSJj3l8Bg&autoplay=1&mute=1"},
    {"name": "DW News",    "channel_id": "UCknLrEdhRCp1aegoMqRaCZg", "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCknLrEdhRCp1aegoMqRaCZg&autoplay=1&mute=1"},
    {"name": "Sky News",   "channel_id": "UCoMdktPbSTixAyNGwb-UYkQ", "embed_url": "https://www.youtube.com/embed/live_stream?channel=UCoMdktPbSTixAyNGwb-UYkQ&autoplay=1&mute=1"},
]

GEO_THEATERS: dict[str, str] = {
    "Middle East + Oil + Hormuz":         "Middle East Iran oil Hormuz",
    "China + Taiwan + Semiconductors":    "China Taiwan semiconductor chips TSMC",
    "Russia + Ukraine + Energy":          "Russia Ukraine energy grain NATO",
    "Africa + Cobalt + Lithium + Coup":   "Africa cobalt lithium coup Sahel Mali",
    "Red Sea + Suez + Shipping":          "Red Sea Suez shipping Houthi container",
    "South China Sea + Trade":            "South China Sea shipping Philippines trade",
}

GEO_IMPACT_TICKERS: dict[str, str] = {
    "WTI Crude": "CL=F", "Brent Crude": "BZ=F", "Natural Gas": "NG=F",
    "Gold":      "GC=F", "Silver":      "SI=F", "Wheat":       "ZW=F",
    "USD Index": "DX-Y.NYB", "EUR/USD": "EURUSD=X", "10Y Yield": "^TNX",
}


MARKET_KEYWORDS: set[str] = {
    "market", "stock", "equit", "bond", "treasury", "yield", "rate", "fed ",
    "federal reserve", "fomc", "monetary", "inflation", "cpi", "pce", "gdp",
    "recession", "rally", "selloff", "sell-off", "crash", "bull", "bear",
    "earnings", "revenue", "profit", "dividend", "buyback", "ipo", "spac",
    "s&p 500", "s&p500", "nasdaq", "dow jones", "russell", "ftse", "dax",
    "nikkei", "hang seng", "index", "futures", "options", "derivative",
    "hedge fund", "short sell", "insider", "sec ", "regulat", "investm",
    "analyst", "upgrade", "downgrade", "target price", "eps",
    "central bank", "ecb", "boj", "boe", "rba", "pboc", "rate hike",
    "rate cut", "taper", "quantitative", "stimulus", "fiscal", "debt",
    "deficit", "surplus", "trade war", "tariff", "sanction", "embargo",
    "currency", "dollar", "euro", "yen", "yuan", "forex", "fx ",
    "commodity", "crude", "oil", "gold", "silver", "copper", "wheat",
    "natural gas", "opec", "energy", "mining",
    "geopolitic", "conflict", "war ", "military", "nato", "nuclear",
    "missile", "sanctions", "blockade", "strait", "strait of hormuz",
    "shipping", "supply chain", "semiconductor", "chip", "ai ", "tech",
    "iran", "russia", "china", "taiwan", "ukraine", "middle east",
    "gaza", "israel", "north korea", "red sea", "houthi", "suez",
    "bitcoin", "crypto", "ethereum", "etf approval", "sec crypto",
    "layoff", "restructur", "merger", "acquisition", "antitrust",
    "bankruptcy", "default", "credit rating", "moody", "fitch",
    "standard & poor", "downgrad",
}

FLUFF_KEYWORDS: set[str] = {
    "celebrity", "entertainment", "lifestyle", "recipe", "fashion",
    "horoscope", "zodiac", "dating", "reality tv", "reality show",
    "sports score", "game recap", "touchdown", "home run",
    "viral video", "tiktok", "influencer", "selfie",
    "weather forecast", "daily weather",
    "lottery", "sweepstakes", "giveaway",
    "pet", "puppy", "kitten", "cute animal",
    "diet", "weight loss", "wellness tip",
    "best movies", "best shows", "streaming pick", "movie review",
    "baby name", "wedding", "engagement ring",
}

FINANCIAL_SOURCES: set[str] = {
    "reuters", "bloomberg", "cnbc", "marketwatch", "financial times",
    "ft.com", "wsj", "wall street journal", "barron", "seekingalpha",
    "investing.com", "zerohedge", "yahoo finance", "benzinga",
    "thestreet", "morningstar", "tradingview", "forexlive",
    "coindesk", "cointelegraph", "the block", "decrypt",
    "defense news", "janes", "jane's", "al jazeera", "bbc",
    "politico", "foreign policy", "foreign affairs",
}
