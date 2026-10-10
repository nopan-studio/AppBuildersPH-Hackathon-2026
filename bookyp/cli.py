"""argparse entry point for bookyp."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

from . import __version__, export, extract, ocr, pipeline

EXIT_OK = 0
EXIT_NEEDS_REVIEW = 1
EXIT_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bookyp",
        description="Read receipt images offline and print validated JSON.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="scan an image file or a folder")
    scan.add_argument("path", help="image file or directory of images")
    scan.add_argument(
        "--model", default=extract.DEFAULT_MODEL, help="Ollama model name"
    )
    scan.add_argument(
        "--ocr-tier",
        choices=list(ocr.OCR_TIERS),
        default="small",
        help="PP-OCRv6 model tier (default: small)",
    )
    scan.add_argument("--out", help="write JSON here (default: stdout)")
    scan.add_argument(
        "--min-conf",
        type=float,
        default=pipeline.DEFAULT_MIN_CONF,
        help="mean OCR confidence threshold (default: 0.80)",
    )
    scan.add_argument(
        "--debug",
        action="store_true",
        help="print raw OCR lines and the LLM response to stderr",
    )
    scan.add_argument(
        "--xlsx",
        metavar="FILE",
        help="also write the results to an Excel (.xlsx) file",
    )

    check = subparsers.add_parser(
        "check", help="verify Ollama is reachable and the model is pulled"
    )
    check.add_argument(
        "--model", default=extract.DEFAULT_MODEL, help="Ollama model name"
    )

    serve = subparsers.add_parser("serve", help="run the web API + UI")
    serve.add_argument("--host", default="127.0.0.1", help="bind host")
    serve.add_argument("--port", type=int, default=8000, help="bind port")
    serve.add_argument(
        "--reload", action="store_true", help="auto-reload on code changes"
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "check":
        return _cmd_check(args)
    if args.command == "serve":
        return _cmd_serve(args)
    return _cmd_scan(args)


def _cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        print(
            "error: web dependencies missing (pip install 'fastapi' "
            "'uvicorn[standard]' 'python-multipart')",
            file=sys.stderr,
        )
        return EXIT_ERROR
    uvicorn.run(
        "bookyp.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return EXIT_OK


def _cmd_check(args: argparse.Namespace) -> int:
    ok, message = extract.check_ollama(args.model)
    print(message, file=sys.stderr if not ok else sys.stdout)
    return EXIT_OK if ok else EXIT_ERROR


def _cmd_scan(args: argparse.Namespace) -> int:
    if not os.path.exists(args.path):
        print("error: path does not exist: {}".format(args.path), file=sys.stderr)
        return EXIT_ERROR

    files = pipeline.list_images(args.path)
    if not files:
        print("error: no images found in {}".format(args.path), file=sys.stderr)
        return EXIT_ERROR

    ok, message = extract.check_ollama(args.model)
    if not ok:
        print("error: {}".format(message), file=sys.stderr)
        return EXIT_ERROR

    try:
        engine = ocr.OcrEngine(args.ocr_tier)
    except ocr.OcrError as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return EXIT_ERROR

    results: List[Dict[str, Any]] = []
    total = len(files)
    for index, path in enumerate(files, start=1):
        print(
            "processing {} ({}/{})...".format(
                os.path.basename(path), index, total
            ),
            file=sys.stderr,
        )
        try:
            result = pipeline.process(
                path,
                model=args.model,
                ocr_tier=args.ocr_tier,
                min_conf=args.min_conf,
                debug=args.debug,
                ocr_engine=engine,
            )
        except pipeline.PipelineError as exc:
            print("error: {}: {}".format(path, exc), file=sys.stderr)
            return EXIT_ERROR
        except (ocr.OcrError, extract.ExtractError) as exc:
            print("error: {}: {}".format(path, exc), file=sys.stderr)
            return EXIT_ERROR

        debug_info = result.pop("_debug", None)
        if debug_info is not None:
            _print_debug(debug_info)
        results.append(result)

    payload: Any = results[0] if os.path.isfile(args.path) else results
    _emit(payload, args.out)

    if args.xlsx:
        try:
            export.write_xlsx(results, args.xlsx)
        except export.ExportError as exc:
            print("error: {}".format(exc), file=sys.stderr)
            return EXIT_ERROR
        print("wrote {}".format(args.xlsx), file=sys.stderr)

    if any(item["status"] != "accepted" for item in results):
        return EXIT_NEEDS_REVIEW
    return EXIT_OK


def _emit(payload: Any, out: Optional[str]) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if out:
        with open(out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    else:
        print(text)


def _print_debug(debug_info: Dict[str, Any]) -> None:
    lines = debug_info.get("ocr_lines", [])
    print("[debug] OCR lines ({}):".format(len(lines)), file=sys.stderr)
    for line in lines:
        print("  {}".format(line), file=sys.stderr)
    print("[debug] LLM response:", file=sys.stderr)
    print(debug_info.get("llm_response", ""), file=sys.stderr)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
