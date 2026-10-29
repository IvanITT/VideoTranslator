# Troubleshooting

The app reports errors as `{"error": {"code", "message", "hint"}}` in the API
and as a message + hint in the job panel. Start with the diagnostics below, then
find the matching symptom.

## Quick diagnostics

```powershell
cd C:\Users\<you>\Desktop\video-translator
.\.venv\Scripts\python.exe backend\verify_install.py
.\.venv\Scripts\python.exe backend\download_models.py --list
```

Check the API while the app is running:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/health | ConvertTo-Json -Depth 5
Invoke-RestMethod http://127.0.0.1:8765/api/system | ConvertTo-Json -Depth 5
```

A job's full state and log:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/jobs/<JOB_ID> | ConvertTo-Json -Depth 8
Invoke-RestMethod http://127.0.0.1:8765/api/jobs/<JOB_ID>/events | ConvertTo-Json -Depth 5
```

Server logs go to the terminal running `start.ps1` (uvicorn). There is no remote
logging and no telemetry.

## Setup and startup

### PowerShell says "running scripts is disabled"

Use the bypass form without changing the policy:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

or double-click the `.bat` launchers.

### The `.exe` does not start / no tray icon appears

- Make sure `Spanish Dubbing Studio.exe` sits in the project folder next to
  `backend\` and `.venv\`. If you moved only the `.exe`, rebuild it with
  `powershell -ExecutionPolicy Bypass -File .\launcher\build.ps1`.
- The first time, Windows SmartScreen may block an unsigned executable:
  choose **Más información → Ejecutar de todas formas**.
- The icon lives in the notification area; open the hidden-icons arrow (`^`) if
  it is not visible next to the clock.
- Check `storage\logs\server.log` (right-click the tray icon → **Ver registro**).
  A missing `.venv` means `scripts\setup.ps1` has not finished.
- To stop the app even without the tray icon:
  `"Spanish Dubbing Studio.exe" --stop`.

### "Python 3.10, 3.11 or 3.12 was not found"

```powershell
winget install Python.Python.3.11
```

Close and reopen the terminal. `py -0p` should list 3.11. Python 3.13 is rejected
because the pinned torch/CTranslate2 wheels are not available for it.

### Setup fails installing torch or CTranslate2

- Confirm 64-bit Python (`python -c "import platform; print(platform.architecture())"`).
- Make sure you are online during setup; the CPU wheel is downloaded from
  `download.pytorch.org`.
- Behind a proxy, set `HTTP_PROXY`/`HTTPS_PROXY` or use the manual pip commands in
  [INSTALL.md](INSTALL.md#61-python-environment).
- Re-run `.\scripts\setup.ps1 -Force -SkipModels` to recreate `.venv`.

### "Node.js was not found" / frontend build fails

```powershell
winget install OpenJS.NodeJS.LTS
```

Then in `frontend\`: `npm install` and `npm run build`. The error must be fixed;
the backend can run without `dist`, but the UI returns 503
`frontend_not_built`.

### FFmpeg or Piper download blocked

Corporate networks sometimes block gyan.dev/GitHub. Download manually:

- FFmpeg: <https://www.gyan.dev/ffmpeg/builds/> → extract to `tools\ffmpeg` so
  `tools\ffmpeg\bin\ffmpeg.exe` exists.
- Piper: <https://github.com/rhasspy/piper/releases> → extract `piper.exe` and
  its DLLs/`espeak-ng-data` to `tools\piper`.

Or set `VTS_FFMPEG`, `VTS_FFPROBE`, `VTS_PIPER` to existing executables before
starting.

### Port 8765 is already in use

If the other process is this app, stop it from the tray icon or with:

```powershell
& ".\Spanish Dubbing Studio.exe" --stop
```

For the console launcher use another port:

```powershell
.\scripts\start.ps1 -Port 8766
```

Then open http://127.0.0.1:8766. Do not run two servers against the same
`storage\app.db` at once.

### "The web interface is not built" (503)

```powershell
cd frontend
npm install
npm run build
cd ..
```

The backend reads `frontend/dist` at startup; restart it after building.

## Browser and security

### 403 "Solicitud rechazada: la API solo acepta conexiones locales"

Open the official URL (`http://127.0.0.1:8765` or `http://localhost:8765`). The
`Host` header must be local; reverse proxies, LAN IPs and tunnels are rejected by
design.

### 403 "Falta la cabecera de cliente local"

You are calling a write endpoint with a script/tool. Add:

```
X-VTS-Client: web
```

Example:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/api/models/unload `
  -Headers @{ "X-VTS-Client" = "web" }
```

Reads (`GET`) do not need it.

### 403 "Solicitud bloqueada por protección de origen (CSRF)"

The browser sent an `Origin` from another site, or a cross-site form. Use the
app's own page. For scripts, omit `Origin` (or set it to
`http://127.0.0.1:8765`) and include the client header.

### Page loads but API calls fail

- Check the terminal for tracebacks.
- Confirm you opened the same port as the server.
- If you changed `VTS_HOST` to a non-loopback address, revert it; the security
  middleware intentionally rejects remote hosts.
