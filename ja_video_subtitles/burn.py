"""Burn-in: ffmpeg subtitles filter -> <out>/xxx.sub.mp4."""

import subprocess
import tempfile
from pathlib import Path

from tqdm import tqdm

from .ffmpeg_util import escape_filter_path, find_ffprobe, probe_duration


def burn(video: Path, bilingual_srt: Path, out_dir: Path, ffmpeg: Path,
         force_style: str, bitrate: str = "8M") -> Path:
    ffprobe = find_ffprobe(ffmpeg)
    duration = probe_duration(ffprobe, video) if ffprobe else None

    out_mp4 = out_dir / f"{video.stem}.sub.mp4"
    vf = (f"subtitles='{escape_filter_path(bilingual_srt)}'"
          f":force_style='{force_style}'")
    cmd = [
        str(ffmpeg), "-y", "-i", str(video),
        "-vf", vf,
        "-c:v", "h264_videotoolbox", "-b:v", bitrate,
        "-c:a", "copy",
        "-nostats", "-progress", "pipe:1",
        str(out_mp4),
    ]
    # stderr goes to a temp file, not a PIPE: a full pipe buffer would
    # deadlock ffmpeg against us. It is read back only on failure.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8",
                                errors="replace") as err_file:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err_file,
                                text=True)
        assert proc.stdout is not None
        try:
            with tqdm(total=duration, unit="s", desc=f"Burning {video.name}",
                      bar_format="{l_bar}{bar}| {n:.0f}/{total:.0f}s") as bar:
                for line in proc.stdout:
                    if line.startswith("out_time_us=") and duration:
                        bar.update(min(duration,
                                       int(line.split("=", 1)[1]) / 1e6) - bar.n)
                proc.wait()
                if proc.returncode == 0 and bar.total:
                    bar.update(bar.total - bar.n)  # fill 100% only on success
        except BaseException:  # Ctrl+C etc: kill ffmpeg, drop the partial file
            proc.kill()
            proc.wait()
            out_mp4.unlink(missing_ok=True)
            raise
        if proc.returncode != 0:
            err_file.seek(0)
            err = err_file.read()[-2000:]
            out_mp4.unlink(missing_ok=True)
            raise RuntimeError(
                f"ffmpeg burn failed (exit code {proc.returncode}):\n{err}")
    print(f"[burn] output -> {out_mp4}")
    return out_mp4
