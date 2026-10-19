"""Central constants: rate limits, cache TTLs, tickers, keyword lists.

Everything here is plain data so any module can ``from sentinel.config import X``
without import cycles.
"""
from __future__ import annotations

import os

import pytz

TRADING_DAYS_PER_YEAR: int = 252
CALENDAR_DAYS_PER_YEAR: int = 365
DEFAULT_RISK_FREE_RATE: float = 0.045

# ── HTTP / yfinance
YF_MAX_CONCURRENT: int = 6
YF_MIN_GAP: float = 0.12
YF_CACHE_TTL: int = 180
YF_CACHE_MAX_SIZE: int = 300

YAHOO_USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

HTTP_POOL_CONNECTIONS: int = 20
HTTP_POOL_MAXSIZE: int = 50
HTTP_RETRY_TOTAL: int = 2
HTTP_RETRY_BACKOFF: float = 0.5
HTTP_RETRY_STATUS_FORCELIST: list[int] = [500, 502, 503, 504]  # never hammer a 429

CIRCUIT_BREAKER_THRESHOLD: int = 3
CIRCUIT_BREAKER_RECOVERY_SECS: int = 120

# Minimum seconds between requests to the same host.
API_RATE_LIMITS: dict[str, float] = {
    "api.gdeltproject.org": 5.2,  # GDELT allows one request every 5 s per IP
    "api.adsb.lol": 1.0,
    "api.coingecko.com": 1.5,
    "gamma-api.polymarket.com": 0.5,
    "api.hyperliquid.xyz": 0.1,
    "api.rainviewer.com": 2.0,
    "eonet.gsfc.nasa.gov": 2.0,
}
API_RATE_LIMIT_DEFAULT: float = 0.2

TZ_PACIFIC = pytz.timezone("US/Pacific")
TZ_EASTERN = pytz.timezone("US/Eastern")
TZ_UTC = pytz.utc

# ── Options scoring weights
OPTIONS_SCORE_W1: float = 0.40
OPTIONS_SCORE_W2: float = 0.30
OPTIONS_SCORE_W3: float = 0.30
OPTIONS_UNUSUAL_VOL_OI_RATIO: float = 3.0

# ── Persistence. Disk writes (watchlist, AI memory) are shared by every
# visitor of a deployed app, so they are opt-in. Local runs enable it by
# default via the localhost check in ``sentinel.state``.
PERSIST_ENV = os.environ.get("SENTINEL_PERSIST", "").strip().lower()
DATA_DIR = os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.expanduser("~"), ".sentinel"))

DEFAULT_WATCHLIST: list[str] = ["SPY", "QQQ", "NVDA", "AAPL", "GLD", "TLT", "BTC-USD"]

# ── BTC spot ETFs
ETF_TICKERS: list[str] = [
    "IBIT", "FBTC", "ARKB", "BITB", "GBTC",
    "HODL", "BRRR", "EZBC", "BTCO", "BTCW",
]

GLOBAL_INDICES: dict[str, list[tuple[str, str, str]]] = {
    "Americas": [
        ("^GSPC", "S&P 500", "US"), ("^DJI", "Dow Jones", "US"), ("^IXIC", "Nasdaq Composite", "US"),
        ("^RUT", "Russell 2000", "US"), ("^GSPTSE", "TSX Composite", "CA"), ("^BVSP", "Bovespa", "BR"),
    ],
    "EMEA": [
        ("^FTSE", "FTSE 100", "GB"), ("^GDAXI", "DAX", "DE"), ("^FCHI", "CAC 40", "FR"),
        ("^STOXX50E", "Euro Stoxx 50", "EU"), ("^AEX", "AEX", "NL"), ("^TA125.TA", "TA-125", "IL"),
    ],
    "APAC": [
        ("^N225", "Nikkei 225", "JP"), ("^HSI", "Hang Seng", "HK"), ("000001.SS", "Shanghai Comp", "CN"),
        ("^KS11", "KOSPI", "KR"), ("^AXJO", "ASX 200", "AU"), ("^BSESN", "Sensex", "IN"),
    ],
}

YIELD_MATURITIES: list[tuple[str, str]] = [
    ("DGS1MO", "1M"), ("DGS3MO", "3M"), ("DGS6MO", "6M"),
    ("DGS1", "1Y"), ("DGS2", "2Y"), ("DGS3", "3Y"),
    ("DGS5", "5Y"), ("DGS7", "7Y"), ("DGS10", "10Y"),
    ("DGS20", "20Y"), ("DGS30", "30Y"),
]

MATURITY_NUM_MAP: dict[str, float] = {
    "1M": 1 / 12, "3M": 0.25, "6M": 0.5, "1Y": 1, "2Y": 2,
    "3Y": 3, "5Y": 5, "7Y": 7, "10Y": 10, "20Y": 20, "30Y": 30,
}

# ── GEO
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

GEO_SHIPPING_LANES: dict = {
    "type": "FeatureCollection",
    "features": [
        {"type": "Feature", "properties": {"name": "Trans-Pacific", "type": "shipping"}, "geometry": {"type": "LineString", "coordinates": [[121.5, 31.2], [140.0, 35.0], [160.0, 38.0], [180.0, 35.0], [-160.0, 28.0], [-140.0, 24.0], [-118.2, 33.7]]}},
        {"type": "Feature", "properties": {"name": "Trans-Atlantic", "type": "shipping"}, "geometry": {"type": "LineString", "coordinates": [[2.35, 48.85], [-5.0, 48.0], [-20.0, 42.0], [-40.0, 38.0], [-60.0, 35.0], [-74.0, 40.7]]}},
        {"type": "Feature", "properties": {"name": "Suez / Red Sea", "type": "shipping"}, "geometry": {"type": "LineString", "coordinates": [[5.0, 36.0], [15.0, 37.0], [25.0, 35.0], [32.0, 31.0], [32.5, 29.9], [33.5, 27.0], [38.0, 23.0], [43.5, 12.5], [50.0, 10.0]]}},
        {"type": "Feature", "properties": {"name": "Strait of Hormuz", "type": "shipping"}, "geometry": {"type": "LineString", "coordinates": [[50.0, 10.0], [55.0, 15.0], [58.0, 20.0], [56.5, 24.0], [57.5, 23.6]]}},
        {"type": "Feature", "properties": {"name": "Malacca / SCS", "type": "shipping"}, "geometry": {"type": "LineString", "coordinates": [[80.0, 5.0], [90.0, 3.0], [100.0, 2.5], [104.5, 1.3], [108.0, 3.5], [110.0, 5.0], [115.0, 8.0], [121.5, 22.0], [121.5, 31.2]]}},
        {"type": "Feature", "properties": {"name": "Cape of Good Hope", "type": "shipping"}, "geometry": {"type": "LineString", "coordinates": [[2.35, 48.85], [-10.0, 30.0], [-17.0, 14.0], [-14.0, -8.0], [0.0, -20.0], [18.5, -34.0], [25.0, -34.5], [35.0, -28.0], [43.5, -12.0], [50.0, 10.0]]}},
    ],
}

# ── News relevance filter
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
    "puppy", "kitten", "cute animal",
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
