"""MP3 export safety, plus opt-in checks with tiny synthetic local media."""

import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ja_video_subtitles import audio
from ja_video_subtitles.ffmpeg_util import find_ffprobe


class TestMp3Encoder(unittest.TestCase):
    def test_supported_encoder_is_recognized(self):
        with mock.patch.object(audio.subprocess, "run", return_value=SimpleNamespace(
            returncode=0, stdout="Encoder libmp3lame [MP3]:\n", stderr="",
        )) as run:
            self.assertTrue(audio.has_mp3_encoder(Path("/path/ffmpeg")))
        self.assertEqual(run.call_args.args[0][-1], "encoder=libmp3lame")
        self.assertEqual(run.call_args.kwargs["timeout"], 15)

    def test_unknown_encoder_with_zero_exit_is_rejected(self):
        with mock.patch.object(audio.subprocess, "run", return_value=SimpleNamespace(
            returncode=0, stdout="", stderr="Codec 'libmp3lame' is not recognized.",
        )):
            self.assertFalse(audio.has_mp3_encoder(Path("ffmpeg")))

    def test_unavailable_or_timed_out_binary_is_rejected(self):
        for error in (FileNotFoundError("missing"),
                      subprocess.TimeoutExpired("ffmpeg", 15)):
            with self.subTest(error=error), mock.patch.object(
                audio.subprocess, "run", side_effect=error,
            ):
                self.assertFalse(audio.has_mp3_encoder(Path("ffmpeg")))


