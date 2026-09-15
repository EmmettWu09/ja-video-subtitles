"""Small OpenAI-compatible request options and safe error formatting."""

import re
from urllib.parse import urlsplit


def chat_options(cfg) -> dict:
    """Return provider-specific chat options based on the configured hostname."""
    # DeepSeek enables thinking by default. Subtitle transformations need the
    # final text only; leave other OpenAI-compatible providers unchanged.
    if urlsplit(cfg.base_url).hostname == "api.deepseek.com":
        return {"extra_body": {"thinking": {"type": "disabled"}}}
    return {}


def safe_error(error, api_key: str = "") -> str:
    """Redact the configured key and sk-prefixed key patterns from an error."""
    message = str(error)
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    return re.sub(r"\bsk-[A-Za-z0-9_-]{8,}", "[REDACTED]", message)
