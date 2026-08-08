import requests
import os
import re
import time
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")

url = "https://api.groq.com/openai/v1/models"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

response = requests.get(url, headers=headers)
response.raise_for_status()

models = response.json()["data"]


def get_rate_limits(model_id):
    """
    Rate limits are per-org and per-model, and Groq returns them as
    response headers on every chat completion call -- this is the only
    reliable way to get exact numbers (docs explicitly say the exact
    values live on your account's limits page, not in a static table).
    We fire a minimal 1-token request just to read the headers.
    """
    chat_url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
    }
    try:
        r = requests.post(chat_url, headers=headers, json=payload, timeout=15)
    except requests.RequestException:
        return None

    h = r.headers
    return {
        "rpm_limit": h.get("x-ratelimit-limit-requests"),
        "rpm_remaining": h.get("x-ratelimit-remaining-requests"),
        "tpm_limit": h.get("x-ratelimit-limit-tokens"),
        "tpm_remaining": h.get("x-ratelimit-remaining-tokens"),
        "reset_requests": h.get("x-ratelimit-reset-requests"),
        "reset_tokens": h.get("x-ratelimit-reset-tokens"),
    }


def classify_type(model):
    """
    Derive a human-readable model type from input/output modalities.
    This is what actually tells you 'reasoning LLM' vs 'image-capable'
    vs 'speech' vs 'transcription' -- supported_features only tells you
    about *behavior* (json mode, tools, reasoning traces), not what kind
    of model it fundamentally is.
    """
    in_mod = set(model.get("input_modalities", []))
    out_mod = set(model.get("output_modalities", []))
    features = set(model.get("supported_features", []))

    if "transcription" in out_mod:
        return "speech-to-text"
    if "speech" in out_mod:
        return "text-to-speech"
    if "image" in in_mod and "text" in out_mod:
        return "vision-llm"
    if "text" in in_mod and "text" in out_mod:
        return "reasoning-llm" if "reasoning" in features else "text-llm"
    return "other"


def parse_param_count(model):
    """
    Groq's API doesn't expose parameter count anywhere -- not in the
    /models payload, not in headers. It's only visible baked into the
    model id/name itself (e.g. 'llama-3.3-70b-versatile', 'gpt-oss-20b',
    'llama-prompt-guard-2-22m'). We regex it out of id, falling back to
    name. Returns a display string, or '?' if the id has no size hint
    (e.g. 'whisper-large-v3', 'allam-2-7b' still matches fine, but
    something like 'groq/compound' has no param count at all).
    """
    for source in (model.get("id", ""), model.get("name", "")):
        match = re.search(r"(\d+(?:\.\d+)?)\s*([bBmM])(?![a-zA-Z])", source)
        if match:
            num, unit = match.groups()
            return f"{num}{unit.upper()}"
    return "?"


def flag(cond):
    return "✓" if cond else "✗"


# Column widths (+2 padding baked in so max-length values still get a gap)
COLS = [
    ("ID", 40),
    ("TYPE", 17),
    ("PARAMS", 8),
    ("STRUCT", 8),
    ("ACTIVE", 8),
    ("RPM", 8),
    ("TPM", 10),
]

header = "".join(f"{name:<{w}}" for name, w in COLS)
divider = "-" * len(header)

rows = []
total = len(models)

for idx, model in enumerate(models, start=1):
    is_active = bool(model.get("active"))
    model_type = classify_type(model)
    params = parse_param_count(model)
    features = set(model.get("supported_features", []))
    has_struct = "structured_outputs" in features

    # Live progress indicator -- overwrites the same line so you see
    # activity instead of a blank screen while we spend one real request
    # per active model (plus the 0.3s politeness sleep between calls).
    print(
        f"\r[{idx}/{total}] checking {model['id'][:50]:<50}",
        end="",
        flush=True,
    )

    # Only probe live headers for active chat/completions-style models.
    # Inactive models will error on the endpoint, and audio/speech models
    # use different endpoints entirely -- both just show n/a.
    if is_active and model_type in ("text-llm", "reasoning-llm", "vision-llm"):
        limits = get_rate_limits(model["id"])
        rpm = limits["rpm_limit"] if limits else "?"
        tpm = limits["tpm_limit"] if limits else "?"
        time.sleep(0.3)  # be polite, we're spending a real request per model
    else:
        rpm, tpm = "n/a", "n/a"

    # Numeric sort key: real TPM values first (highest first), n/a and
    # unknown values pushed to the bottom rather than sorting as 0.
    try:
        tpm_sort_key = int(tpm)
    except (ValueError, TypeError):
        tpm_sort_key = -1

    row = {
        "id": model["id"],
        "type": model_type,
        "params": params,
        "struct": has_struct,
        "active": is_active,
        "rpm": rpm,
        "tpm": tpm,
        "tpm_sort_key": tpm_sort_key,
    }
    rows.append(row)

    # Clear the progress line and print this row immediately, in
    # fetch order, so you get real-time feedback instead of waiting
    # for the whole list. The table header/divider print once, on
    # the first row.
    print("\r" + " " * 100 + "\r", end="")
    if idx == 1:
        print(header)
        print(divider)
    line = [
        row["id"][: COLS[0][1] - 1],
        row["type"],
        row["params"],
        flag(row["struct"]),
        flag(row["active"]),
        row["rpm"],
        row["tpm"],
    ]
    print("".join(f"{str(val):<{w}}" for val, (_, w) in zip(line, COLS)))

# Final pass: same data, sorted by TPM descending, since that's the
# order you actually want to read the results in. The live section
# above is fetch-order progress; this is the real summary table.
rows.sort(key=lambda r: r["tpm_sort_key"], reverse=True)

print("\n" + header)
print(divider)

for r in rows:
    line = [
        r["id"][: COLS[0][1] - 1],
        r["type"],
        r["params"],
        flag(r["struct"]),
        flag(r["active"]),
        r["rpm"],
        r["tpm"],
    ]
    print("".join(f"{str(val):<{w}}" for val, (_, w) in zip(line, COLS)))

active_count = sum(1 for r in rows if r["active"])
print(f"\nActive models: {active_count} / {len(models)}")
print("PARAMS parsed from the model id/name (Groq doesn't expose this via API).")
print("RPM/TPM = your account's current limit for that model, read live")
print("from response headers (x-ratelimit-limit-requests / -tokens).")
print("These are per-org, so they reflect free vs paid tier automatically.")
print("Sorted by TPM descending; n/a (inactive / non-chat models) sink to the bottom.")