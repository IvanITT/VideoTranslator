# Installation guide (Windows)

This guide installs Spanish Dubbing Studio from a clean Windows 10/11 machine.
The automated path takes one command; the manual path is documented for
machines without internet access or with an existing Python/FFmpeg setup.

## 1. Requirements

| Item | Recommended | Why |
|---|---|---|
| Windows | 10 22H2 or 11, 64-bit | Tested platform |
| Python | **3.11.x 64-bit** | Pinned wheels for torch 2.5.1, CTranslate2, ONNX Runtime |
| Node.js | 20 LTS or 22 LTS | Builds the React interface (not needed at runtime) |
| RAM | 8 GB minimum, 16 GB comfortable | Whisper + translation models |
| CPU | 4 threads | 2-core CPUs work but are slow |
| Disk | 6 GB free | venv ~2.5 GB, FFmpeg ~0.3 GB, models ~0.6 GB, working space |
| GPU | optional NVIDIA CUDA | The setup installs the CPU build; CUDA is not the tested path |
| Internet | only for setup/model downloads | Processing is offline afterwards |

Python **3.13 is not supported** by the pinned `torch==2.5.1` /
`ctranslate2` wheels. If `py -3.13` is your default, the setup script still
finds 3.11 or 3.12 explicitly.

## 2. One-command setup

Open PowerShell in the project folder:

```powershell
cd "$env:USERPROFILE\Desktop\video-translator"
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

If script execution is blocked, this form does not change your execution policy.
You can also double-click `scripts\setup.bat`.

The script performs these steps and stops on the first fatal error:

1. Finds Python 3.11, 3.12 or 3.10 (in that order).
2. Creates `.venv` and upgrades pip/setuptools/wheel.
3. Installs `torch==2.5.1+cpu` from `download.pytorch.org/whl/cpu`.
4. Installs [requirements.txt](../requirements.txt).
5. Downloads **FFmpeg 9.x essentials** from gyan.dev into `tools\ffmpeg`.
6. Downloads **Piper 2023.11.14-2** (`piper_windows_amd64.zip`) into `tools\piper`.
7. Runs `npm install` + `npm run build` in `frontend\`, producing `frontend\dist`.
8. Downloads the minimal model set (~500 MB) unless `-SkipModels` is used.
9. Runs `backend\verify_install.py` and prints an installation report.

### Setup flags

| Flag | Effect |
|---|---|
| `-SkipModels` | Do not download AI models now; use the **Modelos** page later. |
| `-SkipBinaries` | Keep existing `tools\ffmpeg` / `tools\piper`; do not download. |
| `-SkipFrontend` | Do not run npm; backend-only development. |
| `-Force` | Delete and recreate `.venv` (models and data are untouched). |

Examples:

```powershell
# Install the app only, download models from the UI when needed
.\scripts\setup.ps1 -SkipModels

# Reproduce a clean Python environment
.\scripts\setup.ps1 -Force -SkipModels
```

### If a prerequisite is missing

```powershell
winget install Python.Python.3.11
winget install OpenJS.NodeJS.LTS
```

Close and reopen PowerShell after installing so `py`/`node` are on PATH.

## 3. Start the app

### One-click executable (recommended)

Double-click **`Spanish Dubbing Studio.exe`** in the project folder, or the
“Spanish Dubbing Studio” shortcut on the Desktop / Start menu.

- Starts `uvicorn` hidden with the project's `.venv`, waits for `/api/health`
  and opens **http://127.0.0.1:8765**.
- Keeps an icon in the notification area: double-click to reopen the app,
  right-click to **start/stop the server**, open `storage\exports`, view
  `storage\logs\server.log` or **quit** (which also stops the server).
- A second launch does not start a second server; it only reopens the browser.
- Scripting switches: `"Spanish Dubbing Studio.exe" --stop` and `--status`
  (exit code 0 when the API is up). `--no-browser` starts the tray app without
  opening the browser.

Rebuild it with `powershell -ExecutionPolicy Bypass -File .\launcher\build.ps1`
(uses the C# compiler bundled with Windows; creates the shortcuts too).

If Windows SmartScreen shows a warning the first time (unsigned executable),
choose **Más información → Ejecutar de todas formas**.

### Console alternative

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

or double-click `scripts\start.bat`.

- Opens **http://127.0.0.1:8765** in the default browser (after a 2 s delay).
- `-NoBrowser` suppresses the browser.
- `-Port 8766` uses another port if 8765 is busy.
- `-Reload` enables uvicorn auto-reload for backend development.
- `Ctrl+C` stops the server; unfinished jobs are marked interrupted and can be
  resumed.

The API and UI are served by one process. The server listens on `127.0.0.1`
only; Windows Firewall does not need an inbound rule.

## 4. Download models

The setup script downloads a minimal, license-friendly set:

| Model ID | Contents | Size |
|---|---|---|
| `whisper-tiny` | Speech recognition (faster-whisper, INT8) | ~75 MB |
| `marian-en-es` | English → Spanish translation | ~312 MB |
| `piper-es-mx-ald-medium` | Spanish (Mexico) voice | ~63 MB |

For better transcription quality, also install Whisper Base (~145 MB) from the
**Modelos** page. The balanced preset automatically uses Base when present and
falls back to Tiny otherwise.

Explicit CLI alternatives:

```powershell
.\.venv\Scripts\python.exe backend\download_models.py --list
.\.venv\Scripts\python.exe backend\download_models.py --minimal
.\.venv\Scripts\python.exe backend\download_models.py whisper-base
.\.venv\Scripts\python.exe backend\download_models.py --all    # ~5.6 GB, read licenses first
```

Downloads are resumable: pressing `Ctrl+C` keeps the Hugging Face cache and the
next run continues. Do not delete `models\<id>\.cache` while a download is
paused if you want to resume that file.

Licenses and commercial-use restrictions are listed in
[MODELS.md](MODELS.md). NLLB-200 is **non-commercial**.

## 5. Verify the installation

```powershell
.\.venv\Scripts\python.exe backend\verify_install.py
```

Expected output:

```
[OK  ] FFmpeg: ffmpeg version 9.x ...
[OK  ] FFprobe: ffprobe version 9.x ...
[OK  ] Piper: 1.2.0
[OK  ] Frontend build: ...\frontend\dist
[OK  ] Speech recognition: whisper-tiny
[OK  ] Translation: marian-en-es
[OK  ] Spanish voice: piper-es-mx-ald-medium
Installation looks complete. Start with:  scripts\start.ps1
```

`--strict` returns exit code 1 when models are missing (useful in scripts).

Run the test suite:

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -m "not slow"
..\.venv\Scripts\python.exe -m pytest -m slow
```

