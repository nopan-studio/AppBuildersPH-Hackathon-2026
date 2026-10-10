"""PP-OCRv6 wrapper.

Public surface:
    OcrEngine(tier).run(image) -> list[OcrLine]
    sort_and_merge(lines)      -> list[str]   (logical rows, top->bottom)

``paddleocr`` and NumPy are imported lazily so the ordering/merging logic can be
unit-tested without the OCR stack installed.
"""

from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import warnings
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

Box = Tuple[float, float, float, float]

# PP-OCRv6 hardware tiers exposed by PaddleOCR >= 3.7.
TIER_MODELS: Dict[str, Tuple[str, str]] = {
    "tiny": ("PP-OCRv6_tiny_det", "PP-OCRv6_tiny_rec"),
    "small": ("PP-OCRv6_small_det", "PP-OCRv6_small_rec"),
    "medium": ("PP-OCRv6_medium_det", "PP-OCRv6_medium_rec"),
}

OCR_TIERS: Tuple[str, ...] = tuple(TIER_MODELS)


class OcrError(RuntimeError):
    """Raised when the OCR engine cannot be built or run."""


@dataclass
class OcrLine:
    text: str
    confidence: float
    box: Box  # x0, y0, x1, y1


def _mkldnn_default() -> bool:
    """oneDNN is disabled by default: PaddlePaddle 3.3's PIR path raises
    ``ConvertPirAttribute2RuntimeAttribute`` on CPU. Set BOOKYP_OCR_MKLDNN=1
    to opt back in once the runtime is fixed."""
    return os.environ.get("BOOKYP_OCR_MKLDNN", "0").lower() in ("1", "true", "yes")


@contextlib.contextmanager
def _quiet_engine_build():
    """Silence PaddlePaddle/PaddleX import-time noise.

    Hides the root-logger "Creating model" INFO lines, the ccache warning (a
    bare ``which ccache`` whose stderr leaks), and stray Python warnings, while
    leaving model-download progress on stderr intact.
    """
    original_check_output = subprocess.check_output

    def _patched(*args: Any, **kwargs: Any) -> Any:
        command = args[0] if args else kwargs.get("args")
        if isinstance(command, (list, tuple)) and "ccache" in command:
            kwargs.setdefault("stderr", subprocess.DEVNULL)
        return original_check_output(*args, **kwargs)

    subprocess.check_output = _patched
    logging.disable(logging.INFO)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            yield
    finally:
        logging.disable(logging.NOTSET)
        subprocess.check_output = original_check_output


def _resolve_device(device: Optional[str]) -> str:
    """Return the requested device, or auto-detect CUDA (else CPU)."""
    if device and device != "auto":
        return device
    env = os.environ.get("BOOKYP_OCR_DEVICE")
    if env:
        return env
    try:
        import paddle

        if paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0:
            return "gpu:0"
    except Exception:  # pragma: no cover - depends on environment
        pass
    return "cpu"


class OcrEngine:
    """Thin adapter over ``paddleocr.PaddleOCR`` for a given model tier."""

    def __init__(
        self,
        tier: str = "small",
        enable_mkldnn: Optional[bool] = None,
        device: Optional[str] = None,
    ):
        if tier not in TIER_MODELS:
            raise OcrError(
                "unknown OCR tier {!r}; choose one of {}".format(
                    tier, ", ".join(OCR_TIERS)
                )
            )
        self.tier = tier
        self.enable_mkldnn = _mkldnn_default() if enable_mkldnn is None else enable_mkldnn
        self._predictor = self._build(tier, self.enable_mkldnn, device)

    def _build(self, tier: str, enable_mkldnn: bool, device: Optional[str]):
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        with _quiet_engine_build():
            try:
                from paddleocr import PaddleOCR
            except ImportError as exc:  # pragma: no cover - depends on env
                raise OcrError(
                    "paddleocr is required (pip install 'paddleocr>=3.7')"
                ) from exc

            self.device = _resolve_device(device)
            det_model, rec_model = TIER_MODELS[tier]
            common: Dict[str, Any] = {
                "text_detection_model_name": det_model,
                "text_recognition_model_name": rec_model,
                # We already deskew and only handle text, so skip extra models.
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "use_textline_orientation": False,
                "enable_mkldnn": enable_mkldnn,
                "device": self.device,
            }
            try:
                return PaddleOCR(**common)
            except TypeError:
                # Older paddleocr builds do not know ``enable_mkldnn``.
                common.pop("enable_mkldnn", None)
                try:
                    return PaddleOCR(**common)
                except (TypeError, ValueError) as exc:
                    raise OcrError(
                        "could not initialise PP-OCRv6 {} tier: {}".format(
                            tier, exc
                        )
                    ) from exc
            except ValueError as exc:
                raise OcrError(
                    "could not initialise PP-OCRv6 {} tier: {}".format(tier, exc)
                ) from exc

    def run(self, image) -> List[OcrLine]:
        """Run OCR on a ``PIL.Image`` or NumPy array and return lines."""
        try:
            import numpy as np
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise OcrError("NumPy is required (pip install numpy)") from exc

        if hasattr(image, "convert"):
            array = np.asarray(image.convert("RGB"))
        else:
            array = np.asarray(image)
            if array.ndim == 2:
                array = np.stack([array] * 3, axis=-1)

        predictor = self._predictor
        if hasattr(predictor, "predict"):
            return _parse_predict(list(predictor.predict(array)))
        if hasattr(predictor, "ocr"):  # PaddleOCR 2.x compatibility
            return _parse_legacy(predictor.ocr(array, cls=True))
        raise OcrError("paddleocr object exposes neither predict() nor ocr()")


