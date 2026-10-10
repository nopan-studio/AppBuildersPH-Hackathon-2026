"""Ollama structured extraction: OCR text -> dict.

The Ollama client is imported lazily. The JSON schema is passed to Ollama's
``format`` parameter so the model is constrained to valid JSON, and
``temperature`` is pinned to 0. The model is instructed never to guess.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_MODEL = "qwen3:1.7b"

_NULLABLE_STRING: Dict[str, Any] = {
    "anyOf": [{"type": "string"}, {"type": "null"}]
}
_NULLABLE_NUMBER: Dict[str, Any] = {
    "anyOf": [{"type": "number"}, {"type": "null"}]
}

EXTRACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "merchant": _NULLABLE_STRING,
        "date": _NULLABLE_STRING,
        "currency": _NULLABLE_STRING,
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "qty": _NULLABLE_NUMBER,
                    "unit_price": _NULLABLE_NUMBER,
                    "amount": _NULLABLE_NUMBER,
                },
                "required": ["name", "qty", "unit_price", "amount"],
            },
        },
        "subtotal": _NULLABLE_NUMBER,
        "tax": _NULLABLE_NUMBER,
        "total": _NULLABLE_NUMBER,
    },
    "required": [
        "merchant",
        "date",
        "currency",
        "items",
        "subtotal",
        "tax",
        "total",
    ],
}

SYSTEM_PROMPT = """You extract structured data from OCR text of a single receipt.
Return JSON that matches the supplied schema exactly.

Rules:
- Use only values that appear in the OCR text.
- Never guess, infer or invent a value. If a field is not present, return null.
- The date, when present, must be ISO format YYYY-MM-DD.
- Numeric fields are plain numbers: no currency symbols and no thousands separators.
- "items" is an array; use [] when no line items are present.
- "amount" is a line total, "unit_price" is the price per unit, "qty" the quantity.
- "currency" must only be reported when the receipt itself makes it explicit:
  * use a 3-letter ISO 4217 code when that code is printed (e.g. "PHP", "USD", "EUR");
  * a single-currency symbol may be mapped (e.g. "\u20ac" -> EUR, "\u00a3" -> GBP,
    "\u20b9" -> INR);
  * for ambiguous symbols (e.g. "$", "P", "\u00a5") return null unless the ISO code
    is also printed;
  * never infer the currency from the country, address, language, merchant or timezone.
"""


class ExtractError(RuntimeError):
    """Raised when the extraction model is unavailable or misbehaves."""


def build_prompt(ocr_text: str) -> str:
    lines = [
        "OCR text (one line per row, top to bottom):",
        ocr_text.strip(),
        "",
        "Extract the fields: merchant, date, currency, "
        "items[name, qty, unit_price, amount], subtotal, tax, total.",
        "Return JSON only.",
    ]
    return "\n".join(lines)


def extract(
    ocr_text: str, model: str = DEFAULT_MODEL
) -> Tuple[Optional[Dict[str, Any]], str, Optional[str]]:
    """Run the model and parse its reply.

    Returns ``(parsed_or_none, raw_response, error)``. The model is called at
    most twice: one retry if the first reply cannot be parsed as JSON.
    """
    prompt = build_prompt(ocr_text)
    last_raw = ""
    last_error: Optional[str] = None

    for _ in range(2):
        raw = _chat(model, prompt)
        last_raw = raw or ""
        parsed, error = _parse(raw)
        if parsed is not None:
            return parsed, last_raw, None
        last_error = error

    return None, last_raw, last_error or "model did not return valid JSON"


def _chat(model: str, prompt: str) -> str:
    try:
        from ollama import Client
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ExtractError(
            "ollama python client is required (pip install ollama)"
        ) from exc

    client = Client()
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "format": EXTRACTION_SCHEMA,
        "options": {"temperature": 0},
        "stream": False,
        "think": False,
    }
    try:
        response = client.chat(**kwargs)
    except TypeError:
        # Older ollama clients do not know the ``think`` parameter.
        kwargs.pop("think", None)
        response = client.chat(**kwargs)
    except Exception as exc:  # pragma: no cover - network/server side
        raise ExtractError("Ollama request failed: {}".format(exc)) from exc
    return _content(response)


def _content(response: Any) -> str:
    message = None
    if isinstance(response, dict):
        message = response.get("message")
    if message is None:
        message = getattr(response, "message", None)
    if isinstance(message, dict):
        return message.get("content") or ""
    return getattr(message, "content", "") or ""


def _parse(raw: Optional[str]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not raw:
        return None, "empty response from model"
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            first, rest = text.split("\n", 1)
            if first.strip().lower() in ("json", ""):
                text = rest
        text = text.strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        return None, "response was not valid JSON: {}".format(exc)
    if not isinstance(data, dict):
        return None, "response JSON was not an object"
    return data, None


def ollama_reachable() -> Tuple[bool, str]:
    try:
        from ollama import Client
    except ImportError as exc:
        return False, "ollama python client is not installed: {}".format(exc)
    try:
        Client().list()
    except Exception as exc:
        return False, "cannot reach Ollama: {}".format(exc)
    return True, "Ollama is reachable"


def _model_names(client) -> List[str]:
    listing = client.list()
    models = None
    if isinstance(listing, dict):
        models = listing.get("models")
    if models is None:
        models = getattr(listing, "models", []) or []
    names: List[str] = []
    for entry in models:
        if isinstance(entry, dict):
            name = entry.get("model") or entry.get("name")
        else:
            name = getattr(entry, "model", None) or getattr(entry, "name", None)
        if name:
            names.append(str(name))
    return names


def check_ollama(model: str = DEFAULT_MODEL) -> Tuple[bool, str]:
    """Return ``(ok, message)``; ok requires Ollama up and ``model`` present."""
    try:
        from ollama import Client
    except ImportError as exc:
        return False, "ollama python client is not installed: {}".format(exc)
    client = Client()
    try:
        names = _model_names(client)
    except Exception as exc:
        return False, "cannot reach Ollama: {}".format(exc)

    wanted = {model}
    if ":" not in model:
        wanted.add(model + ":latest")
    for name in names:
        if name in wanted:
            return True, "Ollama is up and {!r} is available".format(model)
        if ":" not in model and name.split(":", 1)[0] == model:
            return True, "Ollama is up and {!r} is available".format(name)
    return False, "Ollama is up but model {!r} is not pulled (run: ollama pull {})".format(
        model, model
    )