- Hard-refresh (`Ctrl+F5`) after rebuilding the frontend.

## Uploads

| Message | Cause / fix |
|---|---|
| "Formato no soportado. Sube un archivo MP4." | Only `.mp4`/`.m4v` are accepted. Remux with FFmpeg: `ffmpeg -i input.mkv -c copy out.mp4`. |
| "El archivo está vacío." | The upload was interrupted; retry. |
| "No se pudo leer el archivo multimedia." | Corrupt/unsupported container. Probe it: `ffprobe -v error input.mp4`. |
| "El video no tiene pista de audio." | The app needs dialogue. Add audio or choose another file. |
| "El video es demasiado corto." | Minimum 0.5 s. |
| "El archivo supera el límite de N MB." | Raise **Ajustes → límite de subida** (max 10 GB) or compress. |
| "El video dura N min y el máximo es M min." | Raise the duration limit in Ajustes (max 6 h). |
| 500 after upload | Check disk space and the server log; the temp `.part`/project folder should be cleaned automatically. |

MOV files inside an MP4 container are accepted, but re-muxing to H.264/AAC MP4
is the safest input.

## Models, RAM and disk

### "Faltan modelos para iniciar el doblaje"

Open **Modelos** and install the missing stage for your language. For English →
Spanish the minimum is Whisper (any), `marian-en-es` and one Spanish voice.
Auto-detect needs a translation model installed; explicit non-English sources
need their Marian pair or NLLB.

### Download stays at 0 % or fails

- Check internet access to `huggingface.co`.
- The Modelos page shows the error; retry resumes from cache.
- Delete only the incomplete model folder if its state is inconsistent:
  `models\<local_dir>` (never delete `manifest.json`).
- Corporate TLS inspection can break Python certificates; update
  `certifi`/Python or use a trusted network.

### "No hay suficiente memoria RAM"

The pipeline waits 45 s for free memory, then fails with `resource_error`.

- Use `whisper-tiny` and the `low` preset.
- Set **Ajustes → hilos de CPU** to 2 (or 1 on very small machines).
- Close browsers/games/other Python processes.
- Press **Modelos → Liberar memoria** (unloads ASR/translation).
- Avoid NLLB (~3.2 GB); use Marian.
- A 2-core/8 GB machine can dub short clips; 16 GB is comfortable.

### "Espacio insuficiente en disco"

Processing needs roughly the video size plus audio scratch. Free space or change
`VTS_DATA_DIR` to another drive before starting. Old temp files can be cleaned
from **Ajustes → Mantenimiento** or:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8765/api/maintenance/cleanup?days=1" `
  -Headers @{ "X-VTS-Client" = "web" }
```

## Speech recognition

### "No se detectó voz en el audio"

- Confirm the video actually has audible dialogue (play it).
- Very quiet audio: raise the source volume and re-upload, or extract/boost audio
  externally.
- Music-only or sound-effect clips cannot be dubbed by this version.

### Wrong language detected

Set **Idioma de origen** explicitly instead of automatic, then rerun. Automatic
detection below 60 % confidence produces a warning in the job.

### Transcription is inaccurate or repeats

- Install `whisper-base` or `whisper-small` (better accuracy).
- Noise/music/accented speech degrades Tiny.
- Whisper can hallucinate on silence; VAD is enabled, but trimming long silent
  intros helps.
- Edit the Spanish translation after transcription; the source text is kept for
  reference and subtitle export.

## Translation

### "No hay un modelo de traducción instalado para «xx» → español"

Install the matching `marian-xx-es` pair or NLLB-200 (non-commercial). Only
EN/FR/DE/PT/IT pairs are in the manifest; other languages require NLLB.

### Translation sounds literal or too long

- Marian is sentence-level; short conversational lines work best.
- Edit the Spanish text in Studio; only that segment's voice is regenerated.
- Lines that exceed their time window are sped up and flagged; shortening the
  text is better than raising the speed limit.
- NLLB may be better for some languages but is slower and non-commercial.

## Voice / TTS

### The job warns "Piper no está disponible: se usó SAPI"

The Piper binary is missing or broken. Reinstall the `tools\piper` folder or set
`VTS_PIPER`. SAPI still produces intelligible audio but with a robotic voice.

### Piper exits with an error

- `tools\piper` must contain `piper.exe`, the DLLs and `espeak-ng-data`.
- The selected voice must have both `.onnx` and `.onnx.json` in
  `models\piper\<voice>`.
- Antivirus may quarantine `onnxruntime.dll`; restore it or reinstall Piper.
- Test directly:

```powershell
" Hola, esto es una prueba." | .\tools\piper\piper.exe `
  --model .\models\piper\es_MX-ald-medium\es_MX-ald-medium.onnx `
  --output_file test.wav
