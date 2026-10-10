"""bookyp: offline receipt OCR -> validated JSON.

The single entry point a future web API should call is :func:`process`.
"""

from .pipeline import process

__all__ = ["process"]
__version__ = "0.1.0"
