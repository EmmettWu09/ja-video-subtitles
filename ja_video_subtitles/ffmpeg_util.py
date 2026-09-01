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


def escape_filter_path(path: Path) -> str:
    """Escape a path for use inside an ffmpeg filter argument.

    The path is additionally wrapped in single quotes by the caller
    (filtergraph-level protection); here we escape \\ : ' and , for the
    option-level parser, which unescapes them back to the original chars.
    """
    s = str(path.resolve())
    for ch in ("\\", ":", "'", ","):
        s = s.replace(ch, "\\" + ch)
    return s
