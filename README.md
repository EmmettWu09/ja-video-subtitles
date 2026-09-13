# ja-video-subtitles

**Any Japanese video in -> one command -> JA/ZH bilingual hard-subtitled video out.**

Pipeline: `video -> transcribe (kotoba-whisper) -> translate (DeepSeek) -> vocabulary -> bilingual merge -> burn (ffmpeg)`

## How it works

| Stage | What happens | Output |
|---|---|---|
| Transcribe | Local ASR (kotoba-whisper on CPU, no network): Japanese audio -> timestamped JA subtitles, with VAD + hallucination filtering + punctuation-based splitting | `xxx.ja.srt` |
| Translate | JA -> ZH via DeepSeek API, in numbered batches with context; retries/falls back automatically on malformed replies | `xxx.zh.srt` |
| Vocabulary | Local morphology and unofficial JLPT lookup, with Simplified Chinese definitions from the configured API | `xxx.vocab.md`, `xxx.vocab.json` |
| Bilingual merge | Aligns JA/ZH line by line (JA on top, ZH below); local, instant | `xxx.bilingual.srt` |
| Burn | ffmpeg draws the subtitles onto frames and re-encodes with VideoToolbox hardware encoding | `xxx.sub.mp4` |

Transcription, vocabulary extraction/JLPT lookup, merging, and burning run locally. Translation sends subtitle text to the configured API; vocabulary definitions send deduplicated words and Japanese example sentences to that same service. Audio and video are not uploaded by these stages. The default API model is `deepseek-flash`. Per-stage durations appear in `report-*.md`.

Accepts mp4/mov, a single file or a whole folder; `burn` also accepts multiple files and folders in one command. All artifacts go to the `-o` directory; source videos are never modified.

