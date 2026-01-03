"""Sensitive data filtering and redaction."""

from __future__ import annotations

import re
from typing import Any

# Patterns that indicate a password/sensitive input context
SENSITIVE_WINDOW_PATTERNS = [
    r"(?i)password",
    r"(?i)sign\s*in",
    r"(?i)log\s*in",
    r"(?i)authenticate",
    r"(?i)credential",
    r"(?i)secret",
    r"(?i)token",
    r"(?i)api\s*key",
    r"(?i)private\s*key",
    r"(?i)\.env",
    r"(?i)keychain",
    r"(?i)1password",
    r"(?i)lastpass",
    r"(?i)bitwarden",
    r"(?i)dashlane",
]

# Patterns to redact from text before sending to LLMs
REDACTION_PATTERNS = [
    # API keys and tokens
    (r"(?i)(api[_-]?key|token|secret)[\"']?\s*[:=]\s*[\"']?[\w\-]+", "[REDACTED_API_KEY]"),
    # AWS keys
    (r"AKIA[0-9A-Z]{16}", "[REDACTED_AWS_KEY]"),
    (r"(?i)aws[_-]?(secret|access)[_-]?key[\"']?\s*[:=]\s*[\"']?[\w\-/+]+", "[REDACTED_AWS_SECRET]"),
    # Generic secrets in env format
    (r"(?i)^[A-Z_]+_(KEY|SECRET|TOKEN|PASSWORD)\s*=\s*.+$", "[REDACTED_ENV_VAR]"),
    # SSH private keys
    (r"-----BEGIN (?:RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----", "[REDACTED_PRIVATE_KEY]"),
    # Credit card numbers (basic pattern)
    (r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b", "[REDACTED_CARD]"),
    # Social security numbers
    (r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]"),
    # Email addresses (optional - uncomment if needed)
    # (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[REDACTED_EMAIL]"),
]

# Compiled patterns for performance
_sensitive_patterns = [re.compile(p) for p in SENSITIVE_WINDOW_PATTERNS]
_redaction_patterns = [(re.compile(p, re.MULTILINE), r) for p, r in REDACTION_PATTERNS]


def is_sensitive_context(window_title: str = "", app_name: str = "") -> bool:
    """Check if the current context appears to be sensitive (password entry, etc.)."""
    combined = f"{window_title} {app_name}"

    for pattern in _sensitive_patterns:
        if pattern.search(combined):
            return True

    return False


def mask_if_sensitive(text: str, is_sensitive: bool) -> str:
    """Mask text if in a sensitive context."""
    if is_sensitive:
        return "*" * len(text) if len(text) <= 20 else "*" * 20
    return text


def filter_sensitive_data(text: str) -> str:
    """Filter potentially sensitive data from text."""
    result = text

    for pattern, replacement in _redaction_patterns:
        result = pattern.sub(replacement, result)

    return result


def redact_for_llm(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Redact sensitive information from events before sending to LLM."""
    redacted = []

    for event in events:
        redacted_event = event.copy()

        # Redact keystroke data
        if event.get("event_type") == "keystroke":
            data = event.get("data", {})
            if data.get("masked"):
                # Already masked during capture
                pass
            elif "key" in data:
                data = data.copy()
                data["key"] = filter_sensitive_data(data["key"])
                redacted_event["data"] = data

        # Redact window titles that might contain sensitive info
        if event.get("event_type") == "window_change":
            data = event.get("data", {})
            if "window_title" in data:
                data = data.copy()
                data["window_title"] = filter_sensitive_data(data["window_title"])
                redacted_event["data"] = data

        redacted.append(redacted_event)

    return redacted


def is_env_file_content(text: str) -> bool:
    """Check if text appears to be .env file content."""
    lines = text.strip().split("\n")
    env_pattern = re.compile(r"^[A-Z_][A-Z0-9_]*\s*=")

    matches = sum(1 for line in lines if env_pattern.match(line.strip()))
    return matches > len(lines) * 0.5 if lines else False
