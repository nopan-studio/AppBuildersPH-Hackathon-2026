# Bookyp — Installation Manual

**Built for APPBuilders PH Hackathon 2026**

This manual walks through a full install of Bookyp: system prerequisites, Ollama
and its model, the Python environment, the PaddlePaddle runtime (CPU or NVIDIA
GPU), Bookyp itself, and the optional web UI.

Bookyp is developed and tested on Linux. Commands below use Arch/Omarchy package
names where a system package is needed; adapt them for your distro.

---

## 0. Prerequisites

| Software | Version | Notes |
|---|---|---|
| Python | 3.9 – 3.12 | 3.10–3.12 recommended. |
| Node.js | 18+ (npm) | Only needed to build/run the web UI. |
| Ollama | any recent | Provides the local LLM. |
| git | any | To clone the repo (if applicable). |
| NVIDIA driver | recent | Optional; for GPU acceleration. |

> **Note:** Python **3.13/3.14** are not supported by the PaddlePaddle/PaddleOCR
> wheels yet. Use 3.12.

---

## 1. Get the code

```bash
# if from git
git clone <repo-url> bookyp
cd bookyp

# or just cd into the project directory
cd /path/to/bookyp
```

Throughout this manual, run commands from the project root.

---

## 2. Install and start Ollama

Install Ollama from <https://ollama.com/download> or your package manager.

### Arch / Omarchy

```bash
sudo pacman -S ollama
sudo systemctl enable --now ollama
systemctl status ollama
```

### Other systems

Follow the official installer, then make sure the server is running
(`ollama serve` or the provided service).

### Pull the extraction model

```bash
ollama pull qwen3:1.7b
ollama list
```

> If your machine is limited, `qwen3:0.6b` is faster but less accurate on
> receipts; the default is `qwen3:1.7b`.

---

## 3. Create the Python environment

Using [uv](https://docs.astral.sh/uv/) (fast, recommended):

```bash
uv python install 3.12
uv venv --python 3.12 .venv
source .venv/bin/activate
```

Or with the standard library:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

---

## 4. Install Python dependencies

```bash
uv pip install -r requirements.txt
```

This installs Pillow, NumPy, PaddleOCR, the Ollama client, and (via the `web`
extra) FastAPI/Uvicorn for the API.

Then install the **PaddlePaddle runtime** — it is not pulled in automatically.

### CPU only

```bash
uv pip install paddlepaddle
```

### NVIDIA GPU (recommended for speed)

Choose the wheel index that matches your CUDA runtime. The examples below are
for PaddlePaddle 3.3.1 / Python 3.12:

```bash
# CUDA 13
uv pip install "paddlepaddle-gpu==3.3.1" \
  --index-url https://www.paddlepaddle.org.cn/packages/stable/cu130/

# or CUDA 12.9 / 12.6
# --index-url https://www.paddlepaddle.org.cn/packages/stable/cu129/
# --index-url https://www.paddlepaddle.org.cn/packages/stable/cu126/
```

Verify CUDA is visible to Paddle:

```bash
python -c "import paddle; print(paddle.device.is_compiled_with_cuda(), paddle.device.cuda.device_count())"
# expect: True 1
```

> For GPU **LLM** inference, Ollama must also have CUDA support. On Arch install
> `ollama-cuda` (which pulls `cuda`):
> ```bash
> sudo pacman -S ollama-cuda cuda
> sudo systemctl restart ollama
> ollama ps   # PROCESSOR column should read "100% GPU" after a scan
> ```

---

## 5. Install Bookyp

```bash
uv pip install -e .
bookyp --version
```

---

## 6. Verify the backend

```bash
bookyp check
# -> Ollama is up and 'qwen3:1.7b' is available

bookyp scan /path/to/a/receipt.jpg
```

`bookyp check` exits `0` when Ollama is reachable and the model is pulled,
`2` otherwise.

---

## 7. Build the web UI (optional)

```bash
cd web
npm install
npm run build      # produces web/dist, served by `bookyp serve`
cd ..
```

Run the app:

```bash
bookyp serve                    # API + UI on http://127.0.0.1:8000
bookyp serve --port 9000        # custom port
bookyp serve --reload           # auto-reload during backend development
```

Open <http://127.0.0.1:8000>.

### Frontend development mode

```bash
cd web
npm run dev                     # http://localhost:5173, proxies /api to :8000
```

---

## 8. Troubleshooting

| Problem | Cause / Fix |
|---|---|
| `No module named 'paddle'` | Install `paddlepaddle` (CPU) or `paddlepaddle-gpu` (see step 4). |
| `paddleocr is required` | `uv pip install -r requirements.txt`. |
| `cannot reach Ollama` | Start Ollama (`systemctl start ollama` / `ollama serve`) and `ollama pull qwen3:1.7b`. |
| `ConvertPirAttribute2RuntimeAttribute ... not support` | oneDNN/PIR bug in PaddlePaddle 3.3 on CPU. Bookyp disables oneDNN by default; do not set `BOOKYP_OCR_MKLDNN=1`. |
| `which: no ccache` warning | Harmless; install `ccache` to silence. |
| Blank web page | The UI requires **React 18**; Base Web 18 is not React-19 compatible. Reinstall with `cd web && npm install` (package.json pins React 18). |
| OCR running on CPU with a GPU present | You likely installed `paddlepaddle` instead of `paddlepaddle-gpu`; reinstall the GPU build. |
| Very slow scans (~1 min) | The LLM is CPU-bound. Enable GPU for Ollama (`ollama-cuda`) and PaddlePaddle-GPU. |
| `python -m venv` fails on Python 3.13+ | Use Python 3.12 via `uv python install 3.12`. |

---

## 9. Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `BOOKYP_OCR_DEVICE` | `auto` | Force OCR device: `cpu` or `gpu:0`. |
| `BOOKYP_OCR_MKLDNN` | `0` | Set `1` to re-enable oneDNN (PaddlePaddle 3.3 CPU bug workaround). |

---

## 10. Quick smoke test

```bash
source .venv/bin/activate
bookyp check
bookyp scan ./sample/ --debug
bookyp serve &          # then open http://127.0.0.1:8000
```

If `bookyp scan` prints JSON with a `status`, the install is complete.

---

**Built for APPBuilders PH Hackathon 2026.**
