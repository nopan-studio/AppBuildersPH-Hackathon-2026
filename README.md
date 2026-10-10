# Bookyp

**Offline receipt OCR → validated JSON, with a local LLM and a small React UI.**

<p align="center">
  <strong>Built for APPBuilders PH Hackathon 2026</strong>
</p>

Bookyp reads one receipt image (or a folder of them) and prints structured JSON —
merchant, date, currency, line items, subtotal, tax and total — plus a status.
It runs **fully offline**: OCR is handled by PP-OCRv6 via PaddleOCR, and field
extraction is done by a local model served by [Ollama](https://ollama.com).
Anything that fails validation is flagged `needs_review`, never silently accepted.

The OCR and the LLM run on the GPU when one is available, and fall back to CPU
automatically.

---

## Table of contents

- [What it does](#what-it-does)
- [Features](#features)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
  - [CLI](#cli)
  - [Web UI](#web-ui)
  - [HTTP API](#http-api)
- [Output schema](#output-schema)
- [Validation rules](#validation-rules)
- [Configuration](#configuration)
- [Performance](#performance)
- [Project layout](#project-layout)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [Credits](#credits)

---

## What it does

1. Cleans up the photo (grayscale, deskew, contrast, resize).
2. Runs PP-OCRv6 to get text lines with boxes and confidences.
3. Sorts the lines into reading order and merges fragments that share a row.
4. Asks a local LLM (`qwen3:1.7b` by default, JSON-schema constrained) to extract
   the receipt fields. The model is told never to guess.
5. Validates the numbers and the date.
6. Emits JSON with a `status` of `accepted` or `needs_review` and the reasons.

## Features

- **Offline & private** — no network calls at runtime; images never leave the machine.
- **Structured output** — a fixed JSON schema, not a wall of text.
- **Safe by default** — receipts that fail validation are marked `needs_review` with reasons.
- **Never guesses** — missing values are `null`; currency is only reported when the
  receipt actually shows an ISO code or an unambiguous symbol.
- **Tax-inclusive aware** — accepts both `subtotal + tax = total` and VAT/GST-included totals.
- **GPU accelerated** — Ollama (CUDA) and PaddlePaddle-GPU when available; CPU fallback.
- **CLI + Web** — the same core (`bookyp.pipeline.process`) powers both.
- **Folder batch** — scan a whole directory in one command.
- **Excel export** — download results as an `.xlsx` with a `Receipts` sheet and a
  normalized `Items` sheet, from the UI or via `--xlsx`.

## Architecture

```
                 ┌────────────┐
 image file ───▶ │ preprocess │  grayscale → deskew → contrast → resize
                 └─────┬──────┘
                       ▼
                 ┌────────────┐
                 │   ocr.py   │  PP-OCRv6 (PaddleOCR) → lines {text, conf, box}
                 └─────┬──────┘
                       ▼
                 ┌────────────┐
                 │ sort/merge │  reading order, same-row merge
                 └─────┬──────┘
                       ▼
                 ┌────────────┐
                 │ extract.py │  Ollama + JSON schema (qwen3:1.7b), retry once
                 └─────┬──────┘
                       ▼
                 ┌────────────┐
                 │ validate.py│  arithmetic / date / confidence rules
                 └─────┬──────┘
                       ▼
                  result dict  ──▶  CLI JSON  /  POST /api/scan  ──▶  React UI
```

`bookyp.pipeline.process()` is the single entry point the CLI, the API and any
future integration share.

## Requirements

| Component | Requirement |
|---|---|
| OS | Linux (tested on Arch/Omarchy). macOS/Windows should work but are untested. |
| Python | 3.9 – 3.12 (3.10+ recommended) |
| Node.js | 18+ (only for building/running the web UI) |
| Ollama | installed and running, with `qwen3:1.7b` pulled |
| RAM | ~4 GB free (CPU); a GPU with ~2 GB VRAM helps a lot |
| Disk | ~6 GB for the Paddle runtime + models |

## Installation

See **[INSTALL.md](INSTALL.md)** for the full step-by-step guide (system
packages, Ollama, Python venv, CPU vs GPU PaddlePaddle, and the frontend).

Quick version:

```bash
# 1. Ollama + model
ollama pull qwen3:1.7b

# 2. Python venv (uv or python -m venv)
uv venv --python 3.12 .venv
source .venv/bin/activate

# 3. Python deps + Paddle runtime
uv pip install -r requirements.txt
uv pip install paddlepaddle            # CPU
#   or, for NVIDIA GPUs (CUDA 13):
#   uv pip install "paddlepaddle-gpu==3.3.1" \
#       --index-url https://www.paddlepaddle.org.cn/packages/stable/cu130/

# 4. Install Bookyp itself
uv pip install -e .

# 5. Web UI (optional)
cd web && npm install && npm run build && cd ..
```

## Usage

### CLI

```
bookyp scan <path>          # image file or folder
bookyp check                # verify Ollama + model are available
bookyp serve                # run the web API + UI
bookyp --version
```

`scan` flags:

| Flag | Default | Description |
|---|---|---|
| `--model` | `qwen3:1.7b` | Ollama model name |
| `--ocr-tier` | `small` | PP-OCRv6 tier: `tiny` \| `small` \| `medium` |
| `--out` | stdout | Write JSON to a file |
| `--xlsx` | — | Also write results to an Excel (`.xlsx`) file |
| `--min-conf` | `0.80` | Mean OCR confidence threshold |
| `--debug` | off | Print raw OCR lines and the LLM response to stderr |

Exit codes:

| Code | Meaning |
|---|---|
| `0` | All receipts accepted |
| `1` | At least one `needs_review` |
| `2` | Error (bad path, Ollama down, OCR init failed, …) |

Examples:

```bash
bookyp check
bookyp scan receipt.jpg
bookyp scan ./receipts/ --out results.json
bookyp scan receipt.jpg --debug
bookyp scan receipt.jpg --ocr-tier medium --model qwen3:1.7b
```

### Web UI

```bash
bookyp serve            # serves API + built UI on http://127.0.0.1:8000
```

Then open <http://127.0.0.1:8000>. Drag in receipt images, optionally adjust the
model / OCR tier / confidence, and press **Scan**. Results show as cards with a
status tag, a line-item table and the raw JSON.

For frontend development (hot reload, proxies `/api` to the backend):

```bash
cd web
npm run dev             # http://localhost:5173
```

The UI is built with Uber's **Base Design System** (Base Web `baseui`) on React 18.

### HTTP API

| Method | Path | Body | Returns |
|---|---|---|---|
| `GET` | `/api/health` | — | `{ ok, message, model }` |
| `POST` | `/api/scan` | multipart: `files`, `model`, `ocr_tier`, `min_conf` | `{ model, ocr_tier, ocr_device, results: [...] }` |
| `POST` | `/api/export` | JSON: `{ results: [...] }` | `.xlsx` file download |

```bash
curl -F "files=@receipt.jpg" -F "ocr_tier=small" \
     http://127.0.0.1:8000/api/scan

curl -X POST http://127.0.0.1:8000/api/export \
     -H 'Content-Type: application/json' \
     -d '{"results": [...]}' -o bookyp-results.xlsx
```

The exported workbook contains a **Receipts** sheet (one row per receipt) and an
**Items** sheet (one row per line item, linked by file name).

## Output schema

```json
{
  "file": "receipt.jpg",
  "merchant": "GREEN LEAF CAFE",
  "date": "2024-03-05",
  "currency": "USD",
  "items": [
    { "name": "Latte", "qty": 2, "unit_price": 3.0, "amount": 6.0 },
    { "name": "Bagel", "qty": 1, "unit_price": 2.5, "amount": 2.5 }
  ],
  "subtotal": 8.5,
  "tax": 0.68,
  "total": 9.18,
  "tax_inclusive": false,
  "ocr_mean_conf": 0.9987,
  "status": "accepted",
  "review_reasons": []
}
```

Fields that are not present on the receipt are `null`. `status` is
`accepted` or `needs_review`; `review_reasons` lists why a receipt was flagged.

## Validation rules

A receipt is `accepted` only when **all** of these hold (tolerance `0.01`):

- `total` is present and greater than `0`.
- The sum of item `amount`s equals `subtotal`.
- Either `subtotal + tax = total` **or** `subtotal = total` (tax-inclusive/VAT),
  recorded via `tax_inclusive`.
- `date` parses and falls within a plausible range (2000-01-01 → tomorrow).
- `ocr_mean_conf` ≥ `--min-conf`.
- `file` is present.

Any failure sets `needs_review` and records the reason.

## Configuration

| Setting | How |
|---|---|
| OCR device | Auto (GPU if available). Override with `BOOKYP_OCR_DEVICE=cpu` or `gpu:0`. |
| oneDNN | Off by default (PaddlePaddle 3.3 CPU bug). Re-enable with `BOOKYP_OCR_MKLDNN=1`. |
| Model | `--model <name>` on `scan`, or the field in the UI. |
| OCR tier | `--ocr-tier tiny\|small\|medium`. |

## Performance

Measured on an Intel i5-9300H + NVIDIA GTX 1650 (4 GB), per receipt:

| Stage | CPU only | With GPU |
|---|---|---|
| Preprocess | ~0.5 s | ~0.5 s |
| OCR (PP-OCRv6 small) | ~14 s | ~1.4 s |
| LLM (qwen3:1.7b) | ~45 s | ~5 s |
| **Total** | **~65 s** | **~12 s** |

The first run of a session also builds the models once (~3–4 s). The LLM needs
the model loaded; Ollama keeps it warm for a few minutes.

## Project layout

```
bookyp/
  __init__.py        # exports process()
  cli.py             # argparse entry point (scan / check / serve)
  preprocess.py      # image cleanup
  ocr.py             # PP-OCRv6 wrapper + line sort/merge
  extract.py         # Ollama structured extraction + retry
  validate.py        # rules -> status + reasons
  pipeline.py        # process() -> validated result dict
  export.py          # results -> .xlsx workbook
  api.py             # FastAPI app (GET /api/health, POST /api/scan)
api tests in tests/
web/                 # React + Base Web UI (Vite)
  src/App.jsx        # upload, scan, results
  src/theme.js       # Base Web theme (black primary)
  src/api.js         # fetch helpers
pyproject.toml
requirements.txt
```

## Testing

```bash
python -m unittest discover -s tests
```

33 tests cover validation rules, OCR line ordering, number/currency
normalization, Excel export, the CLI parser and the API routes. They use stdlib
`unittest` and skip API/export tests if their optional dependencies are missing.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `check` says model missing | `ollama pull qwen3:1.7b`; ensure `systemctl status ollama` is active |
| Browser page is blank | Ensure the frontend uses **React 18** (Base Web 18 is not React-19 compatible) |
| Paddle error `ConvertPirAttribute2RuntimeAttribute` | oneDNN bug — the default `BOOKYP_OCR_MKLDNN=0` avoids it |
| OCR runs on CPU despite a GPU | install `paddlepaddle-gpu` (not `paddlepaddle`) and check `nvidia-smi` |
| `which: no ccache` on startup | harmless; install `ccache` to silence it |
| Slow (~1 min) scans | LLM is CPU-bound; enable Ollama CUDA and PaddlePaddle-GPU |

## Roadmap

- v0.2: batch scoring harness, more languages/currencies, richer review UI.
- Later: optional fine-tuned extraction model, multi-page documents.

## Credits

**Built for APPBuilders PH Hackathon 2026.**

Built with [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR),
[Ollama](https://ollama.com), [Uber Base Web](https://baseweb.design),
[FastAPI](https://fastapi.tiangolo.com) and [Vite](https://vite.dev).
