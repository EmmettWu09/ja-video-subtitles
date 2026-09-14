"""Offline vocabulary selection, gloss protocol, artifacts and resume tests."""

import copy
import io
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import srt

from ja_video_subtitles import vocabulary as vocab
from ja_video_subtitles.config import Config

CFG = Config(base_url="https://example.test/v1", api_key="test-secret", model="test-model",
             asr_model_id="test-asr", prompt_system="", prompt_user_template="",
             force_style="", video_bitrate="8M")


class Token:
    def __init__(self, surface, lemma=None, reading="テスト", pos=("名詞", "普通名詞")):
        self._surface, self._lemma = surface, lemma or surface
        self._reading, self._pos = reading, pos

    def surface(self):
        return self._surface

    def dictionary_form(self):
        return self._lemma

    def reading_form(self):
        return self._reading

    def part_of_speech(self):
        return self._pos


class Tokenizer:
    def __init__(self, lines):
        self.lines = lines

    def tokenize(self, text, mode):
        return self.lines.get(text, [])


class Lexicon:
    name = "test-lexicon"
    version = "sha256:test-v1"
    source_url = "https://example.test/lexicon"
    license = "CC-BY-SA-4.0"

    def __init__(self, entries=None):
        self.entries = entries or {}

    def lookup(self, lemma, reading):
        return self.entries.get((lemma, reading))


class Client:
    def __init__(self, respond=None):
        self.calls = []
        self.respond = respond
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        entries = json.loads(kwargs["messages"][1]["content"])["items"]
        if self.respond:
            text = self.respond(entries)
        else:
            # Return reverse order and an untrusted level to prove ID alignment
            # and the inability of the remote service to replace local grading.
            text = json.dumps({"items": [
                {"id": entry["id"], "meaning_zh": "解释" + entry["lemma"],
                 "note_zh": "用法", "jlpt_level": "N5"}
                for entry in reversed(entries)]}, ensure_ascii=False)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def subs(lines):
    return [srt.Subtitle(index, srt.timedelta(seconds=start),
                         srt.timedelta(seconds=start + 1), text)
            for index, start, text in lines]


class VocabularyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.ja, self.zh = self.directory / "film.ja.srt", self.directory / "film.zh.srt"
        self.out = self.directory / "out"
        self.lines = {"考える": [Token("考える", reading="カンガエル", pos=("動詞", "一般"))]}
        self.lexicon = Lexicon({("高度", "こうど"): "N2", ("懸念", "けねん"): "N1",
                                ("考える", "かんがえる"): "N2", ("普通", "ふつう"): "N3",
                                ("簡単", "かんたん"): "N4", ("学校", "がっこう"): "N5"})
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(vocab, "_load_tokenizer", return_value=(Tokenizer(self.lines), "mode")).start()
        mock.patch.object(vocab.jlpt_lexicon, "load", return_value=self.lexicon).start()
        mock.patch.object(vocab.time, "sleep").start()
        self.client = Client()
        self.write_subs([(1, 0, "最初")])
        self.lines["最初"] = [Token("高度", reading="コウド"), Token("懸念", reading="ケネン")]

    def write_subs(self, ja, zh=None):
        self.ja.write_text(srt.compose(subs(ja), reindex=False), encoding="utf-8")
        zh = zh if zh is not None else [(index, start, "译" + text) for index, start, text in ja]
        self.zh.write_text(srt.compose(subs(zh), reindex=False), encoding="utf-8")

    def run_generate(self, cfg=CFG, client=None, **kwargs):
        return vocab.generate(self.ja, self.zh, self.out, cfg,
                              client=client or self.client, **kwargs)

    def entries(self, result):
        return json.loads(result.json_path.read_text(encoding="utf-8"))["entries"]

    def test_strict_level_threshold_and_deterministic_group_order(self):
        self.lines["最初"] += [Token("普通", reading="フツウ"), Token("簡単", reading="カンタン"),
                             Token("学校", reading="ガッコウ"), Token("未知", reading="ミチ")]
        n3 = self.entries(self.run_generate())
        self.assertEqual([word["jlpt_level"] for word in n3], ["N2", "N1", "未分级"])
        n4 = self.entries(self.run_generate(replace(CFG, learner_level="N4")))
        self.assertEqual([word["jlpt_level"] for word in n4], ["N3", "N2", "N1", "未分级"])
        n1 = self.entries(self.run_generate(replace(CFG, learner_level="N1")))
        self.assertEqual([word["jlpt_level"] for word in n1], ["未分级"])
        n5 = self.entries(self.run_generate(replace(CFG, learner_level="N5")))
        self.assertEqual([word["jlpt_level"] for word in n5], ["N4", "N3", "N2", "N1", "未分级"])

    def test_inflections_reading_counts_surface_forms_and_example_limit(self):
        self.write_subs([(9, 0, "A"), (10, 2, "B"), (15, 4, "C"), (20, 6, "D")],
                        [(20, 6, "中文四"), (9, 0, "中文一"), (15, 4, "中文三"), (10, 2, "中文二")])
        stem = Token("考え", "考える", "カンガエ", ("動詞", "一般"))
        base = Token("考える", reading="カンガエル", pos=("動詞", "一般"))
        self.lines.update({"A": [stem, stem], "B": [base], "C": [stem], "D": [base]})
        entry, = self.entries(self.run_generate())
        self.assertEqual((entry["lemma"], entry["reading"]), ("考える", "かんがえる"))
        self.assertEqual(entry["occurrence_count"], 5)
        self.assertEqual(entry["surface_forms"], ["考え", "考える"])
        self.assertEqual([example["index"] for example in entry["examples"]], [9, 10, 15])
        self.assertEqual([example["zh"] for example in entry["examples"]], ["中文一", "中文二", "中文三"])
        self.assertEqual(entry["first_occurrence"], "00:00:00.000")

    def test_pos_filter_unknown_proper_names_and_single_kana(self):
        self.lexicon.entries[("鈴木", "すずき")] = "N1"  # proper nouns never receive this grade
        self.lines["最初"] = [Token("鈴木", reading="スズキ", pos=("名詞", "固有名詞", "人名")),
                             Token("は", pos=("助詞",)), Token("た", pos=("助動詞",)),
                             Token("123", pos=("名詞", "数詞")), Token("。", pos=("補助記号",)),
                             Token("★", pos=("名詞",)), Token("三", pos=("名詞", "数詞")),
                             Token("の", pos=("名詞",)), Token("する", pos=("動詞",)),
                             Token("い", pos=("動詞", "非自立可能")),
                             Token("木", reading="キ", pos=("名詞", "普通名詞"))]
        entries = self.entries(self.run_generate())
        self.assertEqual({entry["lemma"] for entry in entries}, {"鈴木", "木"})
        proper = next(entry for entry in entries if entry["lemma"] == "鈴木")
        self.assertTrue(proper["is_proper_noun"])
        self.assertEqual(proper["jlpt_level"], "未分级")
        self.assertEqual(self.entries(self.run_generate(replace(CFG, include_unknown=False))), [])

    def test_homographs_keep_distinct_readings_and_unknown_is_conservative(self):
        self.lines["最初"] = [Token("生", reading="セイ"), Token("生", reading="ナマ"), Token("生", reading="ショウ")]
        self.lexicon.entries.update({("生", "せい"): "N2", ("生", "なま"): "N1"})
        words = self.entries(self.run_generate())
        self.assertEqual({(word["reading"], word["jlpt_level"]) for word in words},
                         {("せい", "N2"), ("なま", "N1"), ("しょう", "未分级")})
        self.assertEqual(len({word["id"] for word in words}), 3)

    def test_inflected_homographs_keep_context_reading(self):
        self.lines["最初"] = [Token("開い", "開く", "アイ", ("動詞", "一般")),
                             Token("開い", "開く", "ヒライ", ("動詞", "一般"))]
        self.lines["開く"] = [Token("開く", reading="ヒラク", pos=("動詞", "一般"))]
        self.lexicon.entries.update({("開く", "あく"): "N2", ("開く", "ひらく"): "N1"})
        words = self.entries(self.run_generate())
        self.assertEqual({(word["reading"], word["jlpt_level"]) for word in words},
                         {("あく", "N2"), ("ひらく", "N1")})

    def test_group_order_first_timestamp_then_lemma(self):
        self.write_subs([(30, 30, "後"), (10, 10, "前")])
        self.lines["後"] = [Token("高度", reading="コウド")]
        self.lines["前"] = [Token("考える", reading="カンガエル", pos=("動詞", "一般")), Token("懸念", reading="ケネン")]
        entries = self.entries(self.run_generate())
        self.assertEqual([entry["lemma"] for entry in entries], ["考える", "高度", "懸念"])
        self.assertEqual(entries[0]["first_start_ms"], 10000)

    def test_api_reorders_by_id_and_cannot_override_local_grade(self):
        result = self.run_generate()
        for entry in self.entries(result):
            self.assertEqual(entry["meaning_zh"], "解释" + entry["lemma"])
            self.assertIn(entry["jlpt_level"], ("N2", "N1"))
        self.assertEqual(self.client.calls[0]["model"], CFG.model)
        self.assertEqual(result.degraded_count, 0)

    def test_api_protocol_rejects_malformed_missing_duplicate_wrong_types_extra_id(self):
        correct = {"id": "w1", "meaning_zh": "词义", "note_zh": ""}
        invalid = ["not json", "[]", '{"items":null}', json.dumps({"items": []}),
                   json.dumps({"items": [correct, correct]}),
                   json.dumps({"items": [dict(correct, meaning_zh=4)]}),
                   json.dumps({"items": [dict(correct, note_zh=None)]}),
                   json.dumps({"items": [dict(correct, id="unexpected")]}),
                   json.dumps({"items": [dict(correct, meaning_zh=" ")]}),
                   json.dumps({"items": [dict(correct, id=[])]})]
        for response in invalid:
            with self.subTest(response=response):
                self.assertIsNone(vocab._parse_glosses(response, {"w1"}))
        self.assertEqual(vocab._parse_glosses(json.dumps({"items": [correct]}), {"w1"}),
                         {"w1": ("词义", "")})

    def test_retry_splits_then_single_word_degrades_and_preserves_local_data(self):
        def response(entries):
            if len(entries) > 1 or entries[0]["lemma"] == "高度":
                return '{"items":[]}'
            return json.dumps({"items": [{"id": entries[0]["id"], "meaning_zh": "担忧", "note_zh": ""}]})
        client = Client(response)
        result = self.run_generate(client=client)
        self.assertEqual(len(client.calls), 5)  # 2 batch retries + 2 failed singleton + success
        self.assertEqual(result.degraded_count, 1)
        self.assertEqual(result.total_count, 2)
        words = {entry["lemma"]: entry for entry in self.entries(result)}
        self.assertEqual(words["高度"]["meaning_zh"], "")
        self.assertTrue(words["高度"]["warning"])
        self.assertEqual(words["高度"]["jlpt_level"], "N2")
        self.assertEqual(words["懸念"]["meaning_zh"], "担忧")
        self.assertEqual(len(result.warnings), 1)

    def test_retry_can_recover_without_split(self):
        calls = 0
        def response(entries):
            nonlocal calls
            calls += 1
            if calls == 1:
                return "bad"
            return json.dumps({"items": [{"id": entry["id"], "meaning_zh": "好", "note_zh": ""}
                                          for entry in entries]})
        result = self.run_generate(client=Client(response))
        self.assertEqual(calls, 2)
        self.assertEqual(result.degraded_count, 0)

    def test_network_errors_never_log_secrets_or_raw_response(self):
        def response(entries):
            raise RuntimeError("Authorization: Bearer private-test-secret")
        stderr = io.StringIO()
        with mock.patch("sys.stderr", stderr):
            result = self.run_generate(client=Client(response))
        self.assertEqual(result.degraded_count, 2)
        self.assertNotIn("private-test-secret", stderr.getvalue())
        self.assertNotIn("Authorization", stderr.getvalue())
        self.assertNotIn(CFG.api_key, result.json_path.read_text(encoding="utf-8"))

    def test_empty_artifacts_without_client_construction(self):
        self.lines["最初"] = [Token("学校", reading="ガッコウ")]
        with mock.patch("openai.OpenAI", side_effect=AssertionError("must not construct client")):
            result = vocab.generate(self.ja, self.zh, self.out, CFG)
        self.assertEqual(result.total_count, 0)
        self.assertEqual(self.entries(result), [])
        self.assertIn("未发现符合条件的词汇", result.markdown_path.read_text(encoding="utf-8"))
        self.assertEqual(result.json_path.name, "film.vocab.json")
        self.assertTrue(vocab._valid_document(json.loads(result.json_path.read_text(encoding="utf-8"))))

    def test_freshness_skips_tokenizer_and_client(self):
        first = self.run_generate()
        with mock.patch.object(vocab, "_load_tokenizer", side_effect=AssertionError("cache should skip")), \
                mock.patch("openai.OpenAI", side_effect=AssertionError("cache should skip")):
            result = vocab.generate(self.ja, self.zh, self.out, CFG)
        self.assertEqual(result.status, "skipped")
        self.assertEqual(first.total_count, result.total_count)
        self.assertEqual(len(self.client.calls), 1)

    def test_force_source_translation_settings_and_dataset_changes_rebuild(self):
        self.run_generate()
        self.assertEqual(self.run_generate(force=True).status, "done")
        for field, value in (("learner_level", "N2"), ("include_unknown", False), ("max_examples", 1)):
            with self.subTest(field=field):
                self.assertEqual(self.run_generate(replace(CFG, **{field: value})).status, "done")
                self.run_generate()
        self.ja.write_text(self.ja.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assertEqual(self.run_generate().status, "done")
        self.zh.write_text(self.zh.read_text(encoding="utf-8").replace("译", "新译"), encoding="utf-8")
        self.assertEqual(self.run_generate().status, "done")
        self.assertTrue(all(example["zh"].startswith("新译") for entry in self.entries(self.run_generate())
                            for example in entry["examples"]))
        self.lexicon.version = "sha256:test-v2"
        self.assertEqual(self.run_generate().status, "done")

    def test_missing_corrupt_mismatched_artifacts_rebuild(self):
        result = self.run_generate()
        result.markdown_path.unlink()
        self.assertEqual(self.run_generate().status, "done")
        result.markdown_path.write_text("truncated", encoding="utf-8")
        self.assertEqual(self.run_generate().status, "done")
        result.json_path.write_text('{"partial":', encoding="utf-8")
        self.assertEqual(self.run_generate().status, "done")
        data = json.loads(result.json_path.read_text(encoding="utf-8"))
        data["entries"][0]["occurrence_count"] = "three"
        result.json_path.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.run_generate().status, "done")

    def test_document_schema_rejects_corrupt_entries_even_matching_markdown(self):
        result = self.run_generate()
        data = json.loads(result.json_path.read_text(encoding="utf-8"))
        for field, value in (("examples", []), ("jlpt_level", "N3"), ("is_proper_noun", 1),
                             ("surface_forms", "高度"), ("occurrence_count", 0),
                             ("first_occurrence", "wrong"), ("warning", "invalid with gloss")):
            with self.subTest(field=field):
                bad = copy.deepcopy(data)
                bad["entries"][0][field] = value
                self.assertFalse(vocab._valid_document(bad))
        for version in (True, "1", 0):
            bad = copy.deepcopy(data)
            bad["schema_version"] = version
            self.assertFalse(vocab._valid_document(bad))
        self.assertTrue(vocab._valid_document(data))
        self.assertEqual(result.markdown_path.read_text(encoding="utf-8"), vocab.render_markdown(data))
        text = result.markdown_path.read_text(encoding="utf-8")
        self.assertLess(text.index("## N2"), text.index("## N1"))
        for expected in ("非官方等级参考", self.lexicon.source_url, self.lexicon.version, "字幕 #1", "译最初"):
            self.assertIn(expected, text)

    def test_atomic_pair_interruption_is_detected_and_temporary_files_cleaned(self):
        result = self.run_generate()
        original = result.json_path.read_text(encoding="utf-8")
        real_replace = vocab.os.replace
        calls = []
        def interrupted(source, destination):
            calls.append(destination)
            if destination == result.json_path:
                raise OSError("simulated interruption before commit")
            return real_replace(source, destination)
        with mock.patch.object(vocab.os, "replace", side_effect=interrupted):
            with self.assertRaisesRegex(OSError, "simulated interruption"):
                self.run_generate(force=True)
        self.assertEqual(result.json_path.read_text(encoding="utf-8"), original)
        self.assertEqual(list(self.out.glob(".*.tmp")), [])
        self.assertEqual(self.run_generate().status, "done")
        self.assertEqual(self.run_generate().status, "skipped")

    def test_formats_create_only_selected_files_in_requested_directory(self):
        for output_format, extensions in (("md", {"md"}), ("json", {"json"}),
                                           ("both", {"md", "json"})):
            with self.subTest(output_format=output_format):
                self.out = self.directory / "separate vocabulary" / output_format
                result = self.run_generate(replace(CFG, vocabulary_format=output_format))
                self.assertEqual({path.name for path in self.out.iterdir()},
                                 {f"film.vocab.{extension}" for extension in extensions})
                self.assertEqual(result.json_path,
                                 self.out / "film.vocab.json" if "json" in extensions else None)
                self.assertEqual(result.markdown_path,
                                 self.out / "film.vocab.md" if "md" in extensions else None)
                self.assertEqual(result.total_count, 2)
        self.assertFalse((self.directory / "film.vocab.md").exists())
        self.assertFalse((self.directory / "film.vocab.json").exists())

    def test_single_format_resume_needs_no_unselected_artifact(self):
        for output_format, unselected_extension in (("md", "json"), ("json", "md")):
            with self.subTest(output_format=output_format):
                self.out = self.directory / output_format
                cfg = replace(CFG, vocabulary_format=output_format)
                self.run_generate(cfg)
                unselected = self.out / f"film.vocab.{unselected_extension}"
                self.assertFalse(unselected.exists())
                with mock.patch.object(vocab, "_load_tokenizer",
                                       side_effect=AssertionError("fresh artifact must be reused")), \
                        mock.patch("openai.OpenAI", side_effect=AssertionError("must not call API")):
                    self.assertEqual(vocab.generate(self.ja, self.zh, self.out, cfg).status, "skipped")
                    unselected.write_bytes(b"stale unselected content")
                    old_mtime = unselected.stat().st_mtime_ns
                    self.assertEqual(vocab.generate(self.ja, self.zh, self.out, cfg).status, "skipped")
                self.assertEqual(unselected.read_bytes(), b"stale unselected content")
                self.assertEqual(unselected.stat().st_mtime_ns, old_mtime)

    def test_switching_formats_reuses_structured_content_without_api(self):
        for previous in ("md", "json", "both"):
            for selected in ("md", "json", "both"):
                if previous == selected:
                    continue
                with self.subTest(previous=previous, selected=selected):
                    self.out = self.directory / f"{previous}-to-{selected}"
                    self.run_generate(replace(CFG, vocabulary_format=previous))
                    cfg = replace(CFG, vocabulary_format=selected)
                    unselected = (self.out / f"film.vocab.{'json' if selected == 'md' else 'md'}"
                                  if selected != "both" else None)
                    before = (unselected.read_bytes() if unselected is not None and unselected.exists()
                              else None)
                    calls = len(self.client.calls)
                    with mock.patch.object(vocab, "_load_tokenizer",
                                           side_effect=AssertionError("format change must reuse data")):
                        result = self.run_generate(cfg)
                        self.assertEqual(result.status, "skipped" if (previous, selected) == ("both", "json")
                                         else "done")
                        self.assertEqual(self.run_generate(cfg).status, "skipped")
                    self.assertEqual(len(self.client.calls), calls)
                    self.assertEqual(result.total_count, 2)
                    if before is not None:
                        self.assertEqual(unselected.read_bytes(), before)
                    elif unselected is not None:
                        self.assertFalse(unselected.exists())

    def test_single_selected_artifact_missing_or_corrupt_regenerates(self):
        for output_format in ("md", "json"):
            with self.subTest(output_format=output_format):
                self.out = self.directory / output_format
                cfg = replace(CFG, vocabulary_format=output_format)
                result = self.run_generate(cfg)
                selected = result.markdown_path if output_format == "md" else result.json_path
                for corrupted in (None, "truncated"):
                    if corrupted is None:
                        selected.unlink()
                    else:
                        selected.write_text(corrupted, encoding="utf-8")
                    calls = len(self.client.calls)
                    self.assertEqual(self.run_generate(cfg).status, "done")
                    self.assertEqual(len(self.client.calls), calls + 1)
                    self.assertEqual(self.run_generate(cfg).status, "skipped")
                if output_format == "md":
                    selected.write_text(selected.read_text(encoding="utf-8").replace("中文：", "中文修改：", 1),
                                        encoding="utf-8")
                else:
                    data = json.loads(selected.read_text(encoding="utf-8"))
                    data["entries"][0]["occurrence_count"] = "bad"
                    selected.write_text(json.dumps(data), encoding="utf-8")
                calls = len(self.client.calls)
                self.assertEqual(self.run_generate(cfg).status, "done")
                self.assertEqual(len(self.client.calls), calls + 1)

    def test_format_switch_preserves_newest_glosses_after_forced_single_output(self):
        for forced_format in ("md", "json"):
            with self.subTest(forced_format=forced_format):
                self.out = self.directory / forced_format
                self.run_generate(replace(CFG, vocabulary_format="md"))
                self.run_generate(replace(CFG, vocabulary_format="json"))
                updated_client = Client(lambda entries: json.dumps({"items": [
                    {"id": entry["id"], "meaning_zh": "更新释义", "note_zh": ""}
                    for entry in entries]}, ensure_ascii=False))
                self.run_generate(replace(CFG, vocabulary_format=forced_format),
                                  client=updated_client, force=True)
                with mock.patch.object(vocab, "_load_tokenizer",
                                       side_effect=AssertionError("format change must reuse latest data")):
                    result = self.run_generate()
                self.assertEqual(result.status, "done")
                self.assertTrue(all(entry["meaning_zh"] == "更新释义" for entry in self.entries(result)))
                self.assertIn("更新释义", result.markdown_path.read_text(encoding="utf-8"))
                self.assertEqual(len(updated_client.calls), 1)

    def test_markdown_embedded_cache_checks_schema_and_safely_encodes_text(self):
        cfg = replace(CFG, vocabulary_format="md")
        client = Client(lambda entries: json.dumps({"items": [
            {"id": entry["id"], "meaning_zh": "内容 --> <!-- 保留", "note_zh": "说明"}
            for entry in entries]}, ensure_ascii=False))
        result = self.run_generate(cfg, client=client)
        text = result.markdown_path.read_text(encoding="utf-8")
        self.assertEqual(text.count(vocab.MARKDOWN_CACHE_PREFIX), 1)
        self.assertEqual(text.count("-->"), 1)
        self.assertEqual(self.run_generate(cfg, client=client).status, "skipped")
        data = vocab._read_fresh_document(
            result.markdown_path,
            {"ja_srt": self.ja.name, "zh_srt": self.zh.name,
             "ja_srt_sha256": vocab.hashlib.sha256(self.ja.read_bytes()).hexdigest(),
             "zh_srt_sha256": vocab.hashlib.sha256(self.zh.read_bytes()).hexdigest()},
            vocab._settings(cfg, self.lexicon),
            {"name": self.lexicon.name, "version": self.lexicon.version,
             "source_url": self.lexicon.source_url, "license": self.lexicon.license}, markdown=True)
        self.assertIsNotNone(data)
        data["schema_version"] = 0
        result.markdown_path.write_text(vocab._standalone_markdown(data), encoding="utf-8")
        self.assertEqual(self.run_generate(cfg, client=client).status, "done")
        self.assertEqual(len(client.calls), 2)

    def test_standalone_freshness_invalidates_changed_inputs_settings_and_force(self):
        for output_format in ("md", "json"):
            with self.subTest(output_format=output_format):
                self.out = self.directory / output_format
                cfg = replace(CFG, vocabulary_format=output_format)
                self.run_generate(cfg)
                calls = len(self.client.calls)
                self.assertEqual(self.run_generate(cfg, force=True).status, "done")
                self.assertEqual(len(self.client.calls), calls + 1)
                self.zh.write_text(self.zh.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                self.assertEqual(self.run_generate(cfg).status, "done")
                self.assertEqual(self.run_generate(replace(cfg, max_examples=1)).status, "done")
                self.lexicon.version += "-changed"
                self.assertEqual(self.run_generate(cfg).status, "done")

    def test_single_artifact_failed_replace_preserves_previous_output(self):
        for output_format in ("md", "json"):
            with self.subTest(output_format=output_format):
                self.out = self.directory / output_format
                cfg = replace(CFG, vocabulary_format=output_format)
                result = self.run_generate(cfg)
                selected = result.markdown_path if output_format == "md" else result.json_path
                original = selected.read_bytes()
                with mock.patch.object(vocab.os, "replace", side_effect=OSError("simulated interruption")):
                    with self.assertRaisesRegex(OSError, "simulated interruption"):
                        self.run_generate(cfg, force=True)
                self.assertEqual(selected.read_bytes(), original)
                self.assertEqual(list(self.out.glob(".*.tmp")), [])
                self.assertEqual(self.run_generate(cfg).status, "skipped")

    def test_stage_failures_propagate_without_partial_artifacts(self):
        with mock.patch.object(vocab, "_load_tokenizer", side_effect=RuntimeError("dictionary broken")):
            with self.assertRaisesRegex(RuntimeError, "dictionary broken"):
                self.run_generate()
        self.assertFalse(self.out.exists())
        with mock.patch.object(vocab.jlpt_lexicon, "load", side_effect=ValueError("invalid lexicon")):
            with self.assertRaisesRegex(ValueError, "invalid lexicon"):
                self.run_generate()
        self.ja.write_text("1\n00:00:00,000 --> 00:00:01,000\n最初\n\n"
                           "1\n00:00:02,000 --> 00:00:03,000\n最初\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unique integer SRT indices"):
            self.run_generate()

    def test_check_ready_loads_both_dependencies(self):
        vocab.check_ready()
        vocab.jlpt_lexicon.load.assert_called_once()
        with mock.patch.object(vocab.jlpt_lexicon, "load", side_effect=ValueError("missing data")):
            with self.assertRaisesRegex(ValueError, "missing data"):
                vocab.check_ready()

    def test_stable_word_ids_do_not_depend_on_batch_or_first_occurrence(self):
        first = {entry["lemma"]: entry["id"] for entry in self.entries(self.run_generate())}
        self.lines["最初"] = list(reversed(self.lines["最初"])) + [Token("未知", reading="ミチ")]
        second = {entry["lemma"]: entry["id"] for entry in self.entries(self.run_generate(force=True))}
        self.assertEqual(first, {lemma: second[lemma] for lemma in first})


class RealMorphologyTests(unittest.TestCase):
    def test_real_sudachi_inflection_reading_and_proper_noun(self):
        try:
            import sudachipy  # noqa: F401
        except ImportError:
            self.skipTest("SudachiPy not installed")
        analyzer, mode = vocab._load_tokenizer()
        tokens = list(analyzer.tokenize("考えていた。考える。鈴木さんは懸念した。", mode))
        thought = [token for token in tokens if token.dictionary_form() == "考える"]
        self.assertEqual(len(thought), 2)
        readings = {vocab._base_reading(token, "考える", analyzer, mode, {}) for token in thought}
        self.assertEqual(readings, {"かんがえる"})
        irregular = next(token for token in analyzer.tokenize("学校に来た。", mode)
                         if token.dictionary_form() == "来る")
        self.assertEqual(vocab._base_reading(irregular, "来る", analyzer, mode, {}), "くる")
        self.assertTrue(any("固有名詞" in token.part_of_speech() and token.surface() == "鈴木"
                            for token in tokens))


if __name__ == "__main__":
    unittest.main()
