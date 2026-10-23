"""Sentinel AI (Gemini) chat with live-market context."""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from sentinel.ai.assistant import (
    detect_sentiment_divergence, format_gemini_msg, gemini_response, list_gemini_models, load_memory,
    parse_chained_commands, save_memory, summarize_and_persist,
)
from sentinel.core.formatting import _esc
from sentinel.data.market import market_snapshot_str, multi_quotes
from sentinel.data.news import build_brief_context
from sentinel.state import key, persistence_enabled
from sentinel.ui.components import note, section

QUICK = {"Brief": "/brief", "Rotation": "/rotate", "Sentiment": "/sentiment", "Narrative": "/narrative",
         "Divergence": "/divergence", "Earnings": "/earnings", "Fed odds": "/poly Fed rate"}


def _context_for(cmd: str) -> str:
    c = cmd.strip().lower()
    ss = st.session_state
    ctx = build_brief_context(geo_watch=ss.geo_watch) if c.startswith(("/brief", "/geo", "/narrative")) else market_snapshot_str()
    if c.startswith("/divergence"):
        divs = detect_sentiment_divergence(ss.watchlist)
        ctx += "\n\nSENTIMENT DIVERGENCE DATA:\n" + ("\n".join(f"  [{d['severity']}] {d['type']}: {d['signal']} — {d['detail']}"
                                                         for d in divs) or "  None detected — signals aligned.")
    if c.startswith("/alert") and ss.watchlist:
        qs = multi_quotes(tuple(ss.watchlist[:10]))
        ctx += "\n\nWATCHLIST:\n" + "\n".join(f"  {q['ticker']}: {q['price']:,.2f} ({q['pct']:+.2f}%)" for q in qs)
    return ctx


def _user_context() -> str:
    ss = st.session_state
    parts = []
    if ss.macro_theses.strip():
        parts.append(f"USER MACRO THESES: {ss.macro_theses.strip()}")
    if ss.watchlist:
        parts.append(f"USER WATCHLIST: {', '.join(ss.watchlist)}")
    if ss.geo_watch.strip():
        parts.append(f"USER GEO WATCH: {ss.geo_watch.strip()}")
    return "\n".join(parts)


def _ask(text: str) -> None:
    ss = st.session_state
    api_key = key("gemini_key")
    ss.chat_history.append({"role": "user", "content": text})
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(_esc(text))
    with st.chat_message("assistant", avatar=":material/insights:"):
        box = st.empty()
        out = ""
        for i, cmd in enumerate(parse_chained_commands(text)):
            if i:
                out += "\n\n" + "─" * 40 + "\n\n"
            for chunk in gemini_response(cmd, ss.chat_history[:-1], _context_for(cmd), api_key, _user_context()):
                out += chunk
                box.markdown(f'<div class="chat-ai">{format_gemini_msg(out)}</div>', unsafe_allow_html=True)
    ss.chat_history.append({"role": "assistant", "content": out})


def render():
    ss = st.session_state
    section("Sentinel AI", "Gemini with live prices, headlines, your watchlist and theses injected as context")
    api_key = key("gemini_key")
    if not api_key:
        note('Add a Gemini API key (GEMINI_API_KEY in secrets, or the sidebar). Free keys: '
             '<a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noopener">Google AI Studio</a>.<br>'
             'Commands: /brief · /flash NVDA · /geo Red Sea · /scenario Gold · /screen low P/E · /narrative · '
             '/divergence · chain with “then”.', "warn", html=True)
        return

    divs = detect_sentiment_divergence(ss.watchlist)
    if divs:
        note("<b>Divergences:</b> " + " · ".join(f"{_esc(d['signal'])} ({_esc(d['detail'])})" for d in divs[:3]), html=True)

    cols = st.columns(len(QUICK))
    clicked = None
    for col, (label, cmd) in zip(cols, QUICK.items()):
        if col.button(label, key=f"qb_{label}", width="stretch"):
            clicked = cmd

    for m in ss.chat_history:
        with st.chat_message(m["role"], avatar=":material/person:" if m["role"] == "user" else ":material/insights:"):
            if m["role"] == "user":
                st.markdown(_esc(m["content"]))
            else:
                st.markdown(f'<div class="chat-ai">{format_gemini_msg(m["content"])}</div>', unsafe_allow_html=True)

    prompt = st.chat_input("Ask anything, or /brief · /flash TSLA · /scenario gold · chain with “then”")
    prompt = prompt or ss.pop("ai_pending", None)  # question typed on the terminal command line
    if clicked or prompt:
        _ask(clicked or prompt)

    with st.expander("Memory & settings"):
        mem = load_memory()
        st.caption("Memory is saved to disk on local runs; on shared deployments it lives only in this browser session."
                   if persistence_enabled() else "Memory lives only in this browser session.")
        a, b = st.columns(2)
        with a.form("thesis_form", clear_on_submit=True, border=False):
            th = st.text_input("Save a thesis", placeholder="Long gold on rate cuts")
            if st.form_submit_button("Save thesis") and th.strip():
                mem["theses"].append(f"[{datetime.now():%m/%d}] {th.strip()[:200]}")
                save_memory(mem)
        with b.form("pos_form", clear_on_submit=True, border=False):
            pos = st.text_input("Track a position", placeholder="Long NVDA 950C 6/20")
            if st.form_submit_button("Track position") and pos.strip():
                mem["positions"].append(f"[{datetime.now():%m/%d}] {pos.strip()[:200]}")
                save_memory(mem)
        if any(mem.values()):
            lines = [f"Thesis · {_esc(t)}" for t in mem["theses"][-5:]] + \
                    [f"Position · {_esc(p)}" for p in mem["positions"][-5:]] + \
                    [f"Session {_esc(s.get('date', ''))} · {_esc(str(s.get('summary', ''))[:160])}" for s in mem["summaries"][-3:]]
            st.markdown("<br>".join(lines), unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        if c1.button("Clear chat (summarise to memory)", width="stretch"):
            summarize_and_persist(ss.chat_history, api_key)
            ss.chat_history = []
            st.rerun()
        if c2.button("List available models", width="stretch"):
            st.code("\n".join(list_gemini_models(api_key)))
