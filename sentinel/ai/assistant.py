"""Sentinel AI: Gemini streaming with live-market context, memory and divergence scan."""
from __future__ import annotations

import html
import json
import logging
import re
from datetime import datetime
from pathlib import Path

import streamlit as st

from sentinel.ai.prompt import SENTINEL_PROMPT
from sentinel.config import DATA_DIR
from sentinel.core.http import _sanitize_error
from sentinel.state import persistence_enabled

logger = logging.getLogger("sentinel.ai")

# Tried in order; the first that streams wins (404/quota falls through).
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"]

_MEMORY_FILE = Path(DATA_DIR) / "memory.json"
_MAX_MEMORY_ENTRIES = 50
_MEMORY_KEYS = ("summaries", "positions", "theses")


# ── Memory: per-session by default; on disk only for local single-user runs ──
def load_memory() -> dict:
    if "ai_memory" not in st.session_state:
        mem = {k: [] for k in _MEMORY_KEYS}
        if persistence_enabled() and _MEMORY_FILE.exists():
            try:
                data = json.loads(_MEMORY_FILE.read_text(encoding="utf-8"))
                for k in _MEMORY_KEYS:
                    if isinstance(data.get(k), list):
                        mem[k] = data[k][-_MAX_MEMORY_ENTRIES:]
            except Exception as e:
                logger.warning("AI memory load failed: %s", e)
        st.session_state.ai_memory = mem
    return st.session_state.ai_memory


def save_memory(mem: dict) -> None:
    for k in _MEMORY_KEYS:
        mem[k] = mem.get(k, [])[-_MAX_MEMORY_ENTRIES:]
    st.session_state.ai_memory = mem
    if not persistence_enabled():
        return
    try:
        _MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _MEMORY_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(mem, indent=2, default=str), encoding="utf-8")
        tmp.replace(_MEMORY_FILE)
    except Exception as e:
        logger.warning("AI memory save failed: %s", e)


def get_memory_context() -> str:
    mem = load_memory()
    parts = []
    if mem["theses"]:
        parts.append("  Active theses: " + "; ".join(mem["theses"][-5:]))
    if mem["positions"]:
        parts.append("  Tracked positions: " + "; ".join(mem["positions"][-10:]))
    for s in mem["summaries"][-3:]:
        parts.append(f"  [{s.get('date', '')}] {str(s.get('summary', ''))[:240]}")
    return ("PERSISTENT MEMORY (user-provided, previous sessions):\n" + "\n".join(parts)) if parts else ""


def summarize_and_persist(chat_history, api_key) -> None:
    """Summarise the conversation into memory (called when the chat is cleared)."""
    if not chat_history or len(chat_history) < 2 or not api_key:
        return
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        transcript = "\n".join(f"{'USER' if m['role'] == 'user' else 'SENTINEL'}: {m['content'][:400]}"
                               for m in chat_history[-20:])
        resp = client.models.generate_content(
            model=GEMINI_MODELS[0],
            contents="Summarise this conversation in 3-5 bullets: tickers, theses, positions, key numbers.\n\n" + transcript,
            config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=300),
        )
        mem = load_memory()
        mem["summaries"].append({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "summary": resp.text or ""})
        save_memory(mem)
    except Exception as e:
        logger.warning("Memory summary failed: %s", _sanitize_error(e))


def parse_chained_commands(text: str) -> list[str]:
    """'/flash NVDA then /scenario NVDA' → ['/flash NVDA', '/scenario NVDA']."""
    return [p.strip() for p in re.split(r"\s+then\s+", text.strip(), flags=re.IGNORECASE) if p.strip()]


def detect_sentiment_divergence(watchlist=None) -> list[dict]:
    """Simple price-vs-sentiment mismatches (VIX vs SPY, market fear/greed vs watchlist moves)."""
    from sentinel.data.market import calc_stock_fear_greed, get_vix_full, multi_quotes, yahoo_quote
    out = []
    vix = get_vix_full()[0]
    spy = yahoo_quote("SPY")
    if vix and spy:
        if spy["pct"] > 0.3 and vix > 20:
            out.append({"type": "VIX / SPY", "signal": "Hidden fear", "severity": "HIGH" if vix > 25 else "MEDIUM",
                        "detail": f"SPY {spy['pct']:+.2f}% while VIX stays elevated at {vix:.1f}"})
        elif spy["pct"] < -0.3 and vix < 16:
            out.append({"type": "VIX / SPY", "signal": "Complacent dip", "severity": "MEDIUM",
                        "detail": f"SPY {spy['pct']:+.2f}% with VIX only {vix:.1f}"})
    fg = calc_stock_fear_greed()[0]
    if watchlist and fg is not None:
        for q in multi_quotes(tuple(watchlist[:8])):
            if fg < 30 and q["pct"] > 1.0:
                out.append({"type": q["ticker"], "signal": "Strength in fear", "severity": "MEDIUM",
                            "detail": f"{q['ticker']} {q['pct']:+.2f}% while market fear/greed = {fg}"})
            elif fg > 75 and q["pct"] < -1.0:
                out.append({"type": q["ticker"], "signal": "Weakness in greed", "severity": "MEDIUM",
                            "detail": f"{q['ticker']} {q['pct']:+.2f}% while market fear/greed = {fg}"})
    return out


def format_gemini_msg(raw: str) -> str:
    """Escape model output and keep line breaks (model text is untrusted HTML)."""
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", raw or "")
    text = re.sub(r"`([^`\n]+)`", r"\1", text)
    return html.escape(text).replace("\n", "<br>")


def list_gemini_models(api_key: str) -> list[str]:
    try:
        from google import genai
        return sorted(m.name for m in genai.Client(api_key=api_key).models.list() if "gemini" in m.name)
    except Exception as e:
        return [f"Error: {_sanitize_error(e)}"]


def gemini_response(user_msg: str, history: list, context: str, api_key: str, extra_context: str = ""):
    """Yield streamed text chunks from the first available Gemini model."""
    if not api_key:
        yield "Add a Gemini API key to use Sentinel AI."
        return
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        yield "The google-genai package is not installed (pip install google-genai)."
        return
    client = genai.Client(api_key=api_key)
    header = "\n\n".join(x for x in (extra_context, context, get_memory_context()) if x)
    contents = [types.Content(role="user" if m["role"] == "user" else "model", parts=[types.Part(text=m["content"])])
                for m in history[-12:]]
    contents.append(types.Content(role="user", parts=[types.Part(text=f"{header}\n\n{user_msg}" if header else user_msg)]))
    errors = []
    for model in GEMINI_MODELS:
        try:
            stream = client.models.generate_content_stream(
                model=model, contents=contents,
                config=types.GenerateContentConfig(system_instruction=SENTINEL_PROMPT, max_output_tokens=4096,
                                                   temperature=0.2, top_p=0.9),
            )
            for chunk in stream:
                text = getattr(chunk, "text", None)
                if text:
                    yield text
            return
        except Exception as e:
            msg = _sanitize_error(e)
            errors.append(f"{model}: {msg[:120]}")
            if any(s in msg.lower() for s in ("not found", "404", "429", "quota", "resource_exhausted", "unavailable", "503")):
                continue
            yield f"Gemini error: {msg[:300]}"
            return
    yield "All Gemini models failed:\n" + "\n".join(errors)
