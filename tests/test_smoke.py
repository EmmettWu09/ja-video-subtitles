"""离线单元测试：不依赖 ASR 模型与 DeepSeek API。

运行：.venv/bin/python -m unittest discover -s tests -v
"""

import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import srt

from ja_video_subtitles.cli import _valid_srt, collect_videos, confirm_overwrites
from ja_video_subtitles.config import Config, ConfigError, DEFAULT_USER_TEMPLATE, load
from ja_video_subtitles.ffmpeg_util import escape_filter_path
from ja_video_subtitles.merge import merge
from ja_video_subtitles.transcribe import _split_segment
from ja_video_subtitles.translate import make_batches, parse_numbered, translate

CFG = Config(base_url="", api_key="k", model="m", asr_model_id="x",
             prompt_system="", prompt_user_template=DEFAULT_USER_TEMPLATE,
             force_style="", video_bitrate="8M")

_LINE = re.compile(r"^(\d+)\.\s(.+)$")


class FakeClient:
    """模拟 LLM：原文加前缀当译文，保持编号格式。"""

    class chat:
        class completions:
            @staticmethod
            def create(model, messages, temperature=None, max_tokens=None):
                user = messages[1]["content"]
                out = [f"{m.group(1)}. [译]{m.group(2)}"
                       for line in user.splitlines() if (m := _LINE.match(line))]
                return type("R", (), {"choices": [type("C", (), {
                    "message": type("M", (), {"content": "\n".join(out)})()})()]})()


def make_subs(n: int) -> list[srt.Subtitle]:
    return [srt.Subtitle(i + 1, srt.timedelta(seconds=i),
                         srt.timedelta(seconds=i + 1), f"テスト{i}番です。")
            for i in range(n)]


class TestBatches(unittest.TestCase):
    def test_split_by_count(self):
        batches = make_batches(make_subs(25))
        self.assertEqual([len(b) for b in batches], [20, 5])

    def test_parse_numbered(self):
        self.assertIsNone(parse_numbered("1. 你好\n3. 漏了2", 3))
        self.assertEqual(parse_numbered("1. 你好\n2. 世界", 2),
                         {1: "你好", 2: "世界"})


class TestSplitSegment(unittest.TestCase):
    def test_split_by_punctuation(self):
        parts = _split_segment(0.0, 10.0, "こんにちは。テストです。うまくいくか。")
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0][2], "こんにちは。")
        # 时间戳单调递增且不越界
        self.assertEqual(parts[0][0], 0.0)
        self.assertAlmostEqual(parts[-1][1], 10.0)
        for (_, e1, _), (s2, _, _) in zip(parts, parts[1:]):
            self.assertLessEqual(e1, s2 + 1e-9)

    def test_no_punctuation_long_text_hard_split(self):
        # 超过 2*max_chars(40) 才硬拆：50 字 → 20 + 30 两段
        parts = _split_segment(0.0, 12.0, "あ" * 50)
        self.assertEqual(len(parts), 2)
        self.assertEqual("".join(p[2] for p in parts), "あ" * 50)

    def test_short_text_untouched(self):
        self.assertEqual(_split_segment(1.0, 2.0, "短い。"), [(1.0, 2.0, "短い。")])


class TestTranslateAndMerge(unittest.TestCase):
    def test_translate_then_merge(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ja = d / "v.ja.srt"
            ja.write_text(srt.compose(make_subs(25)), encoding="utf-8")
            zh = translate(ja, d, FakeClient(), CFG)
            zh_subs = list(srt.parse(zh.read_text(encoding="utf-8")))
            self.assertEqual(len(zh_subs), 25)
            self.assertEqual(zh_subs[0].content, "[译]テスト0番です。")
            self.assertEqual(zh_subs[7].start, srt.timedelta(seconds=7))

            bi = list(srt.parse(
                merge(ja, zh, d).read_text(encoding="utf-8")))
            self.assertEqual(bi[0].content, "テスト0番です。\n[译]テスト0番です。")

    def test_merge_missing_zh_keeps_ja_only(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ja = d / "v.ja.srt"
            zh = d / "v.zh.srt"
            ja.write_text(srt.compose(make_subs(10)), encoding="utf-8")
            zh.write_text(srt.compose(make_subs(9)), encoding="utf-8")
            bi = list(srt.parse(merge(ja, zh, d).read_text(encoding="utf-8")))
            self.assertEqual(bi[9].content, "テスト9番です。")


class TestCliHelpers(unittest.TestCase):
    def test_valid_srt(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            good = d / "good.srt"
            good.write_text(srt.compose(make_subs(3)), encoding="utf-8")
            empty = d / "empty.srt"
            empty.touch()
            bad = d / "bad.srt"
            bad.write_text("这不是字幕", encoding="utf-8")
            self.assertTrue(_valid_srt(good))
            self.assertFalse(_valid_srt(empty))
            self.assertFalse(_valid_srt(bad))
            self.assertFalse(_valid_srt(d / "missing.srt"))

    def test_confirm_overwrites_eof_defaults_to_skip(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "a.sub.mp4").touch()
            with mock.patch("builtins.input", side_effect=EOFError):
                todo, skipped = confirm_overwrites([Path("a.mp4")], d, False)
            self.assertEqual(todo, [])
            self.assertEqual([v.name for v in skipped], ["a.mp4"])

    def test_collect_videos_mov_and_mp4(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "a.mp4").touch()
            (d / "b.MOV").touch()
            (d / "c.txt").touch()
            self.assertEqual([p.name for p in collect_videos(d)],
                             ["a.mp4", "b.MOV"])


class TestMisc(unittest.TestCase):
    def test_escape_filter_path(self):
        escaped = escape_filter_path(Path("a,b:c'd.srt"))
        self.assertIn("\\,", escaped)
        self.assertIn("\\:", escaped)
        self.assertIn("\\'", escaped)

    def test_config_missing_raises(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ConfigError):
                load(Path(d) / "nope.toml")

    def test_config_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.toml"
            p.write_text('[deepseek]\napi_key = "sk-x"\n', encoding="utf-8")
            cfg = load(p)
            self.assertEqual(cfg.model, "deepseek-chat")
            self.assertEqual(cfg.video_bitrate, "8M")


class TestReporter(unittest.TestCase):
    def test_report_content(self):
        from ja_video_subtitles.report import Reporter, StageRecord, VideoRecord
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "v.ja.srt").write_text(srt.compose(make_subs(3)),
                                        encoding="utf-8")
            (d / "v.sub.mp4").write_bytes(b"x" * 2048)
            rep = Reporter(d, version="0.1.1", asr_model="kotoba",
                           translate_model="deepseek-v4-flash",
                           base_url="https://api.deepseek.com", bitrate="8M")
            ok = VideoRecord("v.mp4", "v")
            ok.stages = [StageRecord("transcribe", "done", 8.2),
                         StageRecord("translate", "skipped")]
            rep.records.append(ok)
            rep.records.append(VideoRecord("w.mp4", "w", status="failed",
                                           error="boom"))
            path = rep.write()
            text = path.read_text(encoding="utf-8")
            self.assertIn("1 succeeded / 1 failed / 0 skipped", text)
            self.assertIn("v.ja.srt", text)
            self.assertIn("3 subtitles", text)
            self.assertIn("boom", text)
            self.assertNotIn("api_key", text)
            self.assertTrue(path.name.startswith("report-"))


if __name__ == "__main__":
    unittest.main()
