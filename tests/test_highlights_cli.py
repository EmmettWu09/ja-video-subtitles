"""Offline CLI tests for the --highlights/--no-highlights switch and stage wiring."""

import argparse
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ja_video_subtitles import cli, config
from ja_video_subtitles.config import Config, DEFAULT_USER_TEMPLATE
from ja_video_subtitles.report import VideoRecord


def invoke(*arguments):
    stdout, stderr = io.StringIO(), io.StringIO()
    argv = ["ja-video-subtitles", *map(str, arguments)]
    with mock.patch("sys.argv", argv), redirect_stdout(stdout), \
            redirect_stderr(stderr), unittest.TestCase().assertRaises(SystemExit) as result:
        cli.main()
    return result.exception.code, stdout.getvalue(), stderr.getvalue()


def make_cfg(**overrides):
    values = dict(base_url="https://example.invalid", api_key="sk-" + "x" * 32,
                  model="test", asr_model_id="test", prompt_system="",
                  prompt_user_template=DEFAULT_USER_TEMPLATE, force_style="",
                  video_bitrate="8M", highlights_enabled=True)
    values.update(overrides)
    return Config(**values)


class TestHighlightsSwitch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config_path = self.root / "config.toml"
        self.ffmpeg = Path("/mock/ffmpeg")

        def preflight(videos, out_dir, cfg):
            out_dir.mkdir(parents=True, exist_ok=True)
            return cfg, self.ffmpeg

        self.preflight = self.patch("ja_video_subtitles.cli.preflight.run",
                                    side_effect=preflight)
        self.process = self.patch("ja_video_subtitles.cli.process_video")
        self.load = self.patch(
            "ja_video_subtitles.cli.load",
            side_effect=lambda: config.load(self.config_path))

    def patch(self, target, **kwargs):
        patcher = mock.patch(target, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def video(self, name="a.mp4"):
        path = self.root / name
        path.write_bytes(b"original video")
        return path

    def write_config(self, text):
        self.config_path.write_text(text, encoding="utf-8")

    def invoke_run(self, *arguments):
        return invoke("run", *arguments)

    def test_conflicting_switches_are_rejected(self):
        video = self.video()
        self.write_config("")
        for options in (("--highlights", "--no-highlights"),
                        ("--no-highlights", "--highlights")):
            with self.subTest(options=options):
                code, _, _ = self.invoke_run(video, "-o", self.root / "out", *options)
                self.assertEqual(code, 2)
        self.load.assert_not_called()
        self.process.assert_not_called()

    def test_default_is_disabled(self):
        video = self.video()
        self.write_config("")
        code, _, _ = self.invoke_run(video, "-o", self.root / "out")
        self.assertEqual(code, 0)
        cfg = self.preflight.call_args.args[2]
        self.assertIs(cfg.highlights_enabled, False)

    def test_cli_enables_default_disabled(self):
        video = self.video()
        self.write_config("")
        code, _, _ = self.invoke_run(video, "-o", self.root / "out", "--highlights")
        self.assertEqual(code, 0)
        cfg = self.preflight.call_args.args[2]
        self.assertIs(cfg.highlights_enabled, True)

    def test_config_disables_and_cli_overrides(self):
        video = self.video()
        self.write_config("[highlights]\nenabled = false\n")
        code, _, _ = self.invoke_run(video, "-o", self.root / "out")
        self.assertEqual(code, 0)
        self.assertIs(self.preflight.call_args.args[2].highlights_enabled, False)
        code, _, _ = self.invoke_run(video, "-o", self.root / "out", "--highlights")
        self.assertEqual(code, 0)
        self.assertIs(self.preflight.call_args.args[2].highlights_enabled, True)

    def test_cli_disables_configured_enabled(self):
        video = self.video()
        self.write_config("[highlights]\nenabled = true\n")
        code, _, _ = self.invoke_run(video, "-o", self.root / "out", "--no-highlights")
        self.assertEqual(code, 0)
        self.assertIs(self.preflight.call_args.args[2].highlights_enabled, False)

    def test_burn_rejects_highlights_arguments(self):
        video = self.video()
        for option in ("--highlights", "--no-highlights"):
            with self.subTest(option=option):
                code, _, _ = invoke("burn", video, "-o", self.root / "out",
                                    option)
                self.assertEqual(code, 2)

    def test_run_help_mentions_highlights(self):
        code, stdout, _ = invoke("run", "--help")
        self.assertEqual(code, 0)
        self.assertIn("--highlights", stdout)
        self.assertIn("--no-highlights", stdout)

    def test_existing_essence_requires_confirmation(self):
        video = self.video()
        out = self.root / "out"
        (out / "a").mkdir(parents=True)
        (out / "a" / "a.highlights.mp4").write_bytes(b"old essence")
        self.write_config("[highlights]\nenabled = true\n")
        with mock.patch("builtins.input", side_effect=EOFError):
            code, stdout, _ = self.invoke_run(video, "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("1 skipped", stdout)
        self.process.assert_not_called()
        self.assertEqual((out / "a" / "a.highlights.mp4").read_bytes(),
                         b"old essence")

    def test_existing_essence_ignored_when_highlights_disabled(self):
        video = self.video()
        out = self.root / "out"
        (out / "a").mkdir(parents=True)
        (out / "a" / "a.highlights.mp4").write_bytes(b"old essence")
        self.write_config("")
        with mock.patch("builtins.input",
                        side_effect=AssertionError("unexpected prompt")):
            code, _, _ = self.invoke_run(video, "-o", out, "--no-highlights", "-y")
        self.assertEqual(code, 0)
        self.process.assert_called_once()

    def test_highlights_target_cannot_alias_source_video(self):
        video = self.video()
        out = self.root / "out"
        (out / "a").mkdir(parents=True)
        (out / "a" / "a.highlights.mp4").symlink_to(video)
        self.write_config("[highlights]\nenabled = true\n")
        code, _, stderr = self.invoke_run(video, "-o", out, "-y")
        self.assertEqual(code, 2)
        self.assertIn("would overwrite", stderr)
        self.assertEqual(video.read_bytes(), b"original video")
        self.process.assert_not_called()


class TestHighlightsStage(unittest.TestCase):
    """process_video wiring: the highlights stage is non-blocking."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.video = self.out / "lesson.mp4"
        self.video.write_bytes(b"video")
        for suffix, text in (("ja", "こんにちは。"), ("zh", "你好。")):
            (self.out / f"lesson.{suffix}.srt").write_text(
                f"1\n00:00:00,000 --> 00:00:01,000\n{text}\n\n",
                encoding="utf-8")
        self.ffmpeg = Path("/mock/ffmpeg")
        for target in ("ja_video_subtitles.cli.burn_mod.burn",
                       "ja_video_subtitles.cli.audio_mod.export"):
            patcher = mock.patch(target)
            self.addCleanup(patcher.stop)
            patcher.start()
        self.generate = mock.patch(
            "ja_video_subtitles.highlights.generate").start()
        self.addCleanup(mock.patch.stopall)

    def process(self, cfg):
        record = VideoRecord(self.video.name, self.video.stem)
        cli.process_video(self.video, self.out, cfg, self.ffmpeg, False, record)
        return record

    def test_stage_runs_after_audio_and_records_note(self):
        self.generate.return_value = SimpleNamespace(
            clip_count=3, essence_seconds=233.6, essence_incomplete=False,
            output_dir=self.out / "highlights", note="")
        record = self.process(make_cfg())
        self.assertEqual(record.status, "done")
        self.assertEqual(record.stages[-1].name, "highlights")
        self.assertEqual(record.stages[-1].status, "done")
        self.assertIn("3 clips", record.stages[-1].note)
        self.assertIn("234s", record.stages[-1].note)
        self.assertEqual(self.generate.call_args.args[:4],
                         (self.video, self.out / "lesson.ja.srt",
                          self.out / "lesson.zh.srt", self.out))

    def test_stage_failure_marks_partial_and_keeps_products(self):
        self.generate.side_effect = RuntimeError("analysis down")
        record = self.process(make_cfg())
        self.assertEqual(record.status, "partial")
        self.assertEqual(record.stages[-1].name, "highlights")
        self.assertEqual(record.stages[-1].status, "failed")
        self.assertIn("highlights: analysis down", record.error)
        self.assertIn("burn", [s.name for s in record.stages])

    def test_stage_failure_redacts_api_key(self):
        cfg = make_cfg()
        self.generate.side_effect = RuntimeError("failed with " + cfg.api_key)
        record = self.process(cfg)
        self.assertIn("[REDACTED]", record.error)
        self.assertNotIn(cfg.api_key, record.error)

    def test_disabled_config_skips_the_stage(self):
        record = self.process(make_cfg(highlights_enabled=False))
        self.generate.assert_not_called()
        self.assertNotIn("highlights", [s.name for s in record.stages])
        self.assertEqual(record.status, "done")


class TestHighlightsPreflight(unittest.TestCase):
    def test_disabled_skips_voice_check(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out"
            video = Path(d) / "v.mp4"
            video.write_bytes(b"v")
            voices = mock.patch.object(
                cli.preflight, "check_highlights_voices",
                return_value=["voice boom"]).start()
            openai = mock.patch("openai.OpenAI",
                                side_effect=RuntimeError("offline")).start()
            self.addCleanup(mock.patch.stopall)
            for enabled, expected in ((False, 0), (True, 1)):
                with self.subTest(enabled=enabled):
                    try:
                        cli.preflight.run([video], out,
                                          make_cfg(highlights_enabled=enabled))
                    except cli.preflight.PreflightError:
                        pass
                    self.assertEqual(voices.call_count, expected)

    def test_say_missing(self):
        with mock.patch("shutil.which", return_value=None):
            errors = cli.preflight.check_highlights_voices(make_cfg())
        self.assertEqual(len(errors), 1)
        self.assertIn("--no-highlights", errors[0])

    def test_voice_missing(self):
        which = mock.patch("shutil.which", return_value="/usr/bin/say")
        run = mock.patch("subprocess.run", return_value=SimpleNamespace(
            stdout="Kyoko               ja_JP    # きょうこ\n"
                   "Tingting            zh_CN    # 婷婷\n"))
        with which, run:
            errors = cli.preflight.check_highlights_voices(
                make_cfg(highlights_ja_voice="Otoya"))
            self.assertEqual(len(errors), 1)
            self.assertIn("Otoya", errors[0])
            self.assertIn("--no-highlights", errors[0])
            errors = cli.preflight.check_highlights_voices(make_cfg())
            self.assertEqual(errors, [])


class TestHighlightsReport(unittest.TestCase):
    def make_reporter(self, d, *, enabled=True):
        from ja_video_subtitles.report import Reporter
        return Reporter(d, version="0.1.1", asr_model="k", base_url="b",
                        translate_model="m", bitrate="8M",
                        highlights_config={"enabled": enabled,
                                           "target_seconds": 240,
                                           "intro_start_seconds": 0,
                                           "ja_voice": "Kyoko",
                                           "zh_voice": "Tingting"})

    def test_report_shows_highlights_summary_and_products(self):
        from ja_video_subtitles.report import StageRecord, VideoRecord
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            video_dir = d / "v"
            (video_dir / "highlights").mkdir(parents=True)
            (video_dir / "v.mp4").write_bytes(b"x" * 2048)
            (video_dir / "v.highlights.mp4").write_bytes(b"y" * 1024)
            rep = self.make_reporter(d)
            record = VideoRecord("v.mp4", "v")
            record.stages = [StageRecord("highlights", "done", 12.0,
                                         "3 clips; essence 234s")]
            rep.records.append(record)
            text = rep.write().read_text(encoding="utf-8")
            self.assertIn("Highlights: enabled, target=240s", text)
            self.assertIn("| Highlights | done |", text)
            self.assertIn("v/v.mp4", text)
            self.assertIn("v/v.highlights.mp4", text)
            self.assertIn("v/highlights/", text)

    def test_report_excludes_essence_after_stage_failure(self):
        from ja_video_subtitles.report import StageRecord, VideoRecord
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            video_dir = d / "v"
            (video_dir / "highlights").mkdir(parents=True)
            (video_dir / "v.mp4").write_bytes(b"x" * 2048)
            (video_dir / "v.highlights.mp4").write_bytes(b"y" * 1024)
            rep = self.make_reporter(d)
            record = VideoRecord("v.mp4", "v", status="partial",
                                 error="highlights: boom")
            record.stages = [StageRecord("highlights", "failed", 1.0, "boom")]
            rep.records.append(record)
            text = rep.write().read_text(encoding="utf-8")
            self.assertIn("| Highlights | failed |", text)
            self.assertNotIn("v.highlights.mp4", text)
            self.assertNotIn("v/highlights/", text)

    def test_report_marks_disabled(self):
        from ja_video_subtitles.report import VideoRecord
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            video_dir = d / "v"
            video_dir.mkdir()
            (video_dir / "v.mp4").write_bytes(b"x" * 2048)
            rep = self.make_reporter(d, enabled=False)
            rep.records.append(VideoRecord("v.mp4", "v"))
            text = rep.write().read_text(encoding="utf-8")
            self.assertIn("Highlights: disabled", text)
            self.assertNotIn("| Highlights |", text)


if __name__ == "__main__":
    unittest.main()
