"""Secret lookup (st.secrets → env) wrapped in a redacting SecretStr."""
from __future__ import annotations

import os
from collections import namedtuple


class SecretStr(namedtuple("SecretStr", ["value"])):
    """Immutable secret that never prints its value."""
    __slots__ = ()

    def __repr__(self) -> str:
        return "SecretStr('***')"

    __str__ = __repr__

    def get_secret_value(self) -> str:
        return self.value or ""

    def __bool__(self) -> bool:
        return bool(self.value)


def unwrap_secret(value) -> str:
    """Raw string from SecretStr / pydantic SecretStr / str / None."""
    if value is None:
        return ""
    if hasattr(value, "get_secret_value"):
        try:
            return (value.get_secret_value() or "").strip()
        except Exception:
            return ""
    return str(value).strip()


def _from_streamlit(name: str) -> str:
    try:
        import streamlit as st
        secrets = st.secrets
        for k in (name, name.lower(), name.upper()):
            if k in secrets and secrets[k]:
                return str(secrets[k]).strip()
        section = secrets.get("api_keys", {})
        if section and section.get(name):
            return str(section[name]).strip()
    except Exception:
        # No secrets.toml (or not running under Streamlit) is a normal state.
        pass
    return ""


def get_secret(name: str) -> SecretStr:
    """Look up *name* in Streamlit secrets, then the environment."""
    return SecretStr(_from_streamlit(name) or os.environ.get(name, "").strip())
