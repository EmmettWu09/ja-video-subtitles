"""Exercise real run output routing, vocabulary writing, burning, and MP3 export.

Uses synthetic local media and cached subtitles; API/model preflight is stubbed.
"""

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ja_video_subtitles import cli, config
from ja_video_subtitles.ffmpeg_util import find_ffmpeg, find_ffprobe


@unittest.skipUnless(os.environ.get("RUN_FFMPEG_TESTS") == "1",
                     "set RUN_FFMPEG_TESTS=1 for real output integration checks")
class TestRealRunOutputs(unittest.TestCase):
    def test_all_vocab_formats_with_separate_directory_and_real_mp3(self):
        ffmpeg = find_ffmpeg()
        self.assertIsNotNone(ffmpeg)
        ffprobe = find_ffprobe(ffmpeg)
        self.assertIsNotNone(ffprobe)
        with tempfile.TemporaryDirectory(prefix="ja-run-outputs-") as temp:
            root = Path(temp)
            video = root / "日本語 lesson.mp4"
            subprocess.run([
                str(ffmpeg), "-v", "error", "-f", "lavfi", "-i",
                "color=c=blue:s=640x360:r=24:d=1", "-f", "lavfi", "-i",
                "sine=frequency=440:duration=1", "-c:v", "h264_videotoolbox",
                "-pix_fmt", "yuv420p", "-c:a", "aac", str(video),
            ], check=True, capture_output=True, timeout=30)
            original = video.read_bytes()
            settings = root / "config.toml"
            settings.write_text(
                '[deepseek]\napi_key = "test-key"\n'
                '[vocabulary]\nlearner_level = "N1"\ninclude_unknown = false\n'
                'output_dir = "unused-config-directory"\nformat = "json"\n',
                encoding="utf-8")
            for fmt in ("md", "json", "both"):
                with self.subTest(fmt=fmt):
                    output, words = root / fmt / "media", root / fmt / "生词 notes"
                    output.mkdir(parents=True)
                    for suffix, text in (("ja", "確認しました。"), ("zh", "已经确认了。")):
                        (output / f"{video.stem}.{suffix}.srt").write_text(
                            f"1\n00:00:00,000 --> 00:00:00,900\n{text}\n\n",
                            encoding="utf-8")
                    argv = ["ja-video-subtitles", "run", str(video), "-o", str(output),
                            "--vocab-output-dir", str(words), "--vocab-format", fmt, "-y"]
                    with mock.patch("sys.argv", argv), \
                            mock.patch.object(cli.preflight, "load", return_value=config.load(settings)), \
                            mock.patch.object(cli.preflight.model_mod, "model_ready", return_value=True), \
                            mock.patch("openai.OpenAI") as api, \
                            redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), \
                            self.assertRaises(SystemExit) as result:
                        cli.main()
                    self.assertEqual(result.exception.code, 0)
                    # Exactly one connectivity probe; no transcription/translation/gloss calls.
                    api.return_value.chat.completions.create.assert_called_once()
                    selected = ("md", "json") if fmt == "both" else (fmt,)
                    self.assertEqual({p.name for p in words.iterdir()},
                                     {f"{video.stem}.vocab.{ext}" for ext in selected})
                    self.assertFalse(list(output.glob("*.vocab.*")))
                    self.assertTrue((output / f"{video.stem}.sub.mp4").is_file())
                    audio = output / f"{video.stem}.mp3"
                    probe = subprocess.run([
                        str(ffprobe), "-v", "error", "-show_entries",
                        "stream=codec_type,codec_name:format=duration", "-of", "json", str(audio),
                    ], check=True, capture_output=True, text=True, timeout=10)
                    info = json.loads(probe.stdout)
                    self.assertEqual(info["streams"], [{"codec_name": "mp3", "codec_type": "audio"}])
                    self.assertAlmostEqual(float(info["format"]["duration"]), 1, delta=0.15)
                    report = next(output.glob("report-*.md")).read_text(encoding="utf-8")
                    self.assertIn("| MP3 export | done |", report)
                    for ext in selected:
                        self.assertIn(str(words / f"{video.stem}.vocab.{ext}"), report)
            self.assertEqual(video.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
