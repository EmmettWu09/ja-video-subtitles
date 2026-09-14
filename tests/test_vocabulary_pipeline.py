"""Vocabulary failures must never prevent the final subtitle video."""

import argparse
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ja_video_subtitles import cli
from ja_video_subtitles.config import Config, DEFAULT_USER_TEMPLATE
from ja_video_subtitles.report import VideoRecord

SRT = "1\n00:00:00,000 --> 00:00:01,000\n確認しました。\n\n"


class TestVocabularyPipeline(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.inputs = self.root / "inputs"
        self.out = self.root / "output"
        self.inputs.mkdir()
        self.out.mkdir()
        self.video = self.make_video("first")
        self.cfg = Config(
            base_url="https://example.invalid", api_key="sk-" + "x" * 32,
            model="test", asr_model_id="test", prompt_system="",
            prompt_user_template=DEFAULT_USER_TEMPLATE, force_style="",
            video_bitrate="8M")
        self.ffmpeg = Path("/fake/ffmpeg")
        self.stdout = self.enterContext(redirect_stdout(io.StringIO()))
        self.stderr = self.enterContext(redirect_stderr(io.StringIO()))
        self.generate = self.enterContext(mock.patch(
            "ja_video_subtitles.vocabulary.generate", side_effect=self.glossary))
        self.burn = self.enterContext(mock.patch.object(
            cli.burn_mod, "burn", side_effect=self.encode))
        self.audio = self.enterContext(mock.patch.object(
            cli.audio_mod, "export", side_effect=self.export_audio))
        self.transcribe = self.enterContext(mock.patch.object(
            cli.transcribe_mod, "transcribe",
            side_effect=AssertionError("cached JA should be reused")))
        self.translate = self.enterContext(mock.patch.object(
            cli.translate_mod, "translate",
            side_effect=AssertionError("cached ZH should be reused")))

    def make_video(self, stem):
        video = self.inputs / f"{stem}.mp4"
        video.write_bytes(b"source")
        (self.out / f"{stem}.ja.srt").write_text(SRT, encoding="utf-8")
        (self.out / f"{stem}.zh.srt").write_text(
            SRT.replace("確認しました。", "已经确认了。"), encoding="utf-8")
        return video

    def glossary(self, ja, zh, output, cfg, force=False):
        stem = ja.name.removesuffix(".ja.srt")
        if cfg.vocabulary_format in ("json", "both"):
            (output / f"{stem}.vocab.json").write_text('{"entries": []}', encoding="utf-8")
        if cfg.vocabulary_format in ("md", "both"):
            (output / f"{stem}.vocab.md").write_text("未发现符合条件的词汇", encoding="utf-8")
        return SimpleNamespace(status="done", total_count=0, counts={}, degraded_count=0)

    def export_audio(self, video, output, ffmpeg):
        target = output / f"{video.stem}.mp3"
        target.write_bytes(b"mp3 audio")
        return target

    def encode(self, video, subtitle, output, *_):
        self.assertIn("已经确认了。", subtitle.read_text(encoding="utf-8"))
        target = output / f"{video.stem}.sub.mp4"
        target.write_bytes(b"encoded")
        return target

    def process(self, force=False):
        record = VideoRecord(self.video.name, self.video.stem)
        cli.process_video(self.video, self.out, self.cfg, self.ffmpeg, force, record)
        return record

    def test_empty_glossary_still_merges_and_burns(self):
        record = self.process()
        self.assertEqual(record.status, "done")
        self.assertEqual([s.name for s in record.stages],
                         ["transcribe", "translate", "vocabulary", "merge", "burn", "audio"])
        self.assertIn("no target words", record.stages[2].note)
        self.assertTrue((self.out / "first.vocab.md").exists())
        self.burn.assert_called_once()
        self.audio.assert_called_once_with(self.video, self.out, self.ffmpeg)
        self.assertTrue((self.out / "first.mp3").exists())

    def test_disabled_vocabulary_is_not_run(self):
        self.cfg.vocabulary_enabled = False
        record = self.process()
        self.generate.assert_not_called()
        self.assertNotIn("vocabulary", [s.name for s in record.stages])
        self.burn.assert_called_once()

    def test_stage_failure_keeps_burning_and_redacts_api_key(self):
        self.generate.side_effect = RuntimeError("failure " + self.cfg.api_key)
        record = self.process()
        self.assertEqual(record.status, "partial")
        self.assertEqual(record.stages[2].status, "failed")
        self.assertIn("[REDACTED]", record.error)
        self.assertNotIn(self.cfg.api_key, record.error + self.stderr.getvalue())
        self.assertTrue((self.out / "first.sub.mp4").exists())

    def test_force_reaches_glossary(self):
        self.transcribe.side_effect = None
        self.transcribe.return_value = self.out / "first.ja.srt", 0
        self.translate.side_effect = None
        self.process(force=True)
        self.assertTrue(self.generate.call_args.kwargs["force"])
        self.transcribe.assert_called_once()
        self.translate.assert_called_once()

    def test_edited_translation_refreshes_bilingual_before_burn(self):
        first = self.process()
        self.assertEqual(first.stages[3].status, "done")
        self.assertEqual(self.process().stages[3].status, "skipped")
        translation = self.out / "first.zh.srt"
        translation.write_text(translation.read_text(encoding="utf-8").replace(
            "已经确认了。", "已经确认了。[修订]"), encoding="utf-8")
        record = self.process()
        self.assertEqual(record.stages[3].status, "done")
        self.assertIn("[修订]", (self.out / "first.bilingual.srt").read_text(encoding="utf-8"))
        self.assertIn("N2=0, N1=0, 未分级=0", record.stages[2].note)

    def test_partial_batch_continues_with_nonzero_status_and_report(self):
        second = self.make_video("second")

        def generate(ja, *args, **kwargs):
            if ja.name.startswith("first"):
                raise RuntimeError("morphology unavailable")
            return self.glossary(ja, *args, **kwargs)

        self.generate.side_effect = generate
        with mock.patch.object(cli.preflight, "run", return_value=(self.cfg, self.ffmpeg)):
            code = cli.cmd_run(argparse.Namespace(input=str(self.inputs),
                output_dir=str(self.out), yes=True, force=False))
        self.assertEqual(code, 1)
        self.assertEqual(self.burn.call_count, 2)
        self.assertTrue((self.out / f"{second.stem}.sub.mp4").exists())
        report = next(self.out.glob("report-*.md")).read_text(encoding="utf-8")
        self.assertIn("1 succeeded / 0 failed / 0 skipped / 1 partial", report)
        self.assertIn("| Vocabulary | failed |", report)
        self.assertIn("morphology unavailable", report)
        self.assertIn("first.sub.mp4", report)
        self.assertIn("second.vocab.json", report)
        self.assertIn("second.vocab.md", report)
        self.assertNotIn(self.cfg.api_key, report)

    def run_command(self, **options):
        values = dict(input=str(self.inputs), output_dir=str(self.out), yes=True, force=False)
        values.update(options)
        with mock.patch.object(cli.preflight, "run", return_value=(self.cfg, self.ffmpeg)):
            return cli.cmd_run(argparse.Namespace(**values))

    def test_external_vocab_formats_and_report_paths(self):
        for fmt in ("md", "json", "both"):
            with self.subTest(fmt=fmt):
                words = self.root / f"words-{fmt}"
                words.mkdir()
                self.cfg.vocabulary_output_dir = str(words)
                self.cfg.vocabulary_format = fmt
                # Old artifacts in -o must not masquerade as the selected outputs.
                for suffix in ("md", "json"):
                    (self.out / f"first.vocab.{suffix}").write_text("stale", encoding="utf-8")
                self.assertEqual(self.run_command(), 0)
                latest = max(self.out.glob("report-*.md"), key=lambda p: p.stat().st_mtime_ns)
                report = latest.read_text(encoding="utf-8")
                self.assertEqual(self.generate.call_args.args[2], words)
                for suffix in ("md", "json"):
                    selected = fmt in (suffix, "both")
                    self.assertEqual((words / f"first.vocab.{suffix}").exists(), selected)
                    self.assertEqual(f"{words}/first.vocab.{suffix}" in report, selected)
                    self.assertNotIn(f"- `first.vocab.{suffix}`", report)
                self.assertIn(f"format={fmt}", report)
                self.assertIn("first.mp3", report)
                self.assertIn("| MP3 export | done |", report)
                self.assertTrue((self.out / "first.sub.mp4").is_file())

    def test_audio_failure_keeps_video_and_continues_batch(self):
        self.make_video("second")
        old_audio = self.out / "first.mp3"
        old_audio.write_bytes(b"old audio")

        def export(video, *args):
            if video.stem == "first":
                raise RuntimeError("no audio stream")
            return self.export_audio(video, *args)

        self.audio.side_effect = export
        self.assertEqual(self.run_command(), 1)
        self.assertEqual(self.burn.call_count, 2)
        self.assertEqual(old_audio.read_bytes(), b"old audio")
        self.assertTrue((self.out / "first.sub.mp4").is_file())
        report = next(self.out.glob("report-*.md")).read_text(encoding="utf-8")
        self.assertIn("1 succeeded / 0 failed / 0 skipped / 1 partial", report)
        self.assertIn("| MP3 export | failed |", report)
        self.assertNotIn("- `first.mp3`", report)
        self.assertIn("second.mp3", report)

    def test_vocab_and_audio_failures_are_both_retained(self):
        self.generate.side_effect = RuntimeError("vocabulary unavailable")
        self.audio.side_effect = RuntimeError("audio unavailable")
        record = self.process()
        self.assertEqual(record.status, "partial")
        self.assertIn("vocabulary: vocabulary unavailable", record.error)
        self.assertIn("audio: audio unavailable", record.error)
        self.assertTrue((self.out / "first.sub.mp4").is_file())

    def test_existing_mp3_requires_confirmation_even_without_sub_mp4(self):
        target = self.out / "first.mp3"
        target.write_bytes(b"keep me")
        with mock.patch("builtins.input", side_effect=EOFError) as prompt:
            self.assertEqual(self.run_command(yes=False), 0)
        prompt.assert_called_once()
        self.burn.assert_not_called()
        self.audio.assert_not_called()
        self.assertEqual(target.read_bytes(), b"keep me")
        self.transcribe.side_effect = None
        self.transcribe.return_value = self.out / "first.ja.srt", 0
        self.translate.side_effect = None
        with mock.patch("builtins.input", side_effect=AssertionError("unexpected prompt")):
            self.assertEqual(self.run_command(yes=False, force=True), 0)

    def test_selected_outputs_cannot_alias_source_video(self):
        words = self.root / "words"
        words.mkdir()
        self.cfg.vocabulary_output_dir = str(words)
        for target in (self.out / "first.mp3", words / "first.vocab.md"):
            with self.subTest(target=target):
                target.symlink_to(self.video)
                try:
                    self.assertEqual(self.run_command(), 2)
                    self.assertEqual(self.video.read_bytes(), b"source")
                    self.burn.assert_not_called()
                finally:
                    target.unlink()

    def test_batch_output_stem_collision_rejected(self):
        (self.inputs / "first.mov").write_bytes(b"another source")
        self.assertEqual(self.run_command(), 2)
        self.burn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
