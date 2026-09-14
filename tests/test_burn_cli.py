"""Offline burn-command regressions; no encoder, ASR model, or API calls."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ja_video_subtitles import cli


SRT = "1\n00:00:00,000 --> 00:00:01,000\n日本語\n中文字幕\n\n"


class TestBurnCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.out = self.root / "out"
        self.out.mkdir()
        self.cfg = SimpleNamespace(force_style="FontSize=24", video_bitrate="6M")
        self.ffmpeg = Path("/mock/ffmpeg")

        def preflight(videos, output):
            output.mkdir(parents=True, exist_ok=True)
            return self.cfg, self.ffmpeg

        self.preflight = self.patch("ja_video_subtitles.cli.preflight.run_burn",
                                    side_effect=preflight)
        self.encoder = self.patch("ja_video_subtitles.cli.burn_mod.burn",
                                  side_effect=self.encode)
        self.full_preflight = self.patch("ja_video_subtitles.cli.preflight.run",
                                         side_effect=AssertionError("full pipeline used"))
        for stage in ("transcribe_mod.transcribe", "translate_mod.translate",
                      "merge_mod.merge"):
            self.patch(f"ja_video_subtitles.cli.{stage}",
                       side_effect=AssertionError("upstream stage used"))

    def patch(self, target, **kwargs):
        patcher = mock.patch(target, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def video(self, name="a.mp4", directory=None):
        path = (directory or self.root) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"original video")
        return path

    def subtitle(self, video, directory=None, text=SRT):
        path = (directory or self.out) / f"{video.stem}.bilingual.srt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    @staticmethod
    def encode(video, subtitle, output, ffmpeg, style, bitrate):
        target = output / f"{video.stem}.sub.mp4"
        target.write_bytes(b"encoded video")
        return target

    def invoke(self, *arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        argv = ["ja-video-subtitles", *map(str, arguments)]
        with mock.patch("sys.argv", argv), redirect_stdout(stdout), \
                redirect_stderr(stderr), self.assertRaises(SystemExit) as result:
            cli.main()
        return result.exception.code, stdout.getvalue(), stderr.getvalue()

    def burn(self, *inputs, options=()):
        return self.invoke("burn", *inputs, "-o", self.out, *options)

    def test_single_video_default_subtitle_and_burn_only_report(self):
        video = self.video()
        subtitle = self.subtitle(video)
        before = {p: p.read_bytes() for p in (video, subtitle)}
        code, stdout, stderr = self.burn(video)
        self.assertEqual((code, stderr), (0, ""))
        self.encoder.assert_called_once_with(
            video.absolute(), subtitle.absolute(), self.out.absolute(),
            self.ffmpeg, self.cfg.force_style, self.cfg.video_bitrate)
        self.full_preflight.assert_not_called()
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        self.assertIn("1 succeeded, 0 failed, 0 skipped", stdout)
        log = (self.out / "run.log").read_text(encoding="utf-8")
        report = next(self.out.glob("report-*.md")).read_text(encoding="utf-8")
        for text in (log, report):
            self.assertIn(str(subtitle), text)
        self.assertIn("existing SRT hard subtitles", report)
        self.assertIn("N/A (burn only)", report)
        self.assertIn("a.sub.mp4", report)
        self.assertIn("| Burn | done |", report)
        self.assertIn(f"Subtitles: `{subtitle}`", report)
        self.assertLess(report.index("Subtitles:"), report.index("| Stage |"))
        self.assertNotIn("| Transcribe |", report)
        self.assertNotIn("| Translate |", report)

    def test_explicit_subtitle_accepts_utf8_bom_and_new_output_dir(self):
        video = self.video("a.MOV")
        subtitle = self.root / "my captions.srt"
        subtitle.write_text(SRT, encoding="utf-8-sig")
        self.out = self.root / "new" / "outputs"
        self.assertEqual(self.burn(video, options=("-s", subtitle))[0], 0)
        self.assertEqual(self.encoder.call_args.args[1], subtitle.absolute())

    def test_multiple_files_directories_and_duplicates_keep_input_order(self):
        directory = self.root / "videos"
        first = self.video("z.mp4")
        a = self.video("a.mp4", directory)
        b = self.video("b.MOV", directory)
        self.video("ignored.txt", directory)
        self.video("nested.mp4", directory / "nested")
        alias = self.root / "alias.mp4"
        alias.symlink_to(first)
        subs = self.root / "subtitles"
        for video in (first, a, b):
            self.subtitle(video, subs)
        self.assertEqual(self.burn(first, directory, a, alias,
                                   options=("--subtitle-dir", subs))[0], 0)
        self.assertEqual([c.args[0] for c in self.encoder.call_args_list],
                         [first.absolute(), a.absolute(), b.absolute()])
        self.assertEqual([c.args[1].parent for c in self.encoder.call_args_list],
                         [subs.absolute()] * 3)

    def test_colliding_stems_are_rejected_before_preflight(self):
        for first_name, second_name in (("a.mp4", "a.mov"),
                                        ("A.mp4", "a.mov"),
                                        ("é.mp4", "e\u0301.mov")):
            with self.subTest(first=first_name, second=second_name):
                first = self.video(first_name, self.root / "first")
                second = self.video(second_name, self.root / "second")
                code, _, stderr = self.burn(first, second)
                self.assertEqual(code, 2)
                self.assertIn("same output stem", stderr)
        self.preflight.assert_not_called()
        self.encoder.assert_not_called()

    def test_bad_input_rejects_entire_batch(self):
        valid = self.video()
        self.subtitle(valid)
        empty = self.root / "empty"
        empty.mkdir()
        for invalid in (self.root / "missing.mp4", self.video("bad.avi"), empty):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.burn(valid, invalid)[0], 2)
        self.preflight.assert_not_called()
        self.encoder.assert_not_called()

    def test_missing_subtitles_are_reported_for_every_video_before_encoding(self):
        videos = [self.video("a.mp4"), self.video("b.mp4"), self.video("c.mp4")]
        self.subtitle(videos[0])
        code, _, stderr = self.burn(*videos)
        self.assertEqual(code, 2)
        self.assertIn("b.bilingual.srt", stderr)
        self.assertIn("c.bilingual.srt", stderr)
        self.preflight.assert_not_called()
        self.encoder.assert_not_called()

    def test_every_subtitle_cue_is_validated_before_encoding(self):
        first, second = self.video("a.mp4"), self.video("b.mp4")
        self.subtitle(first)
        invalid = ["", "not an SRT", "garbage\n" + SRT,
                   SRT + "2\n00:00:02,000 --> 00:00:01,000\nbackwards\n\n",
                   SRT + "2\n00:00:02,000 --> 00:00:03,000\n\n"]
        for text in invalid:
            with self.subTest(text=text):
                self.subtitle(second, text=text)
                code, _, stderr = self.burn(first, second)
                self.assertEqual(code, 2)
                self.assertIn("b.bilingual.srt", stderr)
        self.preflight.assert_not_called()
        self.encoder.assert_not_called()

    def test_explicit_subtitle_validation_and_source_options(self):
        first, second = self.video("a.mp4"), self.video("b.mp4")
        subtitle = self.subtitle(first)
        non_srt = self.root / "captions.txt"
        non_srt.write_text(SRT, encoding="utf-8")
        invalid_utf8 = self.root / "invalid.srt"
        invalid_utf8.write_bytes(b"\xff\xfe")
        cases = [((first, second), ("-s", subtitle)),
                 ((first,), ("-s", subtitle, "--subtitle-dir", self.out)),
                 ((first,), ("--subtitle-dir", self.root / "missing")),
                 ((first,), ("-s", non_srt)),
                 ((first,), ("-s", invalid_utf8))]
        for inputs, options in cases:
            with self.subTest(options=options):
                self.assertEqual(self.burn(*inputs, options=options)[0], 2)
        self.preflight.assert_not_called()
        self.encoder.assert_not_called()

    def test_all_overwrite_answers_are_collected_before_encoding(self):
        videos = [self.video("a.mp4"), self.video("b.mp4")]
        for video in videos:
            self.subtitle(video)
            (self.out / f"{video.stem}.sub.mp4").write_bytes(b"old output")
        answers = iter(["yes", "n"])

        def answer(prompt):
            self.encoder.assert_not_called()
            return next(answers)

        with mock.patch("builtins.input", side_effect=answer) as prompts:
            code, stdout, _ = self.burn(*videos)
        self.assertEqual(code, 0)
        self.assertEqual(prompts.call_count, 2)
        self.assertEqual(self.encoder.call_args.args[0], videos[0].absolute())
        self.assertEqual((self.out / "b.sub.mp4").read_bytes(), b"old output")
        self.assertIn("1 succeeded, 0 failed, 1 skipped", stdout)
        report = next(self.out.glob("report-*.md")).read_text(encoding="utf-8")
        skipped = report.split("### b.mp4 (skipped)", 1)[1].split("\n### ", 1)[0]
        self.assertIn(f"Subtitles: `{self.out / 'b.bilingual.srt'}`", skipped)

    def test_overwrite_eof_skips_and_yes_flag_overwrites_without_prompt(self):
        video = self.video()
        self.subtitle(video)
        target = self.out / "a.sub.mp4"
        target.write_bytes(b"old output")
        with mock.patch("builtins.input", side_effect=EOFError):
            code, stdout, _ = self.burn(video)
        self.assertEqual(code, 0)
        self.assertIn("0 succeeded, 0 failed, 1 skipped", stdout)
        self.encoder.assert_not_called()
        self.assertEqual(target.read_bytes(), b"old output")
        with mock.patch("builtins.input", side_effect=AssertionError("prompted")):
            self.assertEqual(self.burn(video, options=("-y",))[0], 0)
        self.encoder.assert_called_once()
        self.assertEqual(target.read_bytes(), b"encoded video")

    def test_encoding_failure_continues_and_is_reported_with_exit_one(self):
        first, second = self.video("a.mp4"), self.video("b.mp4")
        for video in (first, second):
            self.subtitle(video)

        def encode(*args):
            if args[0].stem == "a":
                raise RuntimeError("encoder failed for a")
            return self.encode(*args)

        self.encoder.side_effect = encode
        code, stdout, stderr = self.burn(first, second)
        self.assertEqual(code, 1)
        self.assertEqual(self.encoder.call_count, 2)
        self.assertTrue((self.out / "b.sub.mp4").exists())
        self.assertIn("1 succeeded, 1 failed, 0 skipped", stdout)
        self.assertIn("encoder failed for a", stderr)
        for path in [self.out / "run.log", *self.out.glob("report-*.md")]:
            self.assertIn("encoder failed for a", path.read_text(encoding="utf-8"))
        report = next(self.out.glob("report-*.md")).read_text(encoding="utf-8")
        failed = report.split("### a.mp4 (failed)", 1)[1].split("\n### ", 1)[0]
        self.assertIn(f"Subtitles: `{self.out / 'a.bilingual.srt'}`", failed)

    def test_preflight_failure_returns_two_without_encoding(self):
        video = self.video()
        self.subtitle(video)
        self.preflight.side_effect = cli.preflight.PreflightError("missing libass")
        code, _, stderr = self.burn(video)
        self.assertEqual(code, 2)
        self.assertIn("missing libass", stderr)
        self.encoder.assert_not_called()

    def test_output_aliasing_any_source_is_rejected_even_with_yes(self):
        video = self.video()
        subtitle = self.subtitle(video)
        target = self.out / "a.sub.mp4"
        for source in (video, subtitle):
            original = source.read_bytes()
            for link in (lambda: target.symlink_to(source),
                         lambda: os.link(source, target)):
                with self.subTest(source=source, link=link):
                    link()
                    try:
                        code, _, stderr = self.burn(video, options=("-y",))
                        self.assertEqual(code, 2)
                        self.assertIn("would overwrite", stderr)
                        self.assertEqual(source.read_bytes(), original)
                    finally:
                        target.unlink()
        self.encoder.assert_not_called()
        self.preflight.assert_not_called()

    def test_output_cannot_replace_another_batch_input_in_the_output_directory(self):
        videos = [self.video(name, self.out) for name in ("a.mp4", "a.sub.mp4")]
        for video in videos:
            self.subtitle(video)
        original = {video: video.read_bytes() for video in videos}
        code, _, stderr = self.burn(*videos, options=("-y",))
        self.assertEqual(code, 2)
        self.assertIn("would overwrite", stderr)
        self.assertEqual({video: video.read_bytes() for video in videos}, original)
        self.encoder.assert_not_called()
        self.preflight.assert_not_called()

    def test_log_and_report_links_cannot_modify_video_or_subtitle_inputs(self):
        video = self.video()
        subtitle = self.subtitle(video)
        original = {path: path.read_bytes() for path in (video, subtitle)}
        now = datetime(2026, 9, 13, 12, 0, 0)
        targets = [self.out / "run.log",
                   self.out / f"report-{now:%Y%m%d-%H%M%S}.md"]
        with mock.patch("ja_video_subtitles.report.datetime") as clock:
            clock.now.return_value = now
            for target in targets:
                for source in original:
                    for hardlink in (False, True):
                        with self.subTest(target=target.name, source=source.name,
                                          hardlink=hardlink):
                            if hardlink:
                                os.link(source, target)
                            else:
                                target.symlink_to(source)
                            try:
                                code, _, stderr = self.burn(video, options=("-y",))
                                self.assertEqual(code, 2)
                                self.assertIn("would overwrite", stderr)
                                self.assertIn(str(target), stderr)
                                self.assertEqual({p: p.read_bytes() for p in original},
                                                 original)
                                self.encoder.assert_not_called()
                            finally:
                                target.unlink()

    def test_run_shared_batch_preserves_force_yes_skip_and_report_behavior(self):
        video = self.video()
        cfg = SimpleNamespace(asr_model_id="asr", model="translator",
                              base_url="https://example.invalid", video_bitrate="8M")
        self.full_preflight.side_effect = None
        self.full_preflight.return_value = cfg, self.ffmpeg
        target = self.out / "a.sub.mp4"

        def process(video, output, config, ffmpeg, force, record):
            target.write_bytes(b"processed")
            record.stages.append(cli.StageRecord("burn", "done"))

        for options, expected_force in (((), None), (("-y",), False),
                                        (("--force",), True)):
            with self.subTest(options=options):
                target.write_bytes(b"old output")
                with mock.patch.object(cli, "process_video", side_effect=process) as run, \
                        mock.patch("builtins.input", return_value="n") as prompt:
                    code, stdout, stderr = self.invoke(
                        "run", video, "-o", self.out, *options)
                self.assertEqual((code, stderr), (0, ""))
                report = max(self.out.glob("report-*.md")).read_text(encoding="utf-8")
                self.assertIn("JA/ZH bilingual hard subtitles", report)
                self.assertNotIn("Subtitles:", report)
                if expected_force is None:
                    prompt.assert_called_once()
                    run.assert_not_called()
                    self.assertEqual(target.read_bytes(), b"old output")
                    self.assertIn("0 succeeded, 0 failed, 1 skipped", stdout)
                    self.assertIn("### a.mp4 (skipped)", report)
                else:
                    prompt.assert_not_called()
                    run.assert_called_once()
                    self.assertEqual(run.call_args.args[:5],
                                     (video, self.out, cfg, self.ffmpeg, expected_force))
                    self.assertEqual(run.call_args.args[5].name, video.name)
                    self.assertEqual(target.read_bytes(), b"processed")
                    self.assertIn("1 succeeded, 0 failed, 0 skipped", stdout)
                    self.assertIn("| Burn | done |", report)
        self.full_preflight.assert_called_with([video], self.out)
        self.preflight.assert_not_called()

    def test_run_still_dispatches_to_original_pipeline(self):
        with mock.patch.object(cli, "cmd_run", return_value=0) as run, \
                mock.patch.object(cli, "cmd_burn") as burn:
            self.assertEqual(self.invoke("run", "video.mp4", "-o", self.out,
                                         "--force", "-y", "--vocab-format", "md",
                                         "--vocab-output-dir", "words")[0], 0)
        args = run.call_args.args[0]
        self.assertEqual(args.input, "video.mp4")
        self.assertTrue(args.force)
        self.assertTrue(args.yes)
        self.assertEqual(args.vocab_format, "md")
        self.assertEqual(args.vocab_output_dir, "words")
        burn.assert_not_called()

    def test_invalid_vocab_format_and_burn_vocab_options_are_rejected(self):
        for command, options in (("run", ("--vocab-format", "csv")),
                                 ("burn", ("--vocab-format", "md")),
                                 ("burn", ("--vocab-output-dir", "words"))):
            with self.subTest(command=command, options=options):
                self.assertEqual(self.invoke(command, "video.mp4", "-o", self.out,
                                             *options)[0], 2)
        self.full_preflight.assert_not_called()
        self.preflight.assert_not_called()


if __name__ == "__main__":
    unittest.main()