```

### Voice is too fast/slow or quiet

Adjust **Ajustes → velocidad de habla** (0.6–1.8) and **volumen**, then recreate
the job (settings are frozen per job). Per-segment speed-up for timing is
separate and capped by **límite de aceleración**.

## Synchronization and audio

### Lines are accelerated or cut

The translated line is longer than its window. The app speeds it up to the limit
(default 1.18×), then flags it. Shorten the Spanish text; increasing the limit
above ~1.25 usually sounds unnatural. Raising `gap_ms` gives more breathing room
but can push later lines.

### Dubbed audio drifts or ends early

- The pipeline pads the dub to the exact video duration, so output duration
  should match within 1.5 s. A warning appears if it does not.
- Re-render after edits (`Volver a renderizar`).
- If the source has variable frame rate, the video stream is still copied; audio
  timing follows the container duration, not individual frames.
- Check the job's `sync.json`/stats for `sync_max_speed` and `sync_trimmed`.

### Original dialogue is still audible

- `replace_dialogue` deliberately keeps the original at 35 %.
- `dub_plus_background` without separation keeps the original at 90 % and warns.
- Use `dub_only` for the cleanest result, or install Demucs and enable
  separation. The FFmpeg fallback is a center-cancel estimate and can damage
  centered music.

### Music/effects disappeared

Use `dub_plus_background` with separation, or `replace_dialogue`. `dub_only`
intentionally discards them.

## Render and download

### "FFmpeg falló durante renderizado"

- Ensure at least ~1 GB free disk.
- Check the source still exists in `storage\projects\<id>\source.mp4`.
- The video stream is copied, so an unusual codec can still fail to mux into
  MP4; remux the input to H.264/AAC first.
- Read the hint's FFmpeg tail and the job events.

### Download is 404

The job is not completed or its output was deleted. Re-render. Subtitle exports
require segments.

### Final MP4 plays video but no audio

`verify_output` would normally fail the job. If it happens in an external player,
check the track list:

```powershell
ffprobe -v error -show_streams output.mp4
```

Use `dual` if you need both tracks; some editors only import the first audio
track.

## Jobs, cancellation and recovery

### The app closed during processing

On restart, live jobs are marked **interrupted**. Open the job and press
**Reanudar**; completed stages are reused. Already generated TTS files are reused
by content hash.

### Cancel does not stop immediately

Cancellation is cooperative: the current FFmpeg process is killed within ~250 ms
and Python loops check between segments/batches. A model load in progress can
take a few seconds to return. Wait for `cancelled`, then edit/delete.

### "Ya hay un trabajo en curso para este proyecto"

One active job per project. Wait, cancel, or open the existing job. The queue
itself runs one job at a time overall.

### "No se puede editar mientras el trabajo está activo"

Wait for completion/cancellation, edit, then **Volver a renderizar**.

## Performance

- Whisper Tiny is ~2× faster than Base; Small is much slower on 2 cores.
- CPU threads: 2 on a 2-core/4-thread CPU is a good default; more threads can
  hurt due to contention.
- Model load time dominates very short clips; a 13 s clip takes ~20 s end-to-end
  on the reference i3, mostly model loading + translation.
- Long videos: processing time scales roughly with duration; the queue reports
  stage progress. Close memory-hungry apps.
- GPU: setup installs CPU PyTorch. CUDA requires a manual PyTorch CUDA wheel and
  is experimental; set `device` to `auto`/`cuda` only after verifying
  `torch.cuda.is_available()`.

## Reset and cleanup

- Remove old temp files: **Ajustes → Mantenimiento**, or the cleanup endpoint.
- Delete a project in the UI (blocked while a job is active). This removes its
  source, artifacts and DB rows.
- To reset history only: stop the app, delete `storage\app.db` (and `-wal`/`-shm`).
  Project files remain orphaned and can be deleted manually.
- To remove all app data: delete `storage\`. To reclaim model space: delete
  `models\<id>` except `manifest.json`.
- Full uninstall: delete the project folder. No services or registry entries are
  created.

## Reporting a problem

There is no telemetry. To get help, collect:

1. Output of `backend\verify_install.py`.
2. Windows version, CPU/RAM, Python and Node versions.
3. The job JSON (`/api/jobs/<id>`) and last ~30 events.
4. The server terminal traceback.
5. A short, non-confidential clip that reproduces it, if possible.

Redact paths, names and dialogue before sharing. Never post model weights or
private videos publicly.

## Error code reference

| Code | Typical meaning |
|---|---|
| `validation_error` | Bad request/upload/settings (HTTP 422) |
| `media_error` | Missing audio/video, unreadable file, duration limits |
| `ffmpeg_error` | FFmpeg failed/timed out |
| `asr_error` | Whisper could not load or transcribe |
| `translation_error` | Translator load/inference/batch mismatch |
| `tts_error` | Piper/SAPI synthesis failed |
| `alignment_error` | No voiced segments or unexpected sample rate |
| `mix_error` | Empty mix or invalid final file |
| `model_missing` | Required weights are not installed (HTTP 409) |
| `resource_error` | RAM or disk below the required threshold (HTTP 507) |
| `forbidden` | Local host/CSRF/client-header check failed (HTTP 403) |
| `conflict` | Active job, duplicate job, invalid state transition (HTTP 409) |
| `not_found` | Project/job/segment/model/file does not exist (HTTP 404) |
| `internal_error` | Unexpected exception; details only in the server log |
