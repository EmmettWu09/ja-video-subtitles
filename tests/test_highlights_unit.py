"""Offline unit tests for the highlights pipeline internals; no API, no ffmpeg."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from ja_video_subtitles.config import Config, DEFAULT_USER_TEMPLATE
from ja_video_subtitles.highlights import (_key_parts, _load_state,
                                           _should_skip, _stage_key)
from ja_video_subtitles.highlights import analysis, timeline, transcript


def make_cfg(**overrides):
    values = dict(base_url="https://example.invalid", api_key="sk-test",
                  model="test-model", asr_model_id="test", prompt_system="",
                  prompt_user_template=DEFAULT_USER_TEMPLATE, force_style="",
                  video_bitrate="8M")
    values.update(overrides)
    return Config(**values)


def make_entries(count, step_ms=5000, duration_ms=2000, offset_ms=0):
    return [transcript.Entry(i + 1, offset_ms + i * step_ms,
                             offset_ms + i * step_ms + duration_ms,
                             f"文{i + 1}です。", f"句子{i + 1}。")
            for i in range(count)]


def response(content, finish_reason="stop"):
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


class FakeClient:
    """Scripted OpenAI-compatible stub: responses per call, in order."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    def create(self, model, messages, **kwargs):
        self.calls.append({"model": model, "messages": messages,
                           "kwargs": kwargs})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


CANDIDATE_JSON = json.dumps({
    "topics": ["自我介绍"],
    "candidates": [{"type": "完整表达", "start_index": 2, "end_index": 4,
                    "title_zh": "完整回答", "reason_zh": "句子完整",
                    "context_zh": "老师在提问", "confidence": "high"}]},
    ensure_ascii=False)

SUMMARY_JSON = json.dumps({
    "theme_zh": "自我介绍", "practice_zh": "问答练习",
    "expressions_zh": ["～です"], "highlights_zh": ["完整回答"],
    "intro_sentences": [{"ja": "今日は自己紹介です。", "zh": "今天是自我介绍。"},
                        {"ja": "よくできました。", "zh": "做得很好。"}],
    "closing_zh": "下节课见。"}, ensure_ascii=False)


class TestTranscript(unittest.TestCase):
    def write_pair(self, directory, ja_text, zh_text):
        ja = Path(directory) / "v.ja.srt"
        zh = Path(directory) / "v.zh.srt"
        ja.write_text(ja_text, encoding="utf-8")
        zh.write_text(zh_text, encoding="utf-8")
        return ja, zh

    def cue(self, index, start, end, text):
        def ts(seconds):
            return f"00:00:{seconds:02d},000"
        return f"{index}\n{ts(start)} --> {ts(end)}\n{text}\n\n"

    def test_pairs_by_index(self):
        with tempfile.TemporaryDirectory() as d:
            ja, zh = self.write_pair(d, self.cue(1, 0, 1, "こんにちは")
                                     + self.cue(2, 2, 3, "さようなら"),
                                     self.cue(1, 0, 1, "你好")
                                     + self.cue(2, 2, 3, "再见"))
            entries = transcript.build(ja, zh)
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0].ja, "こんにちは")
            self.assertEqual(entries[0].zh, "你好")
            self.assertEqual(entries[1].index, 2)
            self.assertFalse(entries[0].flags)

    def test_missing_and_mismatched_cues_are_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            ja, zh = self.write_pair(
                d,
                self.cue(1, 0, 1, "一") + self.cue(2, 5, 6, "二"),
                self.cue(2, 25, 26, "二译") + self.cue(3, 30, 31, "三译"))
            entries = transcript.build(ja, zh)
            flags = {entry.index: entry.flags for entry in entries}
            self.assertEqual(flags[1], [transcript.FLAG_MISSING_ZH])
            self.assertEqual(flags[2], [transcript.FLAG_TIME_MISMATCH])
            self.assertEqual(flags[3], [transcript.FLAG_MISSING_JA])
            # 中文-only cue keeps its own timing; nothing is guessed.
            orphan = next(e for e in entries if e.index == 3)
            self.assertEqual((orphan.start_ms, orphan.end_ms), (30000, 31000))
            self.assertEqual(orphan.ja, "")

    def test_unparsable_input_raises(self):
        with tempfile.TemporaryDirectory() as d:
            ja, zh = self.write_pair(d, "这不是字幕", self.cue(1, 0, 1, "译"))
            with self.assertRaises(ValueError):
                transcript.build(ja, zh)

    def test_duplicate_indices_raise(self):
        with tempfile.TemporaryDirectory() as d:
            ja, zh = self.write_pair(d, self.cue(1, 0, 1, "あ")
                                     + self.cue(1, 2, 3, "い"),
                                     self.cue(1, 0, 1, "译"))
            with self.assertRaisesRegex(ValueError, "unique integer"):
                transcript.build(ja, zh)


