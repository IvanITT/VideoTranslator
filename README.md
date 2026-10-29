# Spanish Dubbing Studio

Local-first video dubbing to Spanish. Upload an MP4, transcribe its dialogue,
translate it (Spanish from Mexico by default), generate a Spanish voice, fit it
to the original timing, mix it with the background and export a dubbed MP4.
After the one-time model download, **no video, audio or text leaves the PC**.

![workflow](docs/workflow.svg)

> Status: first version, developed and tested on Windows 11 with an Intel
> i3-1115G4 (2 cores / 4 threads), 8 GB RAM and no GPU. It is a single-user,
> localhost-only application, not a cloud service.

## What it does

1. **Validates and analyzes** the upload (MP4/MOV container, H.264 recommended,
   audio track required, duration and size limits).
2. **Extracts audio** twice with FFmpeg: 48 kHz stereo for the final mix and
   16 kHz mono for speech recognition.
3. **Transcribes** with faster-whisper (Whisper Tiny/Base/Small, CPU INT8).
4. **Translates** with a local MarianMT model (Apache-2.0) or optional NLLB-200.
5. **Generates Spanish speech** with Piper (default voice: Ald, es-MX) and falls
   back to Windows SAPI if Piper is unavailable.
6. **Synchronizes** each line to its original time window, limiting speed-up to
   a safe factor and reporting lines that still do not fit.
7. **Mixes** the dub with the original background (optionally separated with
   Demucs or an FFmpeg fallback), applies loudness normalization and ducking.
8. **Exports** an MP4 with the original video stream copied untouched, plus SRT,
   VTT and TXT transcripts.
9. **Recovers**: every stage writes its artifacts to disk, so a cancelled,
   failed or interrupted job can resume without redoing completed work.

The interface lets you edit the Spanish text (and timings) per segment, preview
each generated voice line, regenerate one segment, and re-render the final video.

## What is intentionally not included

- Voice cloning, voice conversion, emotion transfer or speaker diarization.
  All lines use one selected Spanish voice.
- Lip-sync / talking-head regeneration.
- Automatic music/effects separation unless you install Demucs; otherwise the
  original audio is attenuated or an FFmpeg center-cancel fallback is used.
- Cloud APIs, telemetry, accounts, multi-user access or remote streaming.
- Automatic model downloads. Models are downloaded only from the **Modelos**
  page or explicitly with `backend/download_models.py`.

These are deliberate first-version trade-offs: reliable, synchronized dubbing
on a CPU-only machine comes before voice identity or lip-sync.

## Requirements

| Component | Minimum | Notes |
|---|---|---|
| OS | Windows 10/11 64-bit | Linux/macOS are not officially tested |
| CPU | 2 cores, AVX2 | 4+ cores strongly recommended |
| RAM | 8 GB | 16 GB for Whisper Small or NLLB |
| Disk | ~6 GB free | Python env + FFmpeg + models + working space |
| Python | 3.10–3.12 (3.11 recommended) | 3.13 is not supported by the pinned wheels |
| Node.js | 20 LTS or newer | Only needed to build the interface |
| FFmpeg | bundled by setup | Or set `VTS_FFMPEG` / `VTS_FFPROBE` |
| GPU | optional | CUDA is detected but CPU is the tested path |

## Quick start (Windows)

After the one-time setup, the simplest way to start the app is to double-click
**`Spanish Dubbing Studio.exe`** (or the shortcut created on the Desktop and in
the Start menu). It starts the local server in the background, opens
http://127.0.0.1:8765 and keeps an icon in the notification area:

- **double click** the icon → open the studio;
- **right click** → start/stop the server, open the exported videos folder,
  view the log (`storage\logs\server.log`) or quit.

The first time, install the environment and models:

