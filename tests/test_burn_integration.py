"""Opt-in local ffmpeg check: RUN_FFMPEG_TESTS=1 python -m unittest discover -s tests.

Creates tiny synthetic videos; no model, API, network, or user media is used.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ja_video_subtitles import PROJECT_ROOT
from ja_video_subtitles.ffmpeg_util import find_ffmpeg, find_ffprobe


@unittest.skipUnless(os.environ.get("RUN_FFMPEG_TESTS") == "1",
                     "set RUN_FFMPEG_TESTS=1 for local hardware encoding checks")
class TestRealBurn(unittest.TestCase):
    def test_single_multiple_and_directory_with_special_paths(self):
        self.assertEqual(sys.platform, "darwin", "hardware burn requires macOS")
        ffmpeg = find_ffmpeg()
        self.assertIsNotNone(ffmpeg, "ffmpeg with libass required")
        ffprobe = find_ffprobe(ffmpeg)
        self.assertIsNotNone(ffprobe, "ffprobe required")
        with tempfile.TemporaryDirectory(prefix="ja-burn-integration-") as temp:
            root = Path(temp)
            # Copy only code, so the launcher sees neither user config nor models.
            project = root / "project"
            shutil.copytree(PROJECT_ROOT / "ja_video_subtitles",
                            project / "ja_video_subtitles",
                            ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copy2(PROJECT_ROOT / "ja-video-subtitles", project)
            (project / ".venv").symlink_to(PROJECT_ROOT / ".venv",
                                           target_is_directory=True)
            inputs, subs = root / "videos", root / "字幕's [v1],:;\\ dir"
            inputs.mkdir()
            subs.mkdir()
            first, second = inputs / "試験 one.mp4", inputs / "second.mov"
            subprocess.run([
                str(ffmpeg), "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                "-i", "color=c=blue:s=640x360:r=24:d=1", "-f", "lavfi",
                "-i", "sine=frequency=440:duration=1", "-c:v", "h264_videotoolbox",
                "-pix_fmt", "yuv420p", "-c:a", "aac", str(first),
            ], check=True, capture_output=True, timeout=30)
            subprocess.run([
                str(ffmpeg), "-hide_banner", "-loglevel", "error", "-i", str(first),
                "-c", "copy", str(second),
            ], check=True, capture_output=True, timeout=30)
            for video in (first, second):
                (subs / f"{video.stem}.bilingual.srt").write_text(
                    "1\n00:00:00,000 --> 00:00:00,900\nこんにちは\n你好\n\n",
                    encoding="utf-8-sig")
            before = {p: hashlib.sha256(p.read_bytes()).digest()
                      for directory in (inputs, subs) for p in directory.iterdir()}

            def invoke(*args):
                result = subprocess.run(
                    [str(project / "ja-video-subtitles"), "burn",
                     *map(str, args)], cwd=root, capture_output=True, text=True,
                    timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result.stdout

            # Explicit subtitles, with every filtergraph-special path character.
            single = root / "single"
            invoke(first.relative_to(root), "-s",
                   (subs / f"{first.stem}.bilingual.srt").relative_to(root),
                   "-o", single.relative_to(root))
            # Multiple arguments, deduplicated, using the default subtitle mapping.
            batch = root / "batch"
            batch.mkdir()
            for path in subs.iterdir():
                (batch / path.name).write_bytes(path.read_bytes())
            stdout = invoke(first, second, first, "-o", batch)
            self.assertIn("2 succeeded, 0 failed, 0 skipped", stdout)
            # Directory expansion and separate subtitle directory; overwrite upfront.
            stdout = invoke(inputs, "--subtitle-dir", subs, "-o", batch, "-y")
            self.assertIn("2 succeeded, 0 failed, 0 skipped", stdout)

            for output in (single / f"{first.stem}.sub.mp4",
                           batch / f"{first.stem}.sub.mp4", batch / "second.sub.mp4"):
                probe = subprocess.run([
                    str(ffprobe), "-v", "error", "-show_entries",
                    "stream=codec_name,codec_type:format=duration", "-of", "json",
                    str(output),
                ], check=True, capture_output=True, text=True, timeout=10)
                info = json.loads(probe.stdout)
                self.assertEqual([(s["codec_type"], s["codec_name"])
                                  for s in info["streams"]],
                                 [("video", "h264"), ("audio", "aac")])
                self.assertGreaterEqual(float(info["format"]["duration"]), 0.9)
            # White caption pixels must be present on the otherwise blue frame.
            frame = subprocess.run([
                str(ffmpeg), "-v", "error", "-ss", "0.4", "-i",
                str(single / f"{first.stem}.sub.mp4"), "-frames:v", "1",
                "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1",
            ], check=True, capture_output=True, timeout=10).stdout
            white_pixels = sum(all(c > 180 for c in frame[i:i + 3])
                               for i in range(0, len(frame), 3))
            self.assertGreater(white_pixels, 100, "expected visible caption pixels")
            self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).digest()
                                      for p in before})


if __name__ == "__main__":
    unittest.main()
