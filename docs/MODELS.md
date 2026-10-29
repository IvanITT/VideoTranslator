# Models and licenses

All inference is local. `models/manifest.json` is the single source of truth for
model IDs, Hugging Face repositories, local folders, required files, sizes,
languages and licenses. The backend only *reads* installed files; it downloads
weights only after an explicit action (`POST /api/models/{id}/download` or
`backend/download_models.py`).

The application code is MIT, but **models are licensed separately**. Check the
license before commercial use or redistribution. This page is a summary, not
legal advice.

## Recommended first installation

| Model ID | Stage | Approx. size | RAM | License | Commercial use |
|---|---|---|---|---|---|
| `whisper-tiny` | ASR | 75 MB | ~450 MB | MIT | Yes |
| `marian-en-es` | Translation | 312 MB | ~900 MB | Apache-2.0 | Yes |
| `piper-es-mx-ald-medium` | TTS | 63 MB | ~300 MB | MIT (voice data Unlicense) | Yes |

Total ≈ 450 MB downloaded, ≈ 1.7 GB peak RAM if stages did not unload. The
pipeline releases ASR and translation models between stages, so on 8 GB the
practical peak is lower.

For better transcription, add `whisper-base` (145 MB). The default balanced
preset uses Base when installed and falls back to Tiny.

## Full manifest

### Speech recognition (faster-whisper / CTranslate2)

| ID | Size | Quality | License | Notes |
|---|---|---|---|---|
| `whisper-tiny` | 75 MB | low | MIT | Fastest; clear speech only |
| `whisper-base` | 145 MB | medium | MIT | Recommended default |
| `whisper-small` | 484 MB | high | MIT | Slow on 2–4 cores; 16 GB recommended |

All three support 99 languages and run INT8 on CPU. Weights are distributed by
Systran in `faster-whisper-*` repositories, derived from OpenAI Whisper (MIT).
Sources: <https://huggingface.co/Systran/faster-whisper-base> (and `-tiny`,
`-small`).

### Translation

| ID | Pair | Size | License | Commercial use |
|---|---|---|---|---|
| `marian-en-es` | English → Spanish | 312 MB | Apache-2.0 | Yes |
| `marian-fr-es` | French → Spanish | 310 MB | Apache-2.0 | Yes |
| `marian-de-es` | German → Spanish | 310 MB | Apache-2.0 | Yes |
| `marian-pt-es` | Portuguese → Spanish | 300 MB | Apache-2.0 | Yes |
| `marian-it-es` | Italian → Spanish | 300 MB | Apache-2.0 | Yes |
| `nllb-600m` | 200 languages → Spanish | 2.5 GB | **CC-BY-NC-4.0** | **No (non-commercial)** |

- MarianMT models come from the Helsinki-NLP OPUS-MT project:
  <https://huggingface.co/Helsinki-NLP/opus-mt-en-es>.
- Install only the pairs you need. Auto-detected source languages require a
  matching pair or NLLB.
- NLLB-200 Distilled 600M: <https://huggingface.co/facebook/nllb-200-distilled-600M>.
  The CC-BY-NC-4.0 license forbids commercial use and requires attribution. It
  also needs ~3.2 GB RAM. Prefer Marian whenever a pair exists.
- Model weights may be trained on OPUS data with mixed upstream licenses; the
  model card is the authoritative source for each release.

### Spanish voices (Piper)

| ID | Variant | Size | License summary | Commercial use |
|---|---|---|---|---|
| `piper-es-mx-ald-medium` | es-MX | 63 MB | Piper repo MIT; Ald dataset Unlicense | Yes |
| `piper-es-mx-claude-high` | es-MX | 110 MB | Piper repo MIT; check voice MODEL_CARD | Check |
| `piper-es-es-davefx-medium` | es-ES | 63 MB | Piper repo MIT; check voice MODEL_CARD | Check |

Voices come from <https://huggingface.co/rhasspy/piper-voices>. Each voice has a
`MODEL_CARD` in its folder with dataset attribution. The default Ald voice is
trained on a public-domain Mexican Spanish dataset and is the safest choice for
commercial work; still verify the card shipped with the downloaded files.

## Required files and folders

`models/manifest.json` maps each entry to `models/<local_dir>`:

```
models/
  manifest.json
  whisper-tiny/            model.bin, config.json, tokenizer.json, vocabulary.txt
  whisper-base/            ...
  marian-en-es/            pytorch_model.bin, config.json, source.spm, target.spm, ...
  nllb-200-distilled-600M/ pytorch_model.bin, config.json, sentencepiece.bpe.model, ...
  piper/es_MX-ald-medium/  es_MX-ald-medium.onnx, .onnx.json, MODEL_CARD
```

`models_manager.is_installed()` checks the required files per engine; a partial
download is reported as not installed. Hugging Face metadata is cached under
`models/<id>/.cache` and can be kept for resumable downloads.

## Commands

```powershell
# List IDs, licenses, sizes and install state
.\.venv\Scripts\python.exe backend\download_models.py --list

# Recommended minimal set
.\.venv\Scripts\python.exe backend\download_models.py --minimal

# One or more specific models
.\.venv\Scripts\python.exe backend\download_models.py whisper-base marian-en-es

# Everything (≈5.6 GB; read the NLLB license first)
.\.venv\Scripts\python.exe backend\download_models.py --all
```

In the UI: **Modelos → Descargar**. Downloads run in the background; the page
shows progress and the app reports when a model is ready. The application never
downloads weights implicitly, and it does not check for updates online.

### Removing models

Use **Modelos → Eliminar** or:

```powershell
Invoke-RestMethod -Method Delete -Uri http://127.0.0.1:8765/api/models/nllb-600m `
  -Headers @{ "X-VTS-Client" = "web" }
```

Removing weights is immediate; jobs that need them will fail with a clear
`model_missing` error and keep their artifacts for later.

### Manual/offline installation

Copy a Hugging Face repository into the exact `local_dir` with the file names
listed in the manifest. For faster-whisper use the CTranslate2 files
(`model.bin`, `config.json`, `tokenizer.json`, `vocabulary.txt`), not the original
OpenAI `.pt` weights. For Marian/NLLB, all PyTorch and SentencePiece files are
needed.

Verify:

```powershell
.\.venv\Scripts\python.exe backend\verify_install.py --strict
```

## Offline behavior

- Model loading uses `local_files_only=True`; no request is made at inference.
- The download manager is the only code path that touches the network, and only
  from an explicit endpoint/CLI call.
- If a download fails midway, installed state stays false and the app tells you
  which stage is missing. Retrying resumes from the Hugging Face cache.

## Licenses and redistribution

If you redistribute this project folder:

- Keep `THIRD_PARTY_NOTICES.md`, the FFmpeg `LICENSE` and model `MODEL_CARD`
  files.
- Do **not** bundle NLLB-200 weights for commercial distribution.
- The bundled FFmpeg build is GPLv3; distributing the binary requires complying
  with the GPL (including source availability). If that is a problem, replace it
  with an LGPL build and update `VTS_FFMPEG`/`VTS_FFPROBE`.
- Piper voice datasets may have attribution requirements even when the model
  repository is MIT.
- `storage/` and `models/*` are ignored by git; they are user data, not source.