> **For `run`, input must be Japanese speech.** Transcription is fixed to `language="ja"` (kotoba-whisper is a Japanese-only model). There is no language detection: non-Japanese audio will NOT error out — it silently produces garbage subtitles. `burn` uses your existing SRT without transcribing audio.

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
| DeepSeek API key | JA->ZH translation and vocabulary definitions | [DeepSeek platform](https://platform.deepseek.com) |
| SudachiPy / SudachiDict-core | Local vocabulary morphology | Installed by `requirements.txt`; dictionary download is about 70 MB |

Subtitle font needs no install (PingFang SC ships with macOS).

## Setup

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp config.example.toml config.toml   # then fill in deepseek.api_key
./ja-video-subtitles download                 # one-time ASR model download (~1.5GB)
```

The model lands in the project-local `.cache/hf/` (`HF_HOME` is pinned there) with a `.model-ready` marker. Download defaults to the `hf-mirror.com` mirror; override with `HF_ENDPOINT=https://huggingface.co`.

For `burn` only, install Python, `srt`, `tqdm`, and ffmpeg; you can skip copying the config, adding an API key, and downloading the ASR model or vocabulary dictionaries. If `config.toml` exists, only its subtitle style and video bitrate settings apply; otherwise the defaults are used. `burn` ignores vocabulary settings and does not import the tokenizer or load JLPT data.

## Usage

```bash
./ja-video-subtitles run /path/to/xxx.mp4 -o /path/to/output   # single file
./ja-video-subtitles run /path/to/dir   -o /path/to/output     # all mp4/mov in a folder
./ja-video-subtitles run /path/to/dir   -o out -y              # auto-overwrite outputs
./ja-video-subtitles run xxx.mp4 -o out --force                # redo every stage
```

### Burn existing subtitles

```bash
./ja-video-subtitles burn xxx.mp4 -o out                         # use out/xxx.bilingual.srt
./ja-video-subtitles burn xxx.mp4 -s edited.srt -o out           # choose a single SRT
./ja-video-subtitles burn first.mp4 second.mov -o out            # multiple files
./ja-video-subtitles burn first.mp4 second.mov --subtitle-dir subtitles -o out -y
./ja-video-subtitles burn /path/to/videos --subtitle-dir subtitles -o out
```

`burn` only encodes the video with existing subtitles. Each result is `<out>/<stem>.sub.mp4`, with `run.log` and `report-*.md`; subtitle files are not generated or changed. The default subtitle path is `<out>/<stem>.bilingual.srt`, or `<subtitle-dir>/<stem>.bilingual.srt` with `--subtitle-dir`. Use `-s/--subtitles` for an arbitrary SRT filename when processing exactly one unique video; it cannot be combined with `--subtitle-dir`.

You can mix file and folder inputs. Folders are scanned in filename order without recursion, and repeated resolved video paths are processed once. Any supplied folder with no direct mp4/mov files stops the whole batch. Different videos with the same stem (case-insensitive), or output paths that would overwrite any source video, are rejected before burning. Every matched subtitle must be a readable, nonempty UTF-8 SRT; one missing or invalid subtitle stops the whole batch before any encoding.

Existing videos are confirmed upfront; `-y/--yes` overwrites them automatically, and EOF skips them. `burn` has no `--force` option. After preflight, individual encoding failures are recorded and the remaining videos continue. Exit codes: `0` for success/skips, `1` if any encoding fails, `2` for invalid input/subtitles/config or failed preflight. No API or ASR model is checked or loaded.

### Full pipeline outputs and behavior

`run` outputs in `-o` (nothing written next to the source):

| File | What |
|---|---|
| `xxx.ja.srt` / `xxx.ja.json` | Japanese subtitles / confidence log (for hallucination debugging) |
| `xxx.zh.srt` | Chinese subtitles |
| `xxx.vocab.md` / `xxx.vocab.json` | Readable vocabulary glossary / structured entries and resume metadata (when enabled) |
| `xxx.bilingual.srt` | Bilingual subtitles (JA on top, ZH below) |
| `xxx.sub.mp4` | Final hard-subtitled video |
| `report-<timestamp>.md` | Run report: config summary, per-stage durations, products, failures |
| `run.log` | Full run log |

Behavior notes:

- **Relative paths resolve against your cwd**; config and the model cache are always read from the project directory, so the tool works from anywhere.
- **Resume**: existing valid artifacts are skipped; corrupt/empty ones are re-generated. `run` reuses bilingual subtitles only when they match a fresh merge of the current JA/ZH subtitles. Editing either source subtitle refreshes the bilingual output before burning; use `burn` to render a manually edited standalone SRT unchanged.
- **Overwrite**: existing `xxx.sub.mp4` files trigger one batch of upfront `Overwrite? [y/N]` prompts; burning never blocks midway. Non-interactive sessions default to "no". `-y` auto-overwrites, `--force` redoes everything.
- **Preflight**: platform, Python deps, ffmpeg+libass, config/api_key, DeepSeek connectivity, ASR model, disk space >= 2x input, and a writable output directory. When vocabulary is enabled, the tokenizer, local dictionary, and JLPT data/schema/version/checksums must also pass; failure exits before any video processing with a repair hint.
- **Results**: a vocabulary stage failure still allows merge/burn, marks that video `partial`, and makes the batch exit with code `1`. Other processing failures are `failed`; confirmed skips are `skipped`. A word whose definition fails after retries remains in the glossary with an empty definition and warning; this counts as a degraded definition, not a stage failure. Reports list all four video result counts, vocabulary level/degradation counts, errors, and existing artifacts without API keys.
- **Ctrl+C** during burning kills ffmpeg and removes the partial file.

### Vocabulary settings

The optional `[vocabulary]` section in project-root `config.toml` defaults to:

```toml
[vocabulary]
enabled = true
learner_level = "N3"
include_unknown = true
max_examples = 3
```

`learner_level` accepts `N5` through `N1`: only harder levels are included, so N3 selects N2/N1. `include_unknown` includes ungraded content words and marks proper nouns; an ungraded word is not necessarily difficult. `enabled` and `include_unknown` must be booleans; `max_examples` must be an integer from 1 to 10. Each entry records the dictionary form, reading, observed forms, frequency, first timestamp, and up to that many distinct Japanese subtitle contexts with the existing Chinese translations. No matching words produces a valid empty glossary.

Levels come from pinned, non-official JLPT reference data, never from the API. See the [dataset source, license, and limitations](ja_video_subtitles/data/README.md). JSON records subtitle hashes, settings, data version, and morphology versions. Resume reuses a glossary only if both files are valid and all metadata still matches; changes to Japanese/Chinese subtitles, settings, or data rebuild it. `--force` rebuilds every stage. Re-running with existing finished videos also needs `-y` or an affirmative overwrite response.

Set `enabled = false` to skip vocabulary and its local dependency checks. To repair an enabled setup, reinstall the pinned dependencies and, if needed, rebuild the exact bundled reference:

```bash
uv pip install --python .venv/bin/python --reinstall-package SudachiPy --reinstall-package SudachiDict-core -r requirements.txt
.venv/bin/python ja_video_subtitles/data/rebuild_jlpt.py
```

## Testing

```bash
.venv/bin/python -m unittest discover -s tests
```

Offline unit tests; neither the ASR model nor the DeepSeek API is needed.

On a Mac with ffmpeg installed, also run the real burn checks. They generate tiny
videos locally and use an isolated copy of the code without config or models:

```bash
RUN_FFMPEG_TESTS=1 .venv/bin/python -m unittest discover -s tests
```

## Code layout

```
video-subtitles/
├── ja-video-subtitles                # launcher (no cd; package located via PYTHONPATH)
├── ja_video_subtitles/               # main package, one module per stage
│   ├── __init__.py          # version; project root; HF_HOME/HF_ENDPOINT pinning
│   ├── cli.py               # run/download/burn; pipeline, standalone burning, prompts, tee log, report
│   ├── config.py            # config.toml loading + defaults; optional config for burn
│   ├── preflight.py         # full pipeline and burn-only startup checks
│   ├── model.py             # `download`: model fetch + .model-ready marker
│   ├── transcribe.py        # JA transcription: faster-whisper + kotoba; VAD, hallucination filter, punctuation split; model cached
│   ├── translate.py         # JA->ZH: batched, context-aware, numbering-checked, retry/halve fallback
│   ├── vocabulary.py        # local extraction, API definitions, atomic glossary outputs + resume validation
│   ├── jlpt_lexicon.py      # versioned local JLPT reference validation + unambiguous lookup
│   ├── data/                # pinned JLPT data, attribution/license, reproducible rebuild script
│   ├── merge.py             # ja/zh position-aligned -> bilingual.srt
│   ├── burn.py              # ffmpeg subtitles filter: progress parsing, stderr-to-file (no deadlock), cleanup on failure/Ctrl+C
│   ├── ffmpeg_util.py       # ffmpeg/ffprobe discovery (libass check), duration probe, filter path escaping
│   └── report.py            # report-<timestamp>.md (durations/products/failures; never logs secrets)
├── tests/                   # offline regression tests + opt-in real ffmpeg checks
├── openspec/                # OpenSpec docs: proposal / design / tasks / specs
├── config.example.toml      # config template (real config.toml is gitignored)
├── requirements.txt         # faster-whisper / openai / srt / tqdm / pinned SudachiPy + dictionary
├── LICENSE                  # MIT
└── README.md
```

## Expected timing (1-hour video, Apple Silicon)

| Stage | Time |
|---|---|
| Transcribe | ~10-20 min |
| Translate | ~2-5 min |
| Vocabulary | Depends on unique target words and API latency; see the run report |
| Burn | ~5-15 min (VideoToolbox) |

## Design docs

See the [pipeline design](openspec/changes/archive/2026-09-01-add-video-subtitle-pipeline/design.md), [standalone burn change](openspec/changes/archive/2026-09-13-add-standalone-burn-command/proposal.md), and [vocabulary glossary change](openspec/changes/archive/2026-09-13-add-jlpt-vocabulary-glossary/proposal.md) (in Chinese).

## License

Code: MIT, see `LICENSE`. Bundled JLPT data has its own attribution and license; see [data documentation](ja_video_subtitles/data/README.md).
