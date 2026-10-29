# Architecture

Spanish Dubbing Studio is a local web application: a FastAPI process serves a
React SPA, owns a SQLite database, runs one background dubbing worker and shells
out to FFmpeg/Piper. There is no external service at runtime.

```
┌──────────────────────────── browser (localhost) ────────────────────────────┐
│  React 18 + TypeScript + Tailwind (Vite build, served by FastAPI)            │
│  Dashboard · Studio · Modelos · Ajustes                                      │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │ fetch /api/*  (same-origin, X-VTS-Client: web)
┌───────────────────────────────▼─────────────────────────────────────────────┐
│ FastAPI (uvicorn, 127.0.0.1)                                                │
│  security middleware → routers → SQLite repositories                        │
│  static /assets + SPA fallback                                              │
└───────────────┬──────────────────────────────────────┬──────────────────────┘
                │ enqueue(job_id)                      │ reads/writes
┌───────────────▼──────────────────┐       ┌───────────▼──────────────────────┐
│ Single worker thread (JobQueue)  │       │ SQLite (WAL)                     │
│  Pipeline stages 1..9            │       │ projects · jobs · job_stages     │
│  artifacts on disk per job       │       │ segments · events · settings     │
└───┬──────────┬──────────┬────────┘       │ model_downloads                  │
    │          │          │                └──────────────────────────────────┘
┌───▼────┐ ┌───▼─────┐ ┌──▼──────────────┐
│ FFmpeg │ │ Whisper │ │ MarianMT / NLLB │  ┌──────────┐
│ FFprobe│ │ (CTranslate2) │ (PyTorch)   │  │ Piper    │
└────────┘ └─────────┘ └─────────────────┘  │ / SAPI   │
                                            └──────────┘
```

## Design constraints

- **CPU-first, 8 GB RAM.** Models load lazily, are released after their stage
  and a single job runs at a time. Whisper uses INT8 CTranslate2.
- **No cloud inference.** Every adapter loads from a local folder with
  `local_files_only=True`; downloads are explicit user actions.
- **Resumable by artifacts, not by memory.** Each stage writes its output under
  `storage/projects/<project>/job_<job>/` and records status in SQLite. A restart
  can reuse completed stages.
- **Never mutate the input.** The uploaded file is copied to `source.mp4`; the
  final MP4 copies the original video stream and only replaces audio.
- **Local only.** Host allow-list, CSRF header, origin checks, path containment,
  CSP, no CORS.

## Components

| Path | Responsibility |
|---|---|
| `backend/app/main.py` | App factory, middleware, routers, startup/shutdown, SPA |
| `backend/app/core/config.py` | Paths, binary discovery, limits, Windows flags |
| `backend/app/core/security.py` | Host/origin/header checks, path containment, filename sanitization |
| `backend/app/api/routes_*.py` | HTTP endpoints |
| `backend/app/database/db.py` | SQLite schema and short-lived connections |
| `backend/app/database/repository.py` | Projects, jobs, stages, segments, events, settings, download state |
| `backend/app/schemas/api.py` | Pydantic validation and clamping |
| `backend/app/services/ffmpeg.py` | Probing, extraction, thumbnails, concat, progress parsing, cancellation |
| `backend/app/services/asr.py` | faster-whisper adapter, model cache, segment normalization |
| `backend/app/services/translation.py` | MarianMT and NLLB adapters, cleanup, filler trimming |
| `backend/app/services/tts.py` | Piper and SAPI synthesis, text cleaning |
| `backend/app/services/separation.py` | Optional Demucs / FFmpeg fallback |
| `backend/app/services/alignment.py` | Timeline planning, speed limits, dub WAV assembly |
| `backend/app/services/mixing.py` | Ducking/loudness mix and MP4 mux/verify |
| `backend/app/services/subtitles.py` | SRT, VTT, TXT |
| `backend/app/services/models_manager.py` | Manifest, install detection, explicit downloads |
| `backend/app/workers/pipeline.py` | Nine-stage resumable pipeline |
| `backend/app/workers/queue.py` | One worker, cancellation, crash marking |
| `frontend/src/api/client.ts` | Typed fetch wrapper, upload progress, API errors |
| `frontend/src/hooks/useApi.ts` | Polling hooks with visibility-aware intervals |

## Job lifecycle

1. `POST /api/projects` validates the extension, streams the upload with a size
   cap, probes it, enforces duration/audio requirements, moves it to
   `projects/<id>/source.mp4`, creates a thumbnail and inserts the project.
2. `POST /api/projects/<id>/jobs` merges persisted defaults with the request
   (validated/clamped by `JobSettings`), checks that the required models for
   ASR/translation/TTS are installed, inserts the job + nine stage rows and
   enqueues the job.
