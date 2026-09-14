"""Startup checks for the full pipeline and standalone subtitle burning."""

import importlib
import shutil
import sys
import tempfile
from pathlib import Path

from . import audio, model as model_mod
from .api_util import chat_options, safe_error
from .config import (BurnConfig, Config, api_key_valid, load, load_burn,
                     vocabulary_output_dir)
from .ffmpeg_util import find_ffmpeg, find_ffprobe

REQUIRED_PACKAGES = ["faster_whisper", "openai", "srt", "tqdm", "huggingface_hub"]
BURN_REQUIRED_PACKAGES = ["srt", "tqdm"]


class PreflightError(Exception):
    pass


def run(videos: list[Path], out_dir: Path, *,
        vocab_output_dir: str | None = None,
        vocab_format: str | None = None) -> tuple[Config, Path]:
    """Return (config, ffmpeg path); raise PreflightError on any failure."""
    errors = _check_runtime(REQUIRED_PACKAGES)

    # 2. ffmpeg with the subtitles filter (libass)
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        errors.append("no ffmpeg with the subtitles filter (libass) found. "
                      "Install: brew install homebrew-ffmpeg/ffmpeg/ffmpeg-full")
    elif not audio.has_mp3_encoder(ffmpeg):
        errors.append("ffmpeg has no libmp3lame MP3 encoder. "
                      "Install: brew install homebrew-ffmpeg/ffmpeg/ffmpeg-full")

    # 3. config file and api_key
    cfg: Config | None = None
    try:
        cfg = load()
        if vocab_output_dir is not None:
            if not vocab_output_dir or "\x00" in vocab_output_dir:
                raise ValueError("--vocab-output-dir must be a nonempty path")
            cfg.vocabulary_output_dir = vocab_output_dir
        if vocab_format is not None:
            if vocab_format not in ("md", "json", "both"):
                raise ValueError("--vocab-format must be one of md/json/both")
            cfg.vocabulary_format = vocab_format
        if not api_key_valid(cfg):
            errors.append("deepseek.api_key in config.toml is empty or "
                          "still the placeholder")
    except Exception as e:
        errors.append(str(e))
        cfg = None

    # 4. DeepSeek API connectivity
    if cfg is not None and api_key_valid(cfg):
        try:
            from openai import OpenAI
            client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key,
                            timeout=15)
            client.chat.completions.create(
                model=cfg.model, max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
                **chat_options(cfg))
        except Exception as e:
            errors.append("DeepSeek API connectivity check failed: "
                          f"{safe_error(e, cfg.api_key)}")

    # 5. ASR model ready (never auto-download here)
    if cfg is not None and not model_mod.model_ready(cfg.asr_model_id):
        errors.append("ASR model not downloaded. Run: ja-video-subtitles download")

    # Vocabulary is optional; keep its imports and dictionaries out of burn.
    if cfg is not None and cfg.vocabulary_enabled:
        try:
            from . import vocabulary
            vocabulary.check_ready()
        except Exception as e:
            errors.append(
                f"Vocabulary prerequisites not ready: {safe_error(e, cfg.api_key)}. "
                "Install/repair dependencies: uv pip install --python .venv/bin/python "
                "--reinstall-package SudachiPy --reinstall-package SudachiDict-core "
                "-r requirements.txt; restore the bundled JLPT data with "
                ".venv/bin/python ja_video_subtitles/data/rebuild_jlpt.py, "
                "or set vocabulary.enabled = false.")

    errors.extend(_check_output(videos, out_dir))
    if cfg is not None and cfg.vocabulary_enabled:
        try:
            vocab_dir = vocabulary_output_dir(cfg, out_dir)
            if vocab_dir.resolve() != out_dir.resolve():
                errors.extend(_check_output([], vocab_dir))
        except (OSError, RuntimeError) as e:
            errors.append(f"cannot resolve vocabulary output directory: {e}")

    if errors:
        raise PreflightError("\n".join(f"  x {e}" for e in errors))
    return cfg, ffmpeg


def run_burn(videos: list[Path], out_dir: Path) -> tuple[BurnConfig, Path]:
    """Check local burning prerequisites without ASR or translation services."""
    errors = _check_runtime(BURN_REQUIRED_PACKAGES)
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        errors.append("no ffmpeg with the subtitles filter (libass) found. "
                      "Install: brew install homebrew-ffmpeg/ffmpeg/ffmpeg-full")
    elif find_ffprobe(ffmpeg) is None:
        errors.append("no ffprobe found for reading video duration. "
                      "Install ffmpeg/ffprobe: "
                      "brew install homebrew-ffmpeg/ffmpeg/ffmpeg-full")
    cfg: BurnConfig | None = None
    try:
        cfg = load_burn()
    except Exception as e:
        errors.append(str(e))
    errors.extend(_check_output(videos, out_dir))
    if errors:
        raise PreflightError("\n".join(f"  x {e}" for e in errors))
    assert cfg is not None and ffmpeg is not None
    return cfg, ffmpeg


def _check_runtime(packages: list[str]) -> list[str]:
    errors: list[str] = []
    if sys.platform != "darwin":
        errors.append("macOS only: burning relies on VideoToolbox hardware "
                      "encoding and the PingFang SC font")
    if sys.version_info < (3, 12):
        errors.append(f"Python >= 3.12 required (current "
                      f"{sys.version.split()[0]})")
    missing = [p for p in packages if not _importable(p)]
    if missing:
        errors.append(f"missing packages: {', '.join(missing)}. Run: "
                      "uv pip install --python .venv/bin/python "
                      "-r requirements.txt")
    return errors


def _check_output(videos: list[Path], out_dir: Path) -> list[str]:
    errors: list[str] = []
    # Free disk space >= 2x total input size. Walk up to an existing ancestor.
    try:
        total_size = sum(v.stat().st_size for v in videos)
        probe_dir = out_dir
        while not probe_dir.exists():
            probe_dir = probe_dir.parent
        free = shutil.disk_usage(probe_dir).free
        if free < total_size * 2:
            errors.append(f"insufficient disk space: need ~"
                          f"{total_size * 2 / 1e9:.1f}GB, "
                          f"{free / 1e9:.1f}GB free")
    except OSError as e:
        errors.append(f"cannot check disk space: {e}")

    # Probe an exclusively created temporary file, preserving existing files.
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(prefix=".write_probe-", dir=out_dir) as probe:
            probe.write(b"probe")
            probe.flush()
    except OSError as e:
        errors.append(f"output directory {out_dir} is not writable: {e}")

    return errors


def _importable(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False
