import re

files = {
    'data_fetchers.py': [
        (325, "possibly undefined _enforce_api_rate_limit"),
        (337, "possibly undefined _sanitize_error"),
        (553, "possibly undefined fred_series"),
        (670, "possibly undefined q"),
        (831, "possibly undefined bs_greeks_vectorized"),
        (964, "possibly undefined _get_iv_brentq_fallback"),
        (990, "possibly undefined _get_iv_brentq_fallback"),
        (998, "possibly undefined _get_iv_brentq_fallback"),
        (2178, "possibly undefined compute_max_pain"),
        (2180, "possibly undefined compute_pcr"),
        (22, "unused retry, retry_if_exception, stop_after_attempt, wait_exponential"),
        (2825, "unused gv"),
        (3651, "unused forward_eps"),
        (4690, "unused assets")
    ],
    'sentinel_app.py': [
        (8, "unused yf"),
        (17, "unused json, pd, re"),
        (23, "unused filter_market_news, get_ai_earnings_summary, get_expected_move, get_heatmap_data, get_margin_chart_data, get_sovereign_cds_proxy, get_stock_news"),
        (59, "unused get_memory_context")
    ],
    'ui_components.py': [
        (14, "unused px"),
        (19, "unused GEO_WEBCAM_FEEDS, market_snapshot_str")
    ]
}

for fname, bugs in files.items():
    with open(fname, 'r') as f:
        lines = f.readlines()
    
    # Process from bottom to top to avoid line numbers shifting
    for line_num, msg in sorted(bugs, key=lambda x: x[0], reverse=True):
        idx = line_num - 1
        lines.insert(idx, f"    # TODO (BUG): {msg}\n")
        
    with open(fname, 'w') as f:
        f.writelines(lines)

print("Done marking bugs.")
