"""End-to-end pipeline: image path -> validated result dict.

``process()`` is the single function a future web API would call. It composes
preprocess -> OCR -> extraction -> validation and returns exactly the schema
documented in the spec.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from . import extract, ocr, preprocess, validate

DEFAULT_MODEL = extract.DEFAULT_MODEL
DEFAULT_MIN_CONF = 0.80

_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}


class PipelineError(RuntimeError):
    """Raised for unrecoverable problems (bad path, OCR/LLM unavailable)."""


def empty_result(filename: str) -> Dict[str, Any]:
    return {
        "file": filename,
        "merchant": None,
        "date": None,
        "currency": None,
        "items": [],
        "subtotal": None,
        "tax": None,
        "total": None,
        "tax_inclusive": False,
        "ocr_mean_conf": 0.0,
        "status": "needs_review",
        "review_reasons": [],
    }


def list_images(path: str) -> List[str]:
    """Return a sorted list of image files for a file or directory path."""
    if os.path.isdir(path):
        found = [
            os.path.join(path, name)
            for name in os.listdir(path)
            if os.path.splitext(name)[1].lower() in _IMAGE_EXTENSIONS
            and os.path.isfile(os.path.join(path, name))
        ]
        return sorted(found)
    return [path]


def process(
    image_path: str,
    model: str = DEFAULT_MODEL,
    ocr_tier: str = "small",
    min_conf: float = DEFAULT_MIN_CONF,
    debug: bool = False,
    ocr_engine: Optional[ocr.OcrEngine] = None,
) -> Dict[str, Any]:
    """Process one receipt image and return a validated result dict."""
    if not os.path.isfile(image_path):
        raise PipelineError("not a file: {!r}".format(image_path))

    result = empty_result(os.path.basename(image_path))
    debug_info: Dict[str, Any] = {}

    cleaned = preprocess.preprocess_image(image_path)

    engine = ocr_engine or ocr.OcrEngine(ocr_tier)
    lines = engine.run(cleaned)
    result["ocr_mean_conf"] = round(ocr.mean_confidence(lines), 4)

    ordered_text = ocr.sort_and_merge(lines)
    if debug:
        debug_info["ocr_lines"] = ordered_text

    if not ordered_text:
        result["review_reasons"].append("no OCR text detected")
        result["status"] = "needs_review"
        _attach_debug(result, debug, debug_info)
        return result

    extracted, raw, error = extract.extract("\n".join(ordered_text), model=model)
    if debug:
        debug_info["llm_response"] = raw
    if extracted is None:
        result["review_reasons"].append(
            error or "model did not return valid structured output"
        )
        result["status"] = "needs_review"
        _attach_debug(result, debug, debug_info)
        return result

    _normalize(result, extracted, "\n".join(ordered_text))
    status, reasons = validate.validate(result, min_conf=min_conf)
    result["status"] = status
    result["review_reasons"] = reasons
    _attach_debug(result, debug, debug_info)
    return result


def _attach_debug(
    result: Dict[str, Any], debug: bool, debug_info: Dict[str, Any]
) -> None:
    if debug:
        result["_debug"] = debug_info


def _clean_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# Currency symbols that map to exactly one ISO 4217 code.
_CURRENCY_SYMBOLS = {
    "\u20ac": "EUR",  # euro sign
    "\u00a3": "GBP",  # pound sign
    "\u20b9": "INR",  # Indian rupee sign
    "\u20b1": "PHP",  # Philippine peso sign
}


def _currency_grounded(code: str, source_text: str) -> bool:
    """True when ``code`` is literally supported by the OCR text."""
    if not source_text:
        return False
    pattern = r"(?<![A-Za-z])" + re.escape(code) + r"(?![A-Za-z])"
    if re.search(pattern, source_text, re.IGNORECASE):
        return True
    return any(
        mapped == code and symbol in source_text
        for symbol, mapped in _CURRENCY_SYMBOLS.items()
    )


def _normalize_currency(value: Any, source_text: str = "") -> Optional[str]:
    """Keep an uppercase ISO 4217 code only if the receipt actually supports it.

    Enforces the "never guess" rule: the model may return a plausible code
    (e.g. USD) when the receipt only shows an ambiguous marker, so anything not
    grounded in the OCR text becomes null.
    """
    text = _clean_str(value)
    if text is None:
        return None
    code = text.upper()
    if not re.fullmatch(r"[A-Z]{3}", code):
        return None
    return code if _currency_grounded(code, source_text) else None


def _normalize_separators(text: str) -> str:
    """Turn ``1,234.56`` / ``1.234,56`` into a plain float-literal string."""
    if "," in text and "." in text:
        if text.rfind(".") > text.rfind(","):
            return text.replace(",", "")
        return text.replace(".", "").replace(",", ".")

    separator = "," if "," in text else ("." if "." in text else "")
    if not separator:
        return text
    if text.count(separator) > 1:
        return text.replace(separator, "")
    head, _, tail = text.rpartition(separator)
    if len(tail) == 3 and head:
        return head + tail
    return head + "." + tail


def _to_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    text = re.sub(r"[^0-9,.\-]", "", text)
    if not text:
        return None
    text = _normalize_separators(text)
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


def _normalize(
    result: Dict[str, Any], data: Dict[str, Any], source_text: str = ""
) -> None:
    result["merchant"] = _clean_str(data.get("merchant"))
    result["date"] = _clean_str(data.get("date"))
    result["currency"] = _normalize_currency(data.get("currency"), source_text)

    items: List[Dict[str, Any]] = []
    raw_items = data.get("items")
    if isinstance(raw_items, list):
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            name = _clean_str(raw_item.get("name"))
            qty = _to_float(raw_item.get("qty"))
            unit_price = _to_float(raw_item.get("unit_price"))
            amount = _to_float(raw_item.get("amount"))
            if name is None and amount is None and unit_price is None:
                continue
            if qty is not None and float(qty).is_integer():
                qty = int(qty)
            items.append(
                {
                    "name": name or "",
                    "qty": qty,
                    "unit_price": unit_price,
                    "amount": amount,
                }
            )
    result["items"] = items
    result["subtotal"] = _to_float(data.get("subtotal"))
    result["tax"] = _to_float(data.get("tax"))
    result["total"] = _to_float(data.get("total"))
