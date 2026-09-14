"""Export the first original audio stream to <out>/xxx.mp3."""

import subprocess
import tempfile
from pathlib import Path

from tqdm import tqdm

from .ffmpeg_util import find_ffprobe, probe_duration


def has_mp3_encoder(ffmpeg: Path) -> bool:
    """Check encoder availability without processing any user media."""
    try:
        result = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-h", "encoder=libmp3lame"],
            capture_output=True, text=True, timeout=15,
        )
        return (result.returncode == 0
                and "Encoder libmp3lame " in result.stdout + result.stderr)
    except (OSError, subprocess.TimeoutExpired):
        return False


def export(video: Path, out_dir: Path, ffmpeg: Path) -> Path:
    """Write an audio-only MP3, replacing an existing output only on success."""
    ffprobe = find_ffprobe(ffmpeg)
    duration = None
    if ffprobe:
        try:
            duration = probe_duration(ffprobe, video)
        except (OSError, subprocess.SubprocessError, ValueError):
            # Duration is only needed for progress; ffmpeg reports input errors.
            pass

    out_dir.mkdir(parents=True, exist_ok=True)
    out_mp3 = out_dir / f"{video.stem}.mp3"
    with tempfile.NamedTemporaryFile(
        prefix=".audio-", suffix=".mp3", dir=out_dir, delete=False,
    ) as temp:
        partial = Path(temp.name)
    cmd = [
        str(ffmpeg), "-nostdin", "-y", "-i", str(video.resolve()),
        "-map", "0:a:0", "-vn", "-sn", "-dn",
        "-c:a", "libmp3lame", "-b:a", "192k", "-ac", "2",
        "-nostats", "-progress", "pipe:1", str(partial.resolve()),
    ]
    try:
        # A temporary stderr file avoids blocking ffmpeg on a full stderr pipe.
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8",
                                    errors="replace") as err_file:
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                        stderr=err_file, text=True)
            except OSError as exc:
                raise RuntimeError(f"could not start ffmpeg MP3 export: {exc}") from exc
            assert proc.stdout is not None
            try:
                bar_format = ("{l_bar}{bar}| {n:.0f}/{total:.0f}s" if duration
                              else "{desc}: {n:.0f}s")
                with proc.stdout, tqdm(total=duration, unit="s",
                                       desc=f"Exporting MP3 {video.name}",
                                       bar_format=bar_format) as bar:
                    for line in proc.stdout:
                        if line.startswith("out_time_us="):
                            position = max(0, int(line.split("=", 1)[1]) / 1e6)
                            if duration:
                                position = min(duration, position)
                            bar.update(position - bar.n)
                    proc.wait()
                    if proc.returncode == 0 and bar.total:
                        bar.update(bar.total - bar.n)
            except BaseException:  # Ctrl+C must also preserve existing outputs.
                proc.kill()
                proc.wait()
                raise
            if proc.returncode != 0:
                err_file.seek(0)
                err = err_file.read()[-2000:]
                reason = ("input has no audio stream" if "matches no streams" in err
                          else "ffmpeg MP3 export failed")
                raise RuntimeError(
                    f"{reason} for {video.name} (exit code {proc.returncode}):\n{err}")
        partial.replace(out_mp3)
    finally:
        partial.unlink(missing_ok=True)
    print(f"[audio] output -> {out_mp3}")
    return out_mp3
