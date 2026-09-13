"""ffmpeg/ffprobe location and small burn helpers."""

import shutil
import subprocess
from pathlib import Path

FFMPEG_FULL = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")


def _has_subtitles_filter(ffmpeg: Path) -> bool:
    try:
        r = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-h", "filter=subtitles"],
            capture_output=True, text=True, timeout=15,
        )
        return "Render text subtitles" in (r.stdout + r.stderr)
    except (OSError, subprocess.TimeoutExpired):
        return False


def find_ffmpeg() -> Path | None:
    """Locate an ffmpeg with libass (subtitles filter); prefer the
    Homebrew ffmpeg-full build."""
    candidates = [FFMPEG_FULL]
    on_path = shutil.which("ffmpeg")
    if on_path:
        candidates.append(Path(on_path))
    for c in candidates:
        if c.exists() and _has_subtitles_filter(c):
            return c
    return None


def find_ffprobe(ffmpeg: Path) -> Path | None:
    sibling = ffmpeg.parent / "ffprobe"
    if sibling.exists():
        return sibling
    on_path = shutil.which("ffprobe")
    return Path(on_path) if on_path else None


def probe_duration(ffprobe: Path, media: Path) -> float:
    r = subprocess.run(
        [str(ffprobe), "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(media)],
        capture_output=True, text=True, timeout=60,
    )
    return float(r.stdout.strip())


def escape_filter_value(value: str) -> str:
    """Escape both the option-value parser and the enclosing filtergraph.

    Return an unquoted value for subprocess argv (no shell escaping needed).
    https://ffmpeg.org/ffmpeg-filters.html#Notes-on-filtergraph-escaping
    """
    for specials in ("\\': \t\n\r", "\\'[],; \t\n\r"):
        value = "".join("\\" + ch if ch in specials else ch for ch in value)
    return value


def escape_filter_path(path: Path) -> str:
    return escape_filter_value(str(path.resolve()))
