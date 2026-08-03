#!/usr/bin/env python3
"""SENTINEL — Centralized API Key Management

Handles SecretStr extraction, validation, and injection.
Eliminates the st.secrets → SecretStr → .get_secret_value() chain
scattered throughout the codebase.
"""

from __future__ import annotations

import logging
from collections import namedtuple

logger = logging.getLogger("sentinel.api_keys")


class SecretStr(namedtuple("SecretStr", ["value"])):
    """Immutable secret string that redacts on repr/str."""
    def __repr__(self) -> str: return "***"
    def __str__(self) -> str: return "***"
    def get_secret_value(self) -> str: return self.value
    def __bool__(self) -> bool: return bool(self.value)


class ApiKeyManager:
    """Centralized API key management with multi-source resolution.
    
    Resolution order:
    1. Explicit overrides (set at runtime via .set())
    2. Streamlit secrets (st.secrets, multiple key name variants)
    3. Environment variables
    4. Default empty string
    
    Usage:
        keys = ApiKeyManager()
        keys.load_from_streamlit()  # call once at startup
        fred_key = keys.get("FRED_API_KEY")  # returns raw string, never SecretStr
    """

    _KEY_ALIASES: dict[str, list[str]] = {
        "GEMINI_API_KEY":   ["GEMINI_API_KEY", "gemini_api_key"],
        "FRED_API_KEY":     ["FRED_API_KEY", "fred_api_key"],
        "FINNHUB_API_KEY":  ["FINNHUB_API_KEY", "finnhub_api_key"],
        "NEWSAPI_KEY":      ["NEWSAPI_KEY", "newsapi_key", "NEWSAPI_API_KEY"],
        "CFTC_API_KEY":     ["CFTC_API_KEY", "cftc_api_key"],
        "CESIUM_ION_TOKEN": ["CESIUM_ION_TOKEN", "cesium_ion_token"],
        "ALPACA_API_KEY":   ["ALPACA_API_KEY", "alpaca_api_key"],
        "ALPACA_SECRET_KEY": ["ALPACA_SECRET_KEY", "alpaca_secret_key"],
        "AISSTREAM_API_KEY": ["AISSTREAM_API_KEY", "aisstream_api_key"],
        "MARINESIA_API_KEY": ["MARINESIA_API_KEY", "marinesia_api_key"],
    }

    def __init__(self):
        self._store: dict[str, SecretStr] = {}

    def set(self, key_name: str, value: str) -> None:
        """Explicitly set/override a key at runtime."""
        if value:
            self._store[key_name.upper()] = SecretStr(str(value).strip())

    def get(self, key_name: str, default: str = "") -> str:
        """Get the raw string value of a key. Never returns SecretStr."""
        key_upper = key_name.upper()
        secret = self._store.get(key_upper)
        if secret and secret.value:
            return secret.value
        return default

    def get_secret(self, key_name: str, default: str = "") -> SecretStr:
        """Get the SecretStr wrapper for a key."""
        key_upper = key_name.upper()
        secret = self._store.get(key_upper)
        if secret and secret.value:
            return secret
        return SecretStr(default)

    def has(self, key_name: str) -> bool:
        """Check if a key is available and non-empty."""
        return bool(self.get(key_name))

    def load_from_streamlit(self) -> None:
        """Load all known keys from Streamlit secrets.
        
        Tries exact name, lowercase, uppercase, and nested [api_keys] section.
        Only sets keys that aren't already overridden.
        """
        try:
            import streamlit as st
        except ImportError:
            logger.debug("Streamlit not available, skipping secrets load")
            return

        for canonical, aliases in self._KEY_ALIASES.items():
            if canonical in self._store and self._store[canonical].value:
                continue

            val = None
            for alias in aliases:
                for k in [alias, alias.lower(), alias.upper()]:
                    try:
                        v = st.secrets.get(k, None)
                        if v:
                            val = str(v).strip()
                            break
                    except Exception:
                        pass
                if val:
                    break

            if not val:
                try:
                    v = st.secrets.get("api_keys", {}).get(canonical, None)
                    if v:
                        val = str(v).strip()
                except Exception:
                    pass

            if val:
                self._store[canonical] = SecretStr(val)

    def load_from_env(self) -> None:
        """Load keys from environment variables as fallback."""
        import os
        for canonical in self._KEY_ALIASES:
            if canonical in self._store and self._store[canonical].value:
                continue
            val = os.environ.get(canonical, "")
            if val:
                self._store[canonical] = SecretStr(val.strip())

    def status(self) -> list[tuple[str, bool]]:
        """Return list of (key_name, is_available) for status display."""
        return [(name, self.has(name)) for name in self._KEY_ALIASES]

    def __repr__(self) -> str:
        available = sum(1 for name in self._KEY_ALIASES if self.has(name))
        return f"ApiKeyManager({available}/{len(self._KEY_ALIASES)} keys loaded)"


def resolve_secret_value(value) -> str:
    """Extract raw string from any secret-like object.
    
    Handles: SecretStr, pydantic SecretStr, plain str, None.
    """
    if value is None:
        return ""
    if hasattr(value, "get_secret_value"):
        return value.get_secret_value()
    return str(value).strip()
