# ja-video-subtitles

**Any Japanese video in -> one command -> JA/ZH bilingual hard-subtitled video out.**

Pipeline: `video -> transcribe (kotoba-whisper) -> translate (DeepSeek) -> bilingual merge -> burn (ffmpeg)`

## How it works

| Stage | What happens | Output |
|---|---|---|
| Transcribe | Local ASR (kotoba-whisper on CPU, no network): Japanese audio -> timestamped JA subtitles, with VAD + hallucination filtering + punctuation-based splitting | `xxx.ja.srt` |
| Translate | JA -> ZH via DeepSeek API, in numbered batches with context; retries/falls back automatically on malformed replies | `xxx.zh.srt` |
| Bilingual merge | Aligns JA/ZH line by line (JA on top, ZH below); local, instant | `xxx.bilingual.srt` |
| Burn | ffmpeg draws the subtitles onto frames and re-encodes with VideoToolbox hardware encoding | `xxx.sub.mp4` |

Transcribe and burn are CPU/encoder-bound (long videos take time); translate is network-bound; merge is instant. The per-stage durations in `report-*.md` tell you where time went.

Accepts mp4/mov, a single file or a whole folder. All artifacts go to the `-o` directory; the source directory is never touched.

> **Input must be Japanese speech.** Transcription is fixed to `language="ja"` (kotoba-whisper is a Japanese-only model). There is no language detection: non-Japanese audio will NOT error out — it silently produces garbage subtitles.

[中文文档](README.cn.md) | [日本語ドキュメント](README.ja.md)

## Platform

**macOS (Apple Silicon) only. Windows/Linux are not supported** — burning relies on VideoToolbox hardware encoding, the PingFang SC font, and Homebrew ffmpeg paths. Preflight fails fast on other platforms.

## Requirements

| Dependency | Why | Install |
|---|---|---|
| Homebrew | package manager | `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"` |
| uv | Python env manager | `brew install uv` |
| Python 3.12 | runtime | auto-installed by `uv venv` |
| ffmpeg-full | subtitle burning (libass) | `brew install homebrew-ffmpeg/ffmpeg/ffmpeg-full` |
| DeepSeek API key | JA->ZH translation | <https://platform.deepseek.com> (a 1-hour video costs < $0.15) |

Subtitle font needs no install (PingFang SC ships with macOS).

## Setup

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp config.example.toml config.toml   # then fill in deepseek.api_key
./ja-video-subtitles download                 # one-time ASR model download (~1.5GB)
```

The model lands in the project-local `.cache/hf/` (`HF_HOME` is pinned there) with a `.model-ready` marker. Download defaults to the `hf-mirror.com` mirror; override with `HF_ENDPOINT=https://huggingface.co`.

## Usage

```bash
./ja-video-subtitles run /path/to/xxx.mp4 -o /path/to/output   # single file
./ja-video-subtitles run /path/to/dir   -o /path/to/output     # all mp4/mov in a folder
./ja-video-subtitles run /path/to/dir   -o out -y              # auto-overwrite outputs
./ja-video-subtitles run xxx.mp4 -o out --force                # redo every stage
```

Outputs in `-o` (nothing written next to the source):

| File | What |
|---|---|
| `xxx.ja.srt` / `xxx.ja.json` | Japanese subtitles / confidence log (for hallucination debugging) |
| `xxx.zh.srt` | Chinese subtitles |
| `xxx.bilingual.srt` | Bilingual subtitles (JA on top, ZH below) |
| `xxx.sub.mp4` | Final hard-subtitled video |
| `report-<timestamp>.md` | Run report: config summary, per-stage durations, products, failures |
| `run.log` | Full run log |

Behavior notes:

- **Relative paths resolve against your cwd**; config and the model cache are always read from the project directory, so the tool works from anywhere.
- **Resume**: existing valid artifacts are skipped; corrupt/empty ones are re-generated.
- **Overwrite**: existing `xxx.sub.mp4` files trigger one batch of upfront `Overwrite? [y/N]` prompts; burning never blocks midway. Non-interactive sessions default to "no". `-y` auto-overwrites, `--force` redoes everything.
- **Preflight**: 8 checks (platform, Python deps, ffmpeg+libass, config/api_key, DeepSeek connectivity, ASR model, disk space >= 2x input, writable output dir); any failure exits immediately with a fix hint.
- **Ctrl+C** during burning kills ffmpeg and removes the partial file.

## Testing

```bash
.venv/bin/python -m unittest discover -s tests
```

Offline unit tests; neither the ASR model nor the DeepSeek API is needed.

## Code layout

```
video-subtitles/
├── ja-video-subtitles                # launcher (no cd; package located via PYTHONPATH)
├── ja_video_subtitles/               # main package, one module per stage
│   ├── __init__.py          # version; project root; HF_HOME/HF_ENDPOINT pinning
│   ├── cli.py               # subcommands run/download; pipeline, overwrite prompts, tee log, report
│   ├── config.py            # config.toml loading + defaults (stdlib tomllib)
│   ├── preflight.py         # 8 startup checks
│   ├── model.py             # `download`: model fetch + .model-ready marker
│   ├── transcribe.py        # JA transcription: faster-whisper + kotoba; VAD, hallucination filter, punctuation split; model cached
│   ├── translate.py         # JA->ZH: batched, context-aware, numbering-checked, retry/halve fallback
│   ├── merge.py             # ja/zh position-aligned -> bilingual.srt
│   ├── burn.py              # ffmpeg subtitles filter: progress parsing, stderr-to-file (no deadlock), cleanup on failure/Ctrl+C
│   ├── ffmpeg_util.py       # ffmpeg/ffprobe discovery (libass check), duration probe, filter path escaping
│   └── report.py            # report-<timestamp>.md (durations/products/failures; never logs secrets)
├── tests/test_smoke.py      # 14 offline unit tests
├── openspec/                # OpenSpec docs: proposal / design / tasks / specs (5 capabilities)
├── config.example.toml      # config template (real config.toml is gitignored)
├── requirements.txt         # faster-whisper / openai / srt / tqdm
├── LICENSE                  # MIT
└── README.md
```

## Expected timing (1-hour video, Apple Silicon)

| Stage | Time |
|---|---|
| Transcribe | ~10-20 min |
| Translate | ~2-5 min |
| Burn | ~5-15 min (VideoToolbox) |

## Design docs

See `openspec/changes/add-video-subtitle-pipeline/` (proposal / design / tasks / specs, in Chinese).

## License

MIT. See `LICENSE`.