class TestMp3Export(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.video = self.root / "日本語's [1],:;\\ video.mp4"
        self.video.write_bytes(b"original video")
        self.out = self.root / "audio's [2] dir"
        self.out.mkdir()
        self.output = self.out / f"{self.video.stem}.mp3"
        self.output.write_bytes(b"previous MP3")
        self.enterContext(mock.patch.object(audio, "find_ffprobe", return_value=None))
        self.enterContext(mock.patch.object(audio, "tqdm", side_effect=self.progress))
        self.enterContext(mock.patch("builtins.print"))
        self.process = mock.Mock(returncode=0, stdout=io.StringIO("out_time_us=1000000\n"))
        self.command = None

    @staticmethod
    def progress(**kwargs):
        bar = mock.MagicMock(n=0, total=kwargs["total"])
        bar.__enter__.return_value = bar
        return bar

    def launch(self, cmd, **kwargs):
        self.command = cmd
        Path(cmd[-1]).write_bytes(b"new MP3")
        kwargs["stderr"].write("ffmpeg diagnostic\n")
        return self.process

    def test_success_atomically_replaces_output_with_first_audio(self):
        def launch(cmd, **kwargs):
            self.assertEqual(self.output.read_bytes(), b"previous MP3")
            return self.launch(cmd, **kwargs)

        with mock.patch.object(audio.subprocess, "Popen", side_effect=launch):
            result = audio.export(self.video, self.out, Path("/test/ffmpeg"))
        self.assertEqual(result, self.output)
        self.assertEqual(result.read_bytes(), b"new MP3")
        self.assertEqual(set(self.out.iterdir()), {self.output})
        self.assertEqual(self.video.read_bytes(), b"original video")
        self.assertEqual(self.command[self.command.index("-i") + 1],
                         str(self.video.resolve()))
        self.assertEqual(self.command[self.command.index("-map") + 1], "0:a:0")
        self.assertEqual(self.command[self.command.index("-c:a") + 1], "libmp3lame")
        self.assertEqual(self.command[self.command.index("-b:a") + 1], "192k")
        self.assertEqual(Path(self.command[-1]).parent, self.out.resolve())
        self.assertNotEqual(Path(self.command[-1]), self.output.resolve())
        self.assertIn("-vn", self.command)
        self.process.kill.assert_not_called()

    def test_ffmpeg_failure_preserves_existing_output(self):
        self.process.returncode = 1
        with mock.patch.object(audio.subprocess, "Popen", side_effect=self.launch):
            with self.assertRaisesRegex(RuntimeError, "ffmpeg MP3 export failed.*exit code 1"):
                audio.export(self.video, self.out, Path("ffmpeg"))
        self.assertEqual(self.output.read_bytes(), b"previous MP3")
        self.assertEqual(set(self.out.iterdir()), {self.output})

    def test_start_failure_preserves_existing_output(self):
        with mock.patch.object(audio.subprocess, "Popen", side_effect=OSError("missing")):
            with self.assertRaisesRegex(RuntimeError, "could not start ffmpeg MP3 export"):
                audio.export(self.video, self.out, Path("ffmpeg"))
        self.assertEqual(self.output.read_bytes(), b"previous MP3")
        self.assertEqual(set(self.out.iterdir()), {self.output})

    def test_interruption_kills_process_and_preserves_existing_output(self):
        self.process.wait.side_effect = [KeyboardInterrupt, None]
        with mock.patch.object(audio.subprocess, "Popen", side_effect=self.launch):
            with self.assertRaises(KeyboardInterrupt):
                audio.export(self.video, self.out, Path("ffmpeg"))
        self.process.kill.assert_called_once_with()
        self.assertEqual(self.output.read_bytes(), b"previous MP3")
        self.assertEqual(set(self.out.iterdir()), {self.output})


@unittest.skipUnless(os.environ.get("RUN_FFMPEG_TESTS") == "1",
                     "set RUN_FFMPEG_TESTS=1 for local MP3 encoding checks")
class TestRealMp3Export(unittest.TestCase):
    def test_audio_only_mp3_and_silent_input_preserves_existing_output(self):
        binary = shutil.which("ffmpeg")
        self.assertIsNotNone(binary, "ffmpeg required")
        ffmpeg = Path(binary)
        self.assertTrue(audio.has_mp3_encoder(ffmpeg), "libmp3lame required")
        ffprobe = find_ffprobe(ffmpeg)
        self.assertIsNotNone(ffprobe, "ffprobe required")
        with tempfile.TemporaryDirectory(prefix="ja-mp3-integration-") as temp:
            root = Path(temp)
            video = root / "日本語's [1],:;\\ video.mp4"
            silent = root / "silent.mp4"
            out = root / "-audio's [2],:;\\ dir"
            subprocess.run([
                str(ffmpeg), "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                "-i", "color=c=blue:s=160x90:r=10:d=1", "-f", "lavfi",
                "-i", "sine=frequency=440:duration=1", "-c:v", "mpeg4",
                "-c:a", "aac", str(video),
            ], check=True, capture_output=True, timeout=30)
            subprocess.run([
                str(ffmpeg), "-hide_banner", "-loglevel", "error", "-i", str(video),
                "-an", "-c:v", "copy", str(silent),
            ], check=True, capture_output=True, timeout=30)
            before = video.read_bytes()
            output = audio.export(video, out, ffmpeg)
            probe = subprocess.run([
                str(ffprobe), "-v", "error", "-show_entries",
                "stream=codec_name,codec_type:format=duration", "-of", "json",
                str(output),
            ], check=True, capture_output=True, text=True, timeout=10)
            info = json.loads(probe.stdout)
            self.assertEqual([(s["codec_type"], s["codec_name"])
                              for s in info["streams"]], [("audio", "mp3")])
            self.assertGreaterEqual(float(info["format"]["duration"]), 0.9)
            self.assertLess(float(info["format"]["duration"]), 1.2)
            self.assertEqual(video.read_bytes(), before)
            previous = out / "silent.mp3"
            previous.write_bytes(b"previous MP3")
            with self.assertRaisesRegex(RuntimeError, "input has no audio stream"):
                audio.export(silent, out, ffmpeg)
            self.assertEqual(previous.read_bytes(), b"previous MP3")
            self.assertEqual(set(out.iterdir()), {output, previous})


if __name__ == "__main__":
    unittest.main()
