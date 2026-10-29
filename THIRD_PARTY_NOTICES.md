# Third-party notices

Spanish Dubbing Studio (the "app") is MIT-licensed (see [LICENSE](LICENSE)).
It depends on the software and model weights below. This file is provided for
attribution and compliance; it is not legal advice. Versions are pinned in
[requirements.txt](requirements.txt) and
[frontend/package.json](frontend/package.json).

## Bundled / downloaded executables

### FFmpeg and FFprobe

- **Version used:** FFmpeg 9.0.2 "essentials" build from
  [gyan.dev](https://www.gyan.dev/ffmpeg/builds/), downloaded by
  `scripts/setup.ps1` into `tools/ffmpeg`.
- **License:** **GPLv3** for this build (it enables GPL components such as
  libx264/x265). See `tools/ffmpeg/LICENSE` and `tools/ffmpeg/README.txt` when
  installed.
- **Source:** <https://ffmpeg.org/download.html> and the gyan.dev build page.
- **Why it matters:** distributing the bundled binaries (or an app installer that
  contains them) requires GPL compliance, including source availability. The app
  calls FFmpeg as a separate process. If GPL distribution is unacceptable, use an
  LGPL FFmpeg build and point `VTS_FFMPEG`/`VTS_FFPROBE` at it.
- FFmpeg is a trademark of Fabrice Bellard, originator of the FFmpeg project.

### Piper

- **Version:** Piper 1.2.0 standalone Windows build (`piper_windows_amd64.zip`,
  release 2023.11.14-2) from <https://github.com/rhasspy/piper>.
- **License:** MIT for the Piper project. `piper.exe` embeds/links
  [espeak-ng](https://github.com/espeak-ng/espeak-ng) (GPLv3) for phonemization,
  [ONNX Runtime](https://github.com/microsoft/onnxruntime) (MIT) and
  [piper-phonemize](https://github.com/rhasspy/piper-phonemize) (MIT). The
  distributed zip includes the corresponding DLLs and `espeak-ng-data`.
- Voice models are downloaded separately and have their own dataset terms; see
  [docs/MODELS.md](docs/MODELS.md#spanish-voices-piper).

## AI model weights (downloaded, not part of the source tree)

| Model family | Provider / repository | License | Commercial use |
|---|---|---|---|
| Whisper Tiny/Base/Small (faster-whisper) | Systran / OpenAI Whisper | MIT | Yes |
| MarianMT OPUS-MT pairs | Helsinki-NLP | Apache-2.0 | Yes |
| NLLB-200 Distilled 600M | Meta / Facebook | **CC-BY-NC-4.0** | **No** |
| Piper voices (`es_MX-ald-medium`, `es_MX-claude-high`, `es_ES-davefx-medium`) | rhasspy/piper-voices | MIT repo + per-voice dataset card (Ald: Unlicense; others: check `MODEL_CARD`) | Check the card |

Model files are **not** included in this repository and are not downloaded
automatically. Each model folder keeps its `MODEL_CARD`/license metadata. See
[docs/MODELS.md](docs/MODELS.md) for sizes, links and attribution requirements.

Training data notices: OPUS-MT models are trained on OPUS corpora with mixed
upstream licenses; Whisper weights derive from OpenAI's release; NLLB's license
is non-commercial. The model card is authoritative for each downloaded snapshot.

## Python runtime dependencies

| Package | License | Project |
|---|---|---|
| fastapi | MIT | https://github.com/fastapi/fastapi |
| starlette | BSD-3-Clause | https://github.com/encode/starlette |
| uvicorn | BSD-3-Clause | https://github.com/encode/uvicorn |
| pydantic / pydantic-core | MIT | https://github.com/pydantic/pydantic |
| python-multipart | Apache-2.0 | https://github.com/Kludex/python-multipart |
| psutil | BSD-3-Clause | https://github.com/giampaolo/psutil |
| numpy | BSD-3-Clause | https://numpy.org |
| soundfile | BSD-3-Clause | https://github.com/bastibe/python-soundfile |
| libsndfile (used by soundfile) | LGPL-2.1 | https://github.com/libsndfile/libsndfile |
| huggingface-hub | Apache-2.0 | https://github.com/huggingface/huggingface_hub |
| faster-whisper | MIT | https://github.com/SYSTRAN/faster-whisper |
| CTranslate2 | MIT | https://github.com/OpenNMT/CTranslate2 |
| transformers | Apache-2.0 | https://github.com/huggingface/transformers |
| tokenizers | Apache-2.0 | https://github.com/huggingface/tokenizers |
| sentencepiece | Apache-2.0 | https://github.com/google/sentencepiece |
| sacremoses | LGPL-2.1 | https://github.com/hplt-project/sacremoses |
| torch (CPU wheel) | BSD-3-Clause | https://github.com/pytorch/pytorch |
| SQLite (via Python stdlib) | Public domain | https://sqlite.org |

The CPU PyTorch wheel has no NVIDIA CUDA redistributables. If you replace it with
a CUDA wheel, NVIDIA's CUDA/cuDNN license terms also apply.

## Python test dependencies

| Package | License |
|---|---|
| pytest | MIT |
| httpx | BSD-3-Clause |

## Frontend dependencies

| Package | License | Project |
|---|---|---|
| react, react-dom | MIT | https://github.com/facebook/react |
| react-router-dom | MIT | https://github.com/remix-run/react-router |
| lucide-react | ISC | https://github.com/lucide-icons/lucide |
| vite | MIT | https://github.com/vitejs/vite |
| @vitejs/plugin-react | MIT | https://github.com/vitejs/vite-plugin-react |
| typescript | Apache-2.0 | https://github.com/microsoft/TypeScript |
| tailwindcss | MIT | https://github.com/tailwindlabs/tailwindcss |
| postcss | MIT | https://github.com/postcss/postcss |
| autoprefixer | MIT | https://github.com/postcss/autoprefixer |
| @types/react, @types/react-dom | MIT | https://github.com/DefinitelyTyped/DefinitelyTyped |

The production bundle includes only the runtime packages above (React, React
DOM, React Router, Lucide); the rest are build-time tools.

## Development/download sources

- Hugging Face Hub is contacted only when the user explicitly downloads a model.
- gyan.dev and GitHub are contacted only during setup to fetch FFmpeg/Piper.
- No analytics, crash reporting, CDN fonts, remote images or telemetry are used.

## Trademarks

OpenAI, Whisper, PyTorch, Hugging Face, FFmpeg, Piper, NVIDIA and other names are
trademarks of their respective owners. This project is not affiliated with or
endorsed by them.

## Reporting attribution issues

If a license or attribution is missing or incorrect, open an issue with the
model/tool ID and the relevant model card before using the project commercially.