## 6. Manual installation

Use this if setup cannot download files, or if you prefer managing tools.

### 6.1 Python environment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 6.2 FFmpeg

Download the Windows "essentials" build from <https://www.gyan.dev/ffmpeg/builds/>
and extract it so these files exist:

```
tools\ffmpeg\bin\ffmpeg.exe
tools\ffmpeg\bin\ffprobe.exe
```

Alternatively install FFmpeg elsewhere and set full paths:

```powershell
$env:VTS_FFMPEG  = "C:\ffmpeg\bin\ffmpeg.exe"
$env:VTS_FFPROBE = "C:\ffmpeg\bin\ffprobe.exe"
```

The video stream is copied, not re-encoded, so `libx264` is not required for
normal dubbing. AAC encoding and the filters `loudnorm`, `atempo` and
`sidechaincompress` are required; the bundled build includes all of them.

### 6.3 Piper

Download <https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip>
and extract it so `tools\piper\piper.exe` and the DLLs / `espeak-ng-data`
folder are present. Or set `VTS_PIPER` to `piper.exe`.

Piper is optional: without it the app uses Windows SAPI (lower quality, marked
with a warning in the job). Models are still downloaded from the Modelos page.

### 6.4 Frontend

```powershell
cd frontend
npm install
npm run build
```

`frontend\dist` must contain `index.html` and `assets\`. The backend serves it.

### 6.5 Models

```powershell
.\.venv\Scripts\python.exe backend\download_models.py --minimal
```

Or download the repositories manually from Hugging Face into the folders shown
in [MODELS.md](MODELS.md). `models\manifest.json` is the source of truth for IDs,
folders, required files and licenses. The app never downloads on its own.

## 7. Offline use

After setup and model installation:

1. Disconnect the network or block the app in the firewall.
2. Start with `scripts\start.ps1`.
3. Process a video.

There is no license check, telemetry or cloud call at runtime. The Modelos page
is the only place that can start a download, and only on your click. If you
disable the network, downloads fail visibly instead of blocking processing.

## 8. Configuration

Environment variables (set before starting the server):

| Variable | Default | Meaning |
|---|---|---|
| `VTS_HOST` | `127.0.0.1` | Bind address. Keep it local. |
| `VTS_PORT` | `8765` | HTTP port |
| `VTS_DATA_DIR` | `<project>\storage` | DB, uploads, projects, exports |
| `VTS_MODELS_DIR` | `<project>\models` | Model manifest and weights |
| `VTS_FFMPEG` / `VTS_FFPROBE` | bundled | Override executable paths |
| `VTS_PIPER` | bundled | Override Piper executable |
| `VTS_MAX_UPLOAD_MB` | `2048` | Initial upload limit (also editable in Settings) |
| `VTS_MAX_DURATION_S` | `3600` | Initial duration limit (also editable) |
| `VTS_OFFLINE` | `0` | Informational flag exposed by the API |

Runtime settings (preset, voice, mode, speed-up, gap, threads, limits) are
stored in SQLite and editable in **Ajustes**. Job settings are frozen when the
job is created, so changing globals does not alter a running job.

### Data folders

```
storage\
  app.db                 SQLite (WAL)
  uploads\               temporary multipart chunks
  projects\<id>\         source.mp4, thumbnail.jpg, job_<id>\...
  exports\               final <name>_es_<id>.mp4 copies
  temporary\             scratch files
```

Back up `storage\` to keep projects and jobs. Back up `models\` to avoid
downloading weights again. Both are excluded from git by `.gitignore`.

## 9. Updating

```powershell
# after replacing/updating the source files
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend; npm install; npm run build; cd ..
```

The database schema is created with `CREATE TABLE IF NOT EXISTS`; this version
does not include migrations for older schemas. If you switch between incompatible
development versions, remove `storage\app.db` (this deletes project history, not
the source videos you still have).

## 10. Uninstalling

There is no installer or registry entry. Delete the project folder. To keep your
videos, copy them out of `storage\exports` first. No services are registered and
nothing runs at startup unless you created a shortcut yourself.

## 11. Known installation limitations

- The PyTorch CUDA wheel is not installed automatically. CPU is the tested
  configuration; GPU support is experimental and requires manual PyTorch install.
- First model load is slow (several seconds); later jobs reuse the cache.
- Antivirus real-time scanning can make FFmpeg/model loading noticeably slower.
- Corporate proxies may block gyan.dev, GitHub or huggingface.co during setup.
  In that case use the manual steps and a machine with access.
- Long videos (>10 min) on a 2-core CPU can take a long time. Test with a short
  clip first; the pipeline reports progress per stage and can be cancelled.