```powershell
cd C:\Users\<you>\Desktop\video-translator
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

`setup.ps1`:

- finds Python 3.10–3.12 and creates `.venv`;
- installs the CPU build of PyTorch and `requirements.txt`;
- downloads FFmpeg (gyan.dev essentials) into `tools\ffmpeg`;
- downloads the standalone Piper binary into `tools\piper`;
- runs `npm install` and `npm run build` for the interface;
- downloads the minimal model set (~500 MB): Whisper Tiny, Marian EN→ES and the
  es-MX Ald voice;
- prints a verification report.

Useful flags:

```powershell
.\scripts\setup.ps1 -SkipModels      # install the app, download models in the UI
.\scripts\setup.ps1 -SkipBinaries    # use FFmpeg/Piper already on PATH
.\scripts\setup.ps1 -SkipFrontend    # backend only (development)
.\scripts\setup.ps1 -Force           # recreate .venv
```

Console alternative: `start.ps1` serves the built interface and the API at
**http://127.0.0.1:8765**, then opens the browser. Options:
`-Port 8766`, `-NoBrowser`, `-Reload` (development auto-reload). The `.exe`
launcher always uses port 8765 unless `VTS_PORT` is set.

If PowerShell blocks scripts, use the `powershell -ExecutionPolicy Bypass -File`
form above, the `.bat` launchers or the `.exe`. No permanent execution-policy
change is needed.

To rebuild the executable (after moving the folder or changing the icon):

```powershell
powershell -ExecutionPolicy Bypass -File .\launcher\build.ps1
```

It uses the C# compiler included with Windows and also regenerates the Desktop
and Start-menu shortcuts.

### Manual start (development)

```powershell
# Terminal 1 - API
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765

# Terminal 2 - Vite dev server (proxies /api to 8765)
cd frontend
npm run dev
```

Open http://localhost:5173 for development or http://127.0.0.1:8765 for the
production build.

## Using the app

1. **Dashboard → Nuevo doblaje**: drop an MP4 (with audible dialogue).
2. Choose source language (or automatic), Spanish variant, voice, audio mode and
   quality preset.
3. Start the job and follow the nine stages. The first run loads models; later
   runs reuse the cached models until RAM is released between stages.
4. When it finishes, compare the original and dubbed video in **Studio**.
5. Optional: edit a Spanish line, preview or regenerate its audio, then
   **Volver a renderizar** (only the affected stages rerun).
6. Download the MP4, SRT, VTT or TXT.
7. If a job fails or the app closes, open the job and press **Reanudar**.

### Audio modes

| Mode | Result |
|---|---|
| `dub_only` | Spanish voice only; music/effects removed. Best intelligibility. |
| `replace_dialogue` | Spanish voice + original audio attenuated to 35 %. |
| `dub_plus_background` | Spanish voice + separated background if available, otherwise attenuated original audio. |
| `dual` | Dubbed track first + original audio as a second AAC track (players can switch). |

### Timing behavior

Each translated line gets the window between its start and the next line. If the
synthesized voice is longer, it is sped up with FFmpeg `atempo` up to the
configured limit (default **1.18×**). Lines that still do not fit are flagged in
the timeline and in the job warnings; the final line is compressed to preserve
the video duration. Nothing is silently cut without a warning.

## Models

The app works fully offline after installation. The recommended first set is:

| Model | Stage | Size | License |
|---|---|---|---|
| Whisper Tiny (faster-whisper INT8) | ASR | ~75 MB | MIT |
| MarianMT EN→ES | Translation | ~312 MB | Apache-2.0 |
| Piper `es_MX-ald-medium` | TTS | ~63 MB | MIT (voice data: Unlicense) |

Optional: Whisper Base (~145 MB, better accuracy), Whisper Small (~484 MB),
Marian pairs for FR/DE/PT/IT, more Spanish voices, and NLLB-200 600M (~2.5 GB,
**CC-BY-NC-4.0, non-commercial**). See [docs/MODELS.md](docs/MODELS.md) for the
full table, licenses and commercial-use notes.

Download more from **Modelos** in the app or explicitly:

```powershell
.\.venv\Scripts\python.exe backend\download_models.py --list
.\.venv\Scripts\python.exe backend\download_models.py whisper-base
.\.venv\Scripts\python.exe backend\download_models.py --minimal
```

Nothing is downloaded automatically by the backend or the UI.

## Privacy and security

- The server binds to `127.0.0.1` only and rejects non-local `Host` headers.
- Write requests require the `X-VTS-Client: web` header and a same-origin
  request, which blocks cross-site form posts and malicious local web pages.
- Media paths are resolved and checked against the data directory; uploads use
  sanitized filenames and size/duration limits.
- No analytics, crash reporting, cloud inference or remote database.
- The only network access happens when you explicitly download a model or a
  tool during setup. After that, disconnect and everything still works.
- Storage defaults to `storage\` in the project (database, uploads, projects,
  exports). Models live in `models\`.

Do not expose port 8765 to your LAN or the internet: there is no authentication.

## Tests

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -m "not slow"    # 132 fast tests
..\.venv\Scripts\python.exe -m pytest -m slow          # real 13 s dubbing E2E
..\.venv\Scripts\python.exe -m pytest                  # everything
```

