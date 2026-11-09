"""Published standard token pricing for supported OpenAI models.

Prices are USD per million tokens; update when the provider changes rates.
The values calculate a nominal token charge from API-reported usage, not an
invoice amount. No tool calls, regional adjustments, or taxes are included.
"""

from __future__ import annotations

from typing import Any

PRICING_CHECKED = "2026-11-09"
PRICING_SOURCE = "https://developers.openai.com/api/docs/pricing"

# Efforts vary by model. Keeping a deliberately small supported set avoids
# exposing incompatible API options in the web interface.
MODELS: dict[str, dict[str, Any]] = {
    "gpt-6-luna": {
        "label": "GPT-6 Luna",
        "description": "Best starting point · inexpensive",
        "input": 0.10,
        "cached_input": 0.01,
        "output": 0.50,
        "efforts": ["none", "low", "medium", "high", "xhigh", "max"],
    },
    "gpt-6-sol": {
        "label": "GPT-6 Sol",
        "description": "Higher-cost reasoning",
        "input": 2.00,
        "cached_input": 0.20,
        "output": 10.00,
        "efforts": ["none", "low", "medium", "high", "xhigh", "max"],
    },
    "gpt-6.1-sol": {
        "label": "GPT-6.1 Sol",
        "description": "Current higher-capability option",
        "input": 2.00,
        "cached_input": 0.10,
        "output": 10.00,
        "efforts": ["low", "medium", "high", "xhigh", "max"],
    },
    "gpt-6.1-terra": {
        "label": "GPT-6.1 Terra",
        "description": "Mid-priced alternative",
        "input": 1.00,
        "cached_input": 0.05,
        "output": 5.00,
        "efforts": ["none", "low", "medium", "high", "xhigh", "max"],
    },
    "gpt-5-nano": {
        "label": "GPT-5 nano (legacy)",
        "description": "Lower-priced; deprecated, scheduled for removal Dec 11, 2026",
        "input": 0.05,
        "cached_input": 0.005,
        "output": 0.40,
        "efforts": ["low", "medium", "high"],
        "deprecated": True,
    },
}


def calculated_cost_usd(usage: dict[str, int] | None, model: str = "gpt-6-luna") -> float | None:
    """Calculate standard USD cost using measured token counts.

    Reasoning tokens are already included in output_tokens; do not add twice.
    Return None for unknown model prices or missing usage data.
    """
    rate = MODELS.get(model)
    if rate is None or usage is None:
        return None
    total_in = max(0, int(usage["input_tokens"]))
    cached = max(0, min(total_in, int(usage["cached_input_tokens"])))
    output = max(0, int(usage["output_tokens"]))
    return (
        (total_in - cached) * rate["input"]
        + cached * rate["cached_input"]
        + output * rate["output"]
    ) / 1_000_000


def public_catalog() -> list[dict[str, Any]]:
    """Return safe model metadata for the browser; never includes secrets."""
    return [{"id": name, **data} for name, data in MODELS.items()]
