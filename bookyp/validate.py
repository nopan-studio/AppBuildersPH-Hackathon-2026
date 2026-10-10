"""Validation rules -> status and review reasons.

Every rule that cannot be positively verified marks the receipt
``needs_review`` so a bad read is never silently accepted.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

TOLERANCE = 0.01
MIN_DATE = date(2000, 1, 1)

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
)


def _to_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def parse_date(value: Any) -> Optional[date]:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def validate(
    result: Dict[str, Any],
    min_conf: float = 0.80,
    today: Optional[date] = None,
) -> Tuple[str, List[str]]:
    """Return ``(status, reasons)`` for a normalized result dict."""
    reasons: List[str] = []
    today = today or date.today()
    max_date = today + timedelta(days=1)

    total = _to_float(result.get("total"))
    subtotal = _to_float(result.get("subtotal"))
    tax = _to_float(result.get("tax"))
    items = result.get("items") or []

    if total is None:
        reasons.append("total is missing")
    elif total <= 0:
        reasons.append("total is not greater than 0")

    item_amounts = [_to_float(item.get("amount")) for item in items]
    if subtotal is None:
        reasons.append("subtotal is missing")
    elif any(amount is None for amount in item_amounts):
        reasons.append("one or more item amounts are missing")
    elif abs(sum(item_amounts) - subtotal) > TOLERANCE:
        reasons.append("sum of item amounts does not equal subtotal")

    tax_inclusive = False
    if tax is None:
        reasons.append("tax is missing")
    elif subtotal is not None and total is not None:
        exclusive_ok = abs(subtotal + tax - total) <= TOLERANCE
        inclusive_ok = abs(subtotal - total) <= TOLERANCE
        if exclusive_ok:
            tax_inclusive = False
        elif inclusive_ok:
            # e.g. VAT/GST already baked into the printed subtotal and total.
            tax_inclusive = True
        else:
            reasons.append(
                "neither subtotal + tax nor subtotal alone equals total"
            )
    result["tax_inclusive"] = tax_inclusive

    parsed = parse_date(result.get("date"))
    if parsed is None:
        reasons.append("date is missing or not parseable")
    elif not (MIN_DATE <= parsed <= max_date):
        reasons.append("date is outside the plausible range")

    confidence = result.get("ocr_mean_conf")
    if confidence is None or confidence < min_conf:
        reasons.append("mean OCR confidence is below {:.2f}".format(min_conf))

    if not result.get("file"):
        reasons.append("file is missing")

    status = "accepted" if not reasons else "needs_review"
    return status, reasons
