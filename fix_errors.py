import re

with open("data_fetchers.py", "r") as f:
    content = f.read()

# Remove the st.session_state.api_error_count mutations
pattern_error = r"(\s+if 'api_error_count' not in st\.session_state:\n\s+st\.session_state\.api_error_count = 0\n\s+st\.session_state\.api_error_count \+= 1)"
content = re.sub(pattern_error, "", content)

# Remove the st.session_state.api_circuit_breaker part in _fetch_robust_json
# Let's replace it with a module-level variable
pattern_cb_init = r"    if 'api_circuit_breaker' not in st\.session_state:\n        st\.session_state\.api_circuit_breaker = {}\n        \n    cb = st\.session_state\.api_circuit_breaker\.setdefault\(api_name, \{\"failures\": 0, \"last_fail\": 0\}\)"

replacement_cb_init = """    global _API_CIRCUIT_BREAKERS
    if '_API_CIRCUIT_BREAKERS' not in globals():
        _API_CIRCUIT_BREAKERS = {}
    cb = _API_CIRCUIT_BREAKERS.setdefault(api_name, {"failures": 0, "last_fail": 0})"""
content = re.sub(pattern_cb_init, replacement_cb_init, content)

with open("data_fetchers.py", "w") as f:
    f.write(content)

print("Fixed api_error_count and api_circuit_breaker in data_fetchers.py")