3. The worker marks the job `running`, then runs the pipeline. Progress is a
   weighted sum of stages; the public value stays below 100 until the job ends.
4. On success the job stores `output_path`, stats, warnings and `completed`.
   On `CancelledError` it becomes `cancelled`; on `AppError` `failed` with a
   human message + hint; on unexpected exceptions a generic message is stored
   and the traceback stays in the server log.
5. Startup calls `JobsRepo.mark_interrupted()`: jobs left `running`/`cancelling`
   become `interrupted` so they can be resumed.
6. `POST /api/jobs/<id>/resume` (or `/rerender`) sets `settings.resume=true`,
   requeues and resets only non-completed stages. Completed/skipped stages stay
   completed.

Queue: `queue.Queue(maxsize=20)`, one daemon worker. Cancellation is cooperative:
the API sets `cancel_requested`, the pipeline checks it at stage boundaries,
inside segment loops, and FFmpeg subprocesses are killed every 250 ms while
`cancel_check()` is true.

## Pipeline stages

| # | Stage | Weight | Output / artifact | Resume rule |
|---|---|---|---|---|
| 1 | analysis | 2 | `analysis.json` (probe) | stage completed + file exists |
| 2 | extraction | 5 | `audio/original.wav` (48 kHz stereo), `audio/asr.wav` (16 kHz mono) | both files + stage completed |
| 3 | asr | 20 | `transcript.json`, rows in `segments` | transcript + segments with `text_src` |
| 4 | translation | 12 | `translation.json`, `segments.text_es` | file + every segment translated |
| 5 | separation | 5 | `stems/background.wav` (optional) | file + stage completed/skipped |
| 6 | tts | 32 | `tts/<idx>_<hash>.wav` per segment | file name hash matches text+voice+rate+volume |
| 7 | sync | 8 | `dub.wav`, `sync.json` | recomputed from voiced segments (fast) |
| 8 | mix | 4 | `mix.wav` | recomputed |
| 9 | render | 12 | `job_<id>/output.mp4`, `subtitles/*`, export copy | recomputed |

Progress weights sum to 100. The pipeline reports a maximum of 99 % until the
job row is finalized at 100 %.

### Model caching and memory

- ASR models are cached by `(model_dir, device, compute_type, threads)` and
  unloaded after the ASR stage.
- Translators are cached by `(engine, model_dir, threads, quantize, source,
  target)` and unloaded after translation. The worker also unloads both in a
  `finally` block, even on failure.
- `ensure_memory(required_mb, stage)` waits up to 45 s for available RAM and
  raises a `resource_error` with a recovery hint if it never becomes available.
- TTS runs Piper as a subprocess per segment, so no ONNX session is kept alive
  between jobs.

### Speech recognition

`asr.transcribe()` calls faster-whisper with VAD, `condition_on_previous_text=False`
and `temperature=0`. Results are normalized by `merge_and_split`:

- sorted by start, clamped to `[0, duration]`, minimum 0.2 s;
- literal overlaps merged (text appended) instead of duplicated;
- segments longer than 14 s with more than 12 words are split proportionally.

If no text is detected, the job fails with an actionable message rather than
silently producing a music-only dub.

### Translation

MarianMT is the default (one model per source→Spanish pair, Apache-2.0). NLLB-200
is optional and selects the source/target language tokens. Batches default to 8
lines and check cancellation between batches. Post-processing strips leading
dashes, fixes spacing before punctuation and capitalizes the first letter.

`shorten_for_fit()` removes only Spanish fillers ("bueno", "pues", "la verdad",
…) and is used by `fit_text_to_window()` for UI/planning estimates; the pipeline
does not silently rewrite translated text.

### Text-to-speech

Piper receives text on stdin and writes a WAV, then FFmpeg resamples to 48 kHz
mono. `clean_text()` removes annotations, URLs and markdown characters. If Piper
is missing on Windows, SAPI is used and the job gets a warning + `sapi_fallback`
stat. Per-segment filenames include a SHA-1 of `text|voice|rate|volume`, so
editing one line only regenerates that line.

### Timing and synchronization

`plan_timeline()` is pure and deterministic:

```
start_i   = max(original_start_i, cursor, 0)
window_i  = min(total, max(start_i + 0.3, next_start - gap))   # gap 80 ms default
available = max(0.2, window_i - start_i)
speed     = min(max_speedup, speech_duration / available)      # only if needed
end_i     = start_i + speech_duration / speed
```

- `max_speedup` defaults to 1.18 and is clamped to 1.0–1.6.
- If the line still does not fit, a warning is stored for the segment.
- The final line may be compressed further to keep the video duration; this is
  also warned about.