The suite covers upload/API validation, security/CSRF/path containment, FFmpeg
probing/extraction/thumbnails, timestamp and subtitle conversion, ASR and
translation adapters (mocked), timing/alignment/atempo, cancellation, crash
recovery and artifact reuse, audio mixing, MP4 muxing, and a real end-to-end run
that re-transcribes the output to confirm it is Spanish. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#tests).

## Project layout

```
backend/
  app/
    api/          FastAPI routers (projects, jobs, models, settings, system)
    core/         config, typed errors, localhost security
    database/     SQLite schema and repositories
    schemas/      Pydantic request models
    services/     FFmpeg, ASR, translation, TTS, separation, alignment, mixing
    workers/      single-worker queue and resumable pipeline
  tests/          pytest suite (fast + slow E2E)
  download_models.py
  verify_install.py
frontend/         React 18 + TypeScript + Vite + Tailwind UI
launcher/         C# source + build.ps1 for "Spanish Dubbing Studio.exe"
models/           manifest.json + downloaded weights (ignored by git)
scripts/          setup.ps1 / start.ps1 and .bat launchers
tools/            local FFmpeg and Piper binaries (installed by setup)
storage/          runtime database, uploads, projects, exports and logs
docs/             install, architecture, models, troubleshooting
```

`Spanish Dubbing Studio.exe` in the project root is the one-click launcher; it
uses the `.venv` created by setup, so it is small (about 380 KB) and needs no
extra runtime.

## Troubleshooting

Quick checks:

```powershell
.\.venv\Scripts\python.exe backend\verify_install.py
```

Common fixes (details in [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)):

- **Python not found / 3.13 error** → install Python 3.11 and rerun setup.
- **403 forbidden** → open the official `http://127.0.0.1:8765` UI; scripts must
  send `X-VTS-Client: web`.
- **"Faltan modelos"** → open **Modelos** and download the missing stage.
- **Out of memory** → choose Whisper Tiny, set 2 threads, close other apps;
  models are unloaded between stages.
- **Port in use** → stop the app from the tray icon or
  `& ".\Spanish Dubbing Studio.exe" --stop`; the console launcher accepts
  `-Port 8766`.
- **Audio out of sync / accelerated** → edit the Spanish text to be shorter or
  lower the maximum speed-up; the app warns instead of silently cutting.
- **Original dialogue audible** → use `dub_only`, or enable separation with
  Demucs installed.

## Documentation

- [Installation guide](docs/INSTALL.md) — prerequisites, manual setup, offline use.
- [Architecture](docs/ARCHITECTURE.md) — pipeline, timing, database, API, tests.
- [Models and licenses](docs/MODELS.md) — sizes, licenses, commercial use.
- [Troubleshooting](docs/TROUBLESHOOTING.md).
- [Third-party notices](THIRD_PARTY_NOTICES.md).

## License

The application code is released under the [MIT License](LICENSE). Bundled
tools and downloaded models keep their own licenses; in particular the FFmpeg
build is GPL-licensed and NLLB-200 is non-commercial. Read
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) before redistributing the app or
using it commercially.
