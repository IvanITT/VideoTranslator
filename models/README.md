# Models folder

This folder holds **downloaded model weights** and `manifest.json`. Weights are
excluded from git (`.gitignore`: `models/*` except this README and the manifest).
The application never downloads anything automatically: use the **Modelos** page
or an explicit CLI command.

## Minimum recommended set

```
models/
  manifest.json
  whisper-tiny/                 # speech recognition (MIT, ~75 MB)
  marian-en-es/                 # EN -> ES translation (Apache-2.0, ~312 MB)
  piper/es_MX-ald-medium/       # Spanish (Mexico) voice (MIT/Unlicense, ~63 MB)
```

Install it with:

```powershell
.\.venv\Scripts\python.exe backend\download_models.py --minimal
```

or `scripts\setup.ps1` (default). Add Whisper Base for better accuracy:

```powershell
.\.venv\Scripts\python.exe backend\download_models.py whisper-base
```

## Manifest

`manifest.json` is the source of truth for:

| Field | Meaning |
|---|---|
| `id` | Stable ID used by the API/UI |
| `stage` | `asr`, `translation` or `tts` |
| `engine` | `faster-whisper`, `marian`, `nllb`, `piper` |
| `repo_id` | Hugging Face repository |
| `local_dir` | Folder under `models/` |
| `license`, `license_url`, `commercial_use` | Licensing metadata shown in the UI |
| `approx_size_mb`, `ram_estimate_mb` | Planning values |
| `allow_patterns` / `files` | Exact files to download and their target names |
| `voice` | Piper voice metadata (ID, label, variant) |

`models_manager.is_installed()` checks the required files (`model.bin`,
`config.json`, `tokenizer.json`, … or the Piper `.onnx`). A partially downloaded
folder is reported as not installed.

## Licensing

Model licenses differ. In particular:

- **NLLB-200 (`nllb-600m`) is CC-BY-NC-4.0: non-commercial use only.**
- FFmpeg (under `../tools/ffmpeg`) is GPLv3 in the bundled build.
- Piper voice datasets can have attribution terms even though the Piper repo is
  MIT. Keep each `MODEL_CARD`.

See [../docs/MODELS.md](../docs/MODELS.md) and
[../THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

## Manual installation / offline

Download the repository from Hugging Face and place the files in the exact
`local_dir` with the names listed in the manifest. For faster-whisper use the
CTranslate2 files, not the original OpenAI `.pt` weights. Keep the Hugging Face
`.cache` folder if you want resumable downloads.

Verify:

```powershell
.\.venv\Scripts\python.exe backend\verify_install.py --strict
```

## Removing weights

Use **Modelos → Eliminar** (blocked while downloading) or delete
`models/<local_dir>`. Fetch them again when needed. Deleting a model does not
delete projects; jobs that need it fail with `model_missing` and can be resumed
after reinstalling it.