- `cursor = end_i + gap` prevents overlap even when a line is pushed later.
- `build_dub()` streams silence and audio into a 48 kHz stereo WAV, never
  holding the full track in RAM. Speed changes use chained `atempo` filters
  (split above 2.0), and the output is padded/trimmed to exactly the video
  duration.

### Audio modes and muxing

`mix_audio()`:

| Mode | Background |
|---|---|
| `dub_only` | none |
| `replace_dialogue` | original audio at 35 % gain |
| `dub_plus_background` | separated stem if available, else original audio at 90 % |
| `dual` | no mix; both tracks are muxed separately |

When a background exists, `sidechaincompress` ducks it under the Spanish voice
(threshold 0.025, ratio 8, 20 ms attack, 420 ms release); `amix` then combines
and `loudnorm` targets −16 LUFS with −1.5 dBTP and a limiter. `apad` keeps the
bed at the video duration even if the dub is shorter.

`render_video()` maps `0:v:0` + `1:a:0`, copies the video stream (`-c:v copy`),
encodes AAC (default 192 kbps), adds fast-start metadata and writes the MP4.
Dual mode adds `0:a:0` as a second track with language metadata. `verify_output`
re-probes the file, requires an audio track and warns if the duration differs by
more than 1.5 s. A copy is placed in `storage/exports/`.

## Database

SQLite with WAL and foreign keys enabled; one short-lived connection per
operation (thread-safe without an ORM).

| Table | Key fields |
|---|---|
| `projects` | id, name, source path, size, probe metadata, timestamps |
| `jobs` | id, project, status, stage, progress, message/error/hint, warnings JSON, settings JSON, stats JSON, output path, cancel flag, timestamps |
| `job_stages` | (job, stage) PK, status, progress, detail, timestamps |
| `segments` | job, idx, start/end, `text_src`, `text_es`, tts path/duration, status, warning |
| `events` | job, timestamp, level, message (bounded at 2000 chars) |
| `settings` | key/value JSON for global defaults |
| `model_downloads` | id, status, progress, bytes, message, updated_at |

Indexes cover project jobs, status, segments and events. Job settings are frozen
at creation. `settings.resume` distinguishes a normal run from a resumed one.

## HTTP API

All routes are under `/api`. Reads need no header; writes require
`X-VTS-Client: web`, a local `Host`, and same-origin (or absent) `Origin` /
`Sec-Fetch-Site`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | component checks + queue |
| GET | `/system` | hardware, model/storage summary, capabilities, privacy text |
| GET | `/options` | languages, variants, modes, presets, voices, separation |
| GET/POST | `/projects` | list / upload (multipart `file`, optional `name`) |
| GET/DELETE | `/projects/{id}` | detail with jobs / delete (blocked while active) |
| GET | `/projects/{id}/thumbnail` | JPEG thumbnail |
| GET | `/projects/{id}/video` | original video (range-friendly FileResponse) |
| POST | `/projects/{id}/jobs` | create + enqueue a job (`JobSettings`) |
| GET | `/jobs` | recent jobs (`limit`, `active_only`) |
| GET/DELETE | `/jobs/{id}` | detail + queue/elapsed / delete non-active |
| POST | `/jobs/{id}/cancel` | cooperative cancel |
| POST | `/jobs/{id}/resume` | requeue non-completed stages |
| POST | `/jobs/{id}/rerender` | requeue for edited segments |
| GET | `/jobs/{id}/events` | job log |
| GET | `/jobs/{id}/segments` | transcript + duration |
| PATCH | `/jobs/{id}/segments/{idx}` | edit Spanish text/start/end |
| POST | `/jobs/{id}/segments/{idx}/regenerate` | re-TTS one segment + rerender |
| GET | `/jobs/{id}/segments/{idx}/audio` | WAV preview |
| GET | `/jobs/{id}/media/{kind}` | original/output/dub/mix/background |
| GET | `/jobs/{id}/download` | final MP4 |
| GET | `/jobs/{id}/subtitles/{srt,vtt,txt}` | subtitle/transcript exports |
| GET | `/models` | manifest + install/download state |
| GET/DELETE | `/models/{id}` | one model / remove weights |
| POST | `/models/{id}/download` | explicit download (background) |
| POST | `/models/unload` | free ASR/translation RAM |
| GET/PUT | `/settings` | global settings |
| GET | `/options` | (see above) |
| POST | `/maintenance/cleanup?days=N` | remove old temp files |

Errors are always `{"error": {"code", "message", "hint"}}`. Pydantic request
errors return 422; typed application errors use 400/403/404/409/422/507.

