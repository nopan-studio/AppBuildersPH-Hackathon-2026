"""Image cleanup for receipt OCR.

Pipeline: grayscale -> deskew -> contrast -> resize (long edge ~1600 px).

Heavy imports (Pillow, NumPy) are done lazily so that the rest of the package
can be imported, and unit-tested, on a machine without the OCR dependencies.
"""

from __future__ import annotations

from typing import Optional, Tuple

DEFAULT_LONG_EDGE = 1600

_SKEW_MAX_ANGLE = 10.0
_SKEW_STEP = 0.5
_SKEW_SAMPLE_EDGE = 600


class PreprocessError(RuntimeError):
    """Raised when an image cannot be loaded or cleaned."""


def preprocess_image(
    path: str,
    target_long_edge: int = DEFAULT_LONG_EDGE,
):
    """Load ``path`` and return a cleaned grayscale ``PIL.Image``."""
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise PreprocessError(
            "Pillow is required for preprocessing (pip install pillow)"
        ) from exc

    try:
        with Image.open(path) as raw:
            raw.load()
            img = ImageOps.exif_transpose(raw)
            gray = img.convert("L")
    except (OSError, ValueError) as exc:
        raise PreprocessError("cannot read image {!r}: {}".format(path, exc)) from exc

    angle = estimate_skew_angle(gray)
    if abs(angle) >= _SKEW_STEP:
        gray = gray.rotate(
            angle, resample=Image.BILINEAR, expand=True, fillcolor=255
        )

    gray = ImageOps.autocontrast(gray, cutoff=1)
    return resize_long_edge(gray, target_long_edge)


def estimate_skew_angle(gray) -> float:
    """Estimate the skew of ``gray`` by maximising the row-projection variance."""
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise PreprocessError(
            "NumPy is required for deskewing (pip install numpy)"
        ) from exc

    from PIL import Image

    width, height = gray.size
    long_edge = max(width, height)
    if long_edge == 0:
        return 0.0

    if long_edge > _SKEW_SAMPLE_EDGE:
        scale = _SKEW_SAMPLE_EDGE / float(long_edge)
        sample = gray.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))),
            Image.BILINEAR,
        )
    else:
        sample = gray

    base = np.asarray(sample, dtype=np.float32)
    threshold = float(base.mean() - 0.3 * base.std())

    best_angle = 0.0
    best_score = -1.0
    steps = int(round((2 * _SKEW_MAX_ANGLE) / _SKEW_STEP))
    for index in range(steps + 1):
        angle = -_SKEW_MAX_ANGLE + index * _SKEW_STEP
        rotated = sample.rotate(
            angle, resample=Image.BILINEAR, expand=False, fillcolor=255
        )
        arr = np.asarray(rotated, dtype=np.float32)
        rows = (arr < threshold).sum(axis=1).astype(np.float32)
        score = float(((rows - rows.mean()) ** 2).mean())
        if score > best_score:
            best_score = score
            best_angle = angle
    return best_angle


def resize_long_edge(img, target: int):
    """Scale ``img`` so its long edge is ``target`` pixels."""
    from PIL import Image

    width, height = img.size
    long_edge = max(width, height)
    if long_edge == 0 or long_edge == target:
        return img
    scale = target / float(long_edge)
    size: Tuple[int, int] = (
        max(1, int(round(width * scale))),
        max(1, int(round(height * scale))),
    )
    resample = Image.LANCZOS if scale < 1 else Image.BICUBIC
    return img.resize(size, resample)