class TestChunking(unittest.TestCase):
    def test_five_minute_chunks_with_thirty_second_overlap(self):
        entries = make_entries(71, step_ms=10_000)  # 0..700s
        chunks = analysis.chunk_entries(entries)
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0][0].start_ms, 0)
        self.assertEqual(chunks[0][-1].start_ms, 290_000)
        # Overlap: cues from 270s-300s appear in both chunk 1 and 2.
        self.assertEqual(chunks[1][0].start_ms, 270_000)
        firsts = [chunk[0].start_ms for chunk in chunks]
        self.assertEqual(firsts, [0, 270_000, 540_000])
        shared = {e.index for e in chunks[0]} & {e.index for e in chunks[1]}
        self.assertTrue(shared)
        # Full coverage, stable order.
        self.assertEqual({e.index for chunk in chunks for e in chunk},
                         {e.index for e in entries})

    def test_short_transcript_single_chunk(self):
        self.assertEqual(len(analysis.chunk_entries(make_entries(5))), 1)
        self.assertEqual(analysis.chunk_entries([]), [])


class TestModelOutputValidation(unittest.TestCase):
    def setUp(self):
        self.entries = make_entries(6)

    def analyze(self, *replies):
        with tempfile.TemporaryDirectory() as d:
            client = FakeClient(*replies)
            outcome = analysis.analyze(client, make_cfg(), self.entries,
                                       Path(d))
            return outcome, client

    def test_valid_flow_references_indices_only(self):
        outcome, client = self.analyze(response(CANDIDATE_JSON),
                                       response(SUMMARY_JSON))
        self.assertEqual(len(outcome.candidates), 1)
        self.assertEqual(outcome.candidates[0].start_index, 2)
        self.assertEqual(outcome.summary["theme_zh"], "自我介绍")
        # Structured JSON mode and the configured model are used.
        for call in client.calls:
            self.assertEqual(call["model"], "test-model")
            self.assertEqual(call["kwargs"]["response_format"],
                             {"type": "json_object"})
            # The request carries subtitle text only, never media data.
            payload = json.dumps(call["messages"], ensure_ascii=False,
                                 default=str)
            self.assertNotIn("base64", payload)

    def test_invalid_then_valid_retries(self):
        outcome, client = self.analyze(response("not json"),
                                       response(CANDIDATE_JSON),
                                       response(SUMMARY_JSON))
        self.assertEqual(len(outcome.candidates), 1)
        self.assertEqual(len(client.calls), 3)

    def test_unknown_indices_fail_after_retries(self):
        bad = json.dumps({"candidates": [
            {"type": "完整表达", "start_index": 90, "end_index": 99,
             "title_zh": "t", "reason_zh": "r"}]}, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as d:
            client = FakeClient(*[response(bad)] * 3)
            with self.assertRaisesRegex(RuntimeError, "unknown subtitle"):
                analysis.analyze(client, make_cfg(), self.entries, Path(d))
            self.assertEqual(len(client.calls), 3)  # initial + 2 retries
            raw = list((Path(d)).glob("chunk-*-attempt-*.txt"))
            self.assertEqual(len(raw), 3)  # raw responses preserved

    def test_empty_and_truncated_responses_retry(self):
        for bad in (response(""), response(CANDIDATE_JSON,
                                           finish_reason="length")):
            with self.subTest(bad=bad):
                with tempfile.TemporaryDirectory() as d:
                    client = FakeClient(bad, bad, bad)
                    with self.assertRaises(RuntimeError):
                        analysis.analyze(client, make_cfg(), self.entries,
                                         Path(d))
                    self.assertEqual(len(client.calls), 3)

    def test_invalid_candidate_shapes(self):
        parse = lambda text: analysis._parse_candidates(text, {1, 2, 3})
        base = {"type": "完整表达", "start_index": 1, "end_index": 2,
                "title_zh": "t", "reason_zh": "r"}
        for mutate in (
                lambda c: c.update(type="发音优秀"),
                lambda c: c.update(start_index=3, end_index=1),
                lambda c: c.update(title_zh="  "),
                lambda c: c.update(reason_zh=""),
                lambda c: c.update(start_index=True)):
            candidate = dict(base)
            mutate(candidate)
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    parse(json.dumps({"candidates": [candidate]},
                                     ensure_ascii=False))


class TestSelection(unittest.TestCase):
    def setUp(self):
        self.entries = make_entries(10)

    def candidate(self, start, end, type="完整表达", confidence="high",
                  context="有上下文"):
        return analysis.Candidate(type, start, end, f"标题{start}", "理由",
                                  context, confidence)

    def test_low_confidence_and_missing_context_go_to_review(self):
        selection = analysis.select(self.entries, [
            self.candidate(1, 2, confidence="low"),
            self.candidate(3, 4, context=""),
            self.candidate(5, 6)])
        self.assertEqual(len(selection.kept), 1)
        self.assertEqual(len(selection.review), 2)
        self.assertEqual(len(selection.discarded), 0)

    def test_bare_acknowledgement_praise_is_discarded(self):
        for entry in self.entries[:3]:
            entry.ja = "はい"
        selection = analysis.select(self.entries, [
            self.candidate(1, 3, type="老师认可")])
        self.assertEqual(selection.kept, [])
        self.assertEqual(len(selection.discarded), 1)
        self.assertIn("孤立应答", selection.discarded[0]["reason"])

    def test_overlapping_candidates_merge(self):
        selection = analysis.select(self.entries, [
            self.candidate(2, 5), self.candidate(4, 7),
            self.candidate(9, 10)])
        self.assertEqual(len(selection.kept), 2)
        merged = selection.kept[0]
        self.assertEqual((merged.start_index, merged.end_index), (2, 7))
        self.assertIn("合并", json.dumps(selection.decisions,
                                         ensure_ascii=False))


class TestTimeline(unittest.TestCase):
    def test_adjudication_pads_clamps_and_separates(self):
        entries = make_entries(20, step_ms=10_000, duration_ms=3000)
        kept = [analysis.Candidate("完整表达", 2, 3, "a", "r", "c", "high"),
                analysis.Candidate("主动交流", 4, 5, "b", "r", "c", "high")]
        bounds = timeline.adjudicate(kept, entries, video_ms=197_000)
        self.assertEqual(bounds[0]["start_ms"], 10_000 - 1500)
        self.assertEqual(bounds[0]["end_ms"], 23_000 + 1500)
        # The second event's padded start would overlap; the midpoint splits.
        self.assertLessEqual(bounds[0]["end_ms"], bounds[1]["start_ms"])
        self.assertGreater(bounds[1]["end_ms"], bounds[1]["start_ms"])

    def test_adjudication_clamps_to_video(self):
        entries = make_entries(2, step_ms=1000, duration_ms=500)
        kept = [analysis.Candidate("完整表达", 1, 2, "a", "r", "c", "high")]
        bounds = timeline.adjudicate(kept, entries, video_ms=2000)
        self.assertEqual(bounds[0]["start_ms"], 0)
        self.assertEqual(bounds[0]["end_ms"], 2000)

    def test_intersect_cues_clips_and_shifts(self):
        entries = [transcript.Entry(1, 0, 4000, "一", "1"),
                   transcript.Entry(2, 4000, 8000, "二", "2"),
                   transcript.Entry(3, 8000, 12000, "三", "3")]
        cues = timeline.intersect_cues(entries, 1, 3, 2000, 9000, 50_000)
        # cue1 clipped to [2000,4000) -> [50000,52000); cue3 clipped to 9000.
        self.assertEqual([(c["start_ms"], c["end_ms"]) for c in cues],
                         [(50_000, 52_000), (52_000, 56_000), (56_000, 57_000)])
        for cue in cues:
            self.assertGreaterEqual(cue["start_ms"], 50_000)
            self.assertGreater(cue["end_ms"], cue["start_ms"])

    def test_compose_and_validate_srt(self):
        text = timeline.compose_srt([
            {"start_ms": 0, "end_ms": 1500, "ja": "あ", "zh": "啊"},
            {"start_ms": 1500, "end_ms": 3000, "ja": "い", "zh": ""}])
        self.assertTrue(timeline.valid_srt(text))
        self.assertFalse(timeline.valid_srt(""))
        self.assertFalse(timeline.valid_srt("不是字幕"))


class TestRenderReplace(unittest.TestCase):
    def test_missing_partial_raises_clear_error(self):
        from unittest import mock
        from ja_video_subtitles.highlights import render
        with tempfile.TemporaryDirectory() as d:
            final = Path(d) / "v.highlights.mp4"
            with mock.patch.object(render, "_concat", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "missing or empty"):
                    render._replace_rendered(Path("ffmpeg"), [Path("s")],
                                             final, None)
            self.assertFalse(final.exists())
            self.assertFalse(
                (Path(d) / ".v.highlights.mp4.partial.mp4").exists())

    def test_successful_concat_replaces_final(self):
        from unittest import mock
        from ja_video_subtitles.highlights import render
        with tempfile.TemporaryDirectory() as d:
            final = Path(d) / "v.highlights.mp4"

            def fake_concat(segments, out, ffmpeg, cfg):
                out.write_bytes(b"rendered")

            with mock.patch.object(render, "_concat", fake_concat):
                render._replace_rendered(Path("ffmpeg"), [Path("s")],
                                         final, None)
            self.assertEqual(final.read_bytes(), b"rendered")
            self.assertFalse(
                (Path(d) / ".v.highlights.mp4.partial.mp4").exists())


class TestEssencePlan(unittest.TestCase):
    def bound(self, event, start_ms, end_ms):
        return {"event": event, "type": "完整表达", "title_zh": f"事件{event}",
                "reason_zh": "r", "context_zh": "c",
                "start_index": event, "end_index": event,
                "start_ms": start_ms, "end_ms": end_ms}

    def summary(self):
        return json.loads(SUMMARY_JSON)

    def test_budget_selects_events_with_bridges_between(self):
        bounds = [self.bound(i, i * 60_000, i * 60_000 + 55_000)
                  for i in range(6)]
        plan = timeline.build_essence_plan(self.summary(), bounds, 240, 0,
                                           400_000)
        kinds = [seg["kind"] for seg in plan["segments"]]
        self.assertEqual(kinds[0], "intro")
        self.assertEqual(kinds[-1], "closing")
        self.assertIn("event", kinds)
        # Bridges only appear between events, never before the first one.
        first_event = kinds.index("event")
        self.assertNotEqual(kinds[first_event - 1], "bridge")
        events = [seg for seg in plan["segments"] if seg["kind"] == "event"]
        nominal = sum(seg["nominal_ms"] for seg in plan["segments"])
        self.assertLessEqual(nominal, 240_000 + 55_000)
        self.assertLess(len(events), len(bounds))  # budget was enforced

    def test_oversized_first_event_is_kept_whole(self):
        plan = timeline.build_essence_plan(self.summary(),
                                           [self.bound(0, 0, 500_000)],
                                           60, 0, 600_000)
        events = [seg for seg in plan["segments"] if seg["kind"] == "event"]
        self.assertEqual(len(events), 1)  # 完整事件不为比例裁剪

    def test_short_material_is_marked_as_draft(self):
        plan = timeline.build_essence_plan(self.summary(),
                                           [self.bound(0, 0, 30_000)],
                                           240, 0, 100_000)
        self.assertIn("草稿", plan["draft"])

    def test_intro_start_outside_video_raises(self):
        with self.assertRaises(RuntimeError):
            timeline.build_essence_plan(self.summary(), [], 240, 59_000,
                                        60_000)


class TestCacheKeys(unittest.TestCase):
    def parts(self, **overrides):
        base = {"video": "v", "ja_srt": "j", "zh_srt": "z", "model": "m",
                "prompt_version": 1, "ja_voice": "Kyoko",
                "zh_voice": "Tingting", "target_seconds": 240,
                "intro_start_seconds": 0}
        base.update(overrides)
        return base

    def test_granularity(self):
        base = self.parts()
        voices = self.parts(ja_voice="Otoya")
        # Voice changes invalidate TTS/plan/render but keep analysis & clips.
        for stage in ("transcript", "analysis", "selection", "boundaries",
                      "clips"):
            self.assertEqual(_stage_key(base, stage), _stage_key(voices, stage))
        for stage in ("tts", "plan", "render"):
            self.assertNotEqual(_stage_key(base, stage),
                                _stage_key(voices, stage))
        # Subtitle changes invalidate everything.
        edited = self.parts(ja_srt="edited")
        for stage in ("analysis", "clips", "tts", "render"):
            self.assertNotEqual(_stage_key(base, stage),
                                _stage_key(edited, stage))
        # Target duration only affects planning downstream.
        target = self.parts(target_seconds=300)
        self.assertEqual(_stage_key(base, "clips"), _stage_key(target, "clips"))
        self.assertNotEqual(_stage_key(base, "plan"), _stage_key(target, "plan"))

    def test_state_skip_rules(self):
        state = {"version": 1,
                 "stages": {"clips": {"status": "done", "key": "abc"}}}
        self.assertTrue(_should_skip(state, "clips", "abc", force=False))
        self.assertFalse(_should_skip(state, "clips", "abc", force=True))
        self.assertFalse(_should_skip(state, "clips", "different", force=False))
        self.assertFalse(_should_skip(state, "render", "abc", force=False))

    def test_broken_state_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            hdir = Path(d)
            (hdir / "state.json").write_text("not json", encoding="utf-8")
            self.assertEqual(_load_state(hdir)["stages"], {})


if __name__ == "__main__":
    unittest.main()