Static delivery: `/assets/*` is mounted from `frontend/dist`; any other non-API
path returns `index.html` so React Router deep links work. If the frontend is
not built, the API returns 503 with a build hint.

## Security model

- **Network:** uvicorn binds `127.0.0.1`. Middleware rejects any `Host` other
  than `127.0.0.1`, `localhost`, `[::1]`, `0.0.0.0` (covers DNS rebinding).
- **CSRF:** mutating methods need `X-VTS-Client: web`, and an `Origin` (if sent)
  must match the request host/port. `Sec-Fetch-Site: cross-site` is rejected.
  This protects against a malicious page in the same browser.
- **Files:** `ensure_within()` resolves paths and requires them under the data
  directory. Upload names are sanitized; size and duration are capped; only
  MP4/MOV containers with audio are accepted.
- **Subprocesses:** argument lists only (never `shell=True`), `-nostdin`,
  bounded output buffers, timeouts and cancellation.
- **Browser:** CSP (`default-src 'self'`, no inline script), `nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`. No CORS headers are
  emitted; the SPA is same-origin.
- **No authentication.** This is a single-user localhost tool. Do not expose it.

## Frontend

- `App.tsx` routes: Dashboard (`/`), Studio (`/studio/:projectId`), Models,
  Settings. Layout uses a compact sidebar and responsive content.
- `api/client.ts` wraps `fetch`, injects `X-VTS-Client`, parses typed API errors
  and uploads with `XMLHttpRequest` progress.
- `hooks/useApi.ts` provides `useJob`, `useProjects`, `useModels`, etc. Polling
  stops when the document is hidden and uses different intervals for active vs
  finished jobs to avoid unnecessary requests.
- `Studio.tsx` is the main workflow: upload/launch, stage tracker, video preview,
  segment editor with per-line audio, warnings, subtitles and download.
- The UI is in Spanish (Mexico), with explicit labels for model/license state and
  recovery actions.

## Tests

`backend/tests/` uses a throw-away `VTS_DATA_DIR` and the real project models
(read-only). Fixtures generate a 3 s H.264/AAC clip and WAV tones with FFmpeg.

| File | Coverage |
|---|---|
| `test_core.py` | host detection, dirs, binaries, path traversal, filename slugs, CSRF header/origin, security headers, settings validation/clamping, repository persistence |
| `test_media.py` | probe (valid/invalid/no audio), 16 kHz extraction, thumbnails, silence, SRT timestamps, subtitle exports, subprocess cancellation/timeout/exit codes, dub-only/ducked mixes, MP4 mux (single/dual), output verification |
| `test_alignment.py` | ordering/no overlap, speed limit, tail compression, empty segments, exact WAV duration, silence gaps, `atempo`, cancellation, text fitting, gap clamp |
| `test_adapters.py` | mocked Whisper success/failure/cancel/empty, overlap merge/split, translation batches/cancel/mismatch, text helpers, TTS cleaning/errors, manifest structure, installed resolvers |
| `test_api.py` | upload validation (extension/empty/fake/no audio), thumbnail/video, project CRUD, active-job conflict, options, settings, health/system/models, job create/cancel/conflict, resume, editing, regenerate, subtitles, events, media/download, delete rules |
| `test_jobs.py` | cancel queued/finished, `mark_interrupted`, resume after restart, artifact reuse, missing source, worker cancellation/AppError/unexpected exception, pre-start cancel |
| `test_zz_e2e.py` | **real** upload → Whisper Tiny → Marian → Piper → sync → mux, then re-transcribe the output and assert Spanish, plus subtitles/download/stream stats |

Current results on the development machine (i3-1115G4, 8 GB, CPU):

```
132 passed, 1 deselected in 17.35s     # pytest -m "not slow"
1 passed, 132 deselected in 20.44s     # pytest -m slow
```

The slow test processes a real 12.7 s English clip in about 20 s including the
verification transcription. Longer videos scale with duration; the pipeline
reports progress and can be cancelled.

## Known limitations

- One voice for all speakers; no diarization or voice cloning.
- No lip-sync/visual regeneration.
- Source separation is optional and not bundled. Without Demucs, the fallback is
  attenuation or a center-cancel estimate that can remove centered music.
- Translation quality depends on the model. Marian is focused on EN→ES; other
  languages need their pair or NLLB (non-commercial).
- Aggressive speed-up can sound unnatural; the app warns but does not silently
  rewrite the text. `fit_text_to_window` is available for future auto-shortening.
- No DB migrations between major versions; remove `storage/app.db` if the schema
  is incompatible.
- GPU inference is detected but not the tested path; setup installs CPU PyTorch.
- The queue is intentionally single-worker; `parallel_jobs` is fixed at 1.
- The SPA has no authentication and must stay bound to localhost.
