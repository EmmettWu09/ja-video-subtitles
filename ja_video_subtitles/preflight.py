"""Startup preflight: all 8 checks must pass before any processing starts."""

import importlib
import shutil
import sys
from pathlib import Path

from . import model as model_mod
from .config import Config, api_key_valid, load
from .ffmpeg_util import find_ffmpeg

REQUIRED_PACKAGES = ["faster_whisper", "openai", "srt", "tqdm", "huggingface_hub"]


class PreflightError(Exception):
    pass


def run(videos: list[Path], out_dir: Path) -> tuple[Config, Path]:
    """Return (config, ffmpeg path); raise PreflightError on any failure."""
    errors: list[str] = []

    # 0. macOS only (VideoToolbox encoder, PingFang SC font, brew ffmpeg paths)
    if sys.platform != "darwin":
        errors.append("macOS only: burning relies on VideoToolbox hardware "
                      "encoding and the PingFang SC font")

    # 1. Python version and required packages
    if sys.version_info < (3, 12):
        errors.append(f"Python >= 3.12 required (current "
                      f"{sys.version.split()[0]})")
    missing = [p for p in REQUIRED_PACKAGES if not _importable(p)]
    if missing:
        errors.append(f"missing packages: {', '.join(missing)}. Run: "
                      "uv pip install --python .venv/bin/python "
                      "-r requirements.txt")

    # 2. ffmpeg with the subtitles filter (libass)
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        errors.append("no ffmpeg with the subtitles filter (libass) found. "
                      "Install: brew install homebrew-ffmpeg/ffmpeg/ffmpeg-full")

    # 3. config file and api_key
    cfg: Config | None = None
    try:
        cfg = load()
        if not api_key_valid(cfg):
            errors.append("deepseek.api_key in config.toml is empty or "
                          "still the placeholder")
    except Exception as e:
        errors.append(str(e))

    # 4. DeepSeek API connectivity
    if cfg is not None and api_key_valid(cfg):
        try:
            from openai import OpenAI
            client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key,
                            timeout=15)
            client.chat.completions.create(
                model=cfg.model, max_tokens=1,
                messages=[{"role": "user", "content": "ping"}])
        except Exception as e:
            errors.append(f"DeepSeek API connectivity check failed: {e}")

    # 5. ASR model ready (never auto-download here)
    if cfg is not None and not model_mod.model_ready(cfg.asr_model_id):
        errors.append("ASR model not downloaded. Run: ja-video-subtitles download")

    # 6. Free disk space >= 2x total input size
    #    (walk up to the first existing ancestor for the stat)
    total_size = sum(v.stat().st_size for v in videos)
    try:
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

    # 7. Output directory creatable and writable
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        probe = out_dir / ".write_probe"
        probe.touch()
        probe.unlink()
    except OSError as e:
        errors.append(f"output directory {out_dir} is not writable: {e}")

    if errors:
        raise PreflightError("\n".join(f"  x {e}" for e in errors))
    return cfg, ffmpeg


def _importable(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False