def _get(obj: Any, key: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    try:
        return obj[key]
    except (KeyError, TypeError, IndexError):
        return getattr(obj, key, None)


def _box_from_poly(poly: Any) -> Box:
    try:
        import numpy as np

        arr = np.asarray(poly, dtype=np.float64).reshape(-1, 2)
    except Exception:  # pragma: no cover - malformed poly
        return (0.0, 0.0, 0.0, 0.0)
    xs = arr[:, 0]
    ys = arr[:, 1]
    return (float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max()))


def _parse_predict(results: Sequence[Any]) -> List[OcrLine]:
    """Parse PaddleOCR 3.x ``predict`` output."""
    lines: List[OcrLine] = []
    for result in results:
        texts = _get(result, "rec_texts")
        if texts is None:
            continue
        scores = _get(result, "rec_scores")
        polys = _get(result, "rec_polys")
        if polys is None:
            polys = _get(result, "dt_polys")
        boxes = _get(result, "rec_boxes")
        for index, text in enumerate(texts):
            confidence = 0.0
            if scores is not None and index < len(scores):
                try:
                    confidence = float(scores[index])
                except (TypeError, ValueError):
                    confidence = 0.0
            box = (0.0, 0.0, 0.0, 0.0)
            if polys is not None and index < len(polys):
                box = _box_from_poly(polys[index])
            elif boxes is not None and index < len(boxes):
                b = boxes[index]
                box = (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
            lines.append(OcrLine(str(text), confidence, box))
    return lines


def _parse_legacy(results: Any) -> List[OcrLine]:
    """Parse PaddleOCR 2.x ``ocr`` output: [[[box, (text, score)], ...]]."""
    lines: List[OcrLine] = []
    if not results:
        return lines
    for entry in results:
        if entry is None:
            continue
        for item in entry:
            try:
                box, payload = item[0], item[1]
                text, score = payload[0], payload[1]
            except (TypeError, IndexError, ValueError):
                continue
            lines.append(OcrLine(str(text), float(score), _box_from_poly(box)))
    return lines


def mean_confidence(lines: Sequence[OcrLine]) -> float:
    if not lines:
        return 0.0
    return sum(line.confidence for line in lines) / float(len(lines))


def _y_overlap(a: Box, b: Box) -> float:
    top = max(a[1], b[1])
    bottom = min(a[3], b[3])
    return max(0.0, bottom - top)


def sort_and_merge(lines: Sequence[OcrLine]) -> List[str]:
    """Sort lines into reading order and merge fragments that share a row."""
    if not lines:
        return []

    ordered = sorted(
        lines, key=lambda line: ((line.box[1] + line.box[3]) / 2.0, line.box[0])
    )

    rows: List[List[OcrLine]] = []
    current = [ordered[0]]
    current_box = ordered[0].box

    for line in ordered[1:]:
        overlap = _y_overlap(current_box, line.box)
        min_height = min(
            current_box[3] - current_box[1], line.box[3] - line.box[1]
        )
        if min_height <= 0:
            min_height = 1.0
        if overlap / min_height >= 0.5:
            current.append(line)
            current_box = (
                min(current_box[0], line.box[0]),
                min(current_box[1], line.box[1]),
                max(current_box[2], line.box[2]),
                max(current_box[3], line.box[3]),
            )
        else:
            rows.append(current)
            current = [line]
            current_box = line.box
    rows.append(current)

    merged: List[str] = []
    for row in rows:
        row_sorted = sorted(row, key=lambda line: line.box[0])
        text = " ".join(line.text for line in row_sorted if line.text).strip()
        if text:
            merged.append(text)
    return merged
