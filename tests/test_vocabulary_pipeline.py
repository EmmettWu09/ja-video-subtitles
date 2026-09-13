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
        (output / f"{stem}.vocab.json").write_text('{"entries": []}', encoding="utf-8")
        (output / f"{stem}.vocab.md").write_text("未发现符合条件的词汇", encoding="utf-8")
        return SimpleNamespace(status="done", total_count=0, counts={}, degraded_count=0)

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
                         ["transcribe", "translate", "vocabulary", "merge", "burn"])
        self.assertIn("no target words", record.stages[2].note)
        self.assertTrue((self.out / "first.vocab.md").exists())
        self.burn.assert_called_once()

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


if __name__ == "__main__":
    unittest.main()
