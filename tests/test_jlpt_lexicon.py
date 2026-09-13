"""Offline checks for provenance, integrity and ambiguity-safe JLPT lookup."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ja_video_subtitles import jlpt_lexicon as jlpt


def payload(entries=None):
    if entries is None:
        entries = [{"lemma": "語", "reading": "ご", "level": "N2"}]
    return {
        "schema_version": 1,
        "name": "test-lexicon",
        "version": "test-v1",
        "source_url": "https://example.com/test-lexicon",
        "license": "CC0-1.0",
        "entries_sha256": jlpt.entries_sha256(entries),
        "entries": entries,
    }


class TestLexicon(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "lexicon.json"

    def write(self, data):
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return self.path

    def test_bundled_dataset_integrity_and_all_levels(self):
        lexicon = jlpt.load()
        self.assertEqual(lexicon.name, "yomitan-jlpt-vocab")
        self.assertEqual(lexicon.version, jlpt.DATA_VERSION)
        self.assertIn("b062d4e38c4bdd0950ae1d4ec55f04b176182e03", lexicon.source_url)
        self.assertEqual(lexicon.license, "CC-BY-SA-4.0")
        self.assertEqual(lexicon.entry_count, 8113)
        for lemma, reading, level in [
            ("食べる", "たべる", "N5"), ("考える", "かんがえる", "N4"),
            ("愛", "あい", "N3"), ("相変わらず", "あいかわらず", "N2"),
            ("見落とす", "みおとす", "N1"),
        ]:
            with self.subTest(lemma=lemma):
                self.assertEqual(lexicon.lookup(lemma, reading), level)
        self.assertIsNone(lexicon.lookup("存在しないテスト語", "そんざいしないてすとご"))

    def test_real_homograph_uses_reading_and_does_not_guess(self):
        lexicon = jlpt.load()
        self.assertEqual(lexicon.lookup("上手", "ジョウズ"), "N5")
        self.assertEqual(lexicon.lookup("上手", "うわて"), "N1")
        self.assertIsNone(lexicon.lookup("上手", ""))
        self.assertIsNone(lexicon.lookup("上手", "かみて"))
        self.assertEqual(lexicon.lookup("一昨日", "いっさくじつ"), "N2")
        self.assertEqual(lexicon.lookup("一昨日", "おととい"), "N5")

    def test_exact_conflict_remains_unknown_even_with_duplicate_entries(self):
        entries = [
            {"lemma": "語", "reading": "ご", "level": "N1"},
            {"lemma": "語", "reading": "ゴ", "level": "N2"},
            {"lemma": "語", "reading": "ご", "level": "N1"},
        ]
        lexicon = jlpt.load(self.write(payload(entries)))
        self.assertIsNone(lexicon.lookup("語", "ご"))
        self.assertIsNone(lexicon.lookup("語"))

    def test_same_level_with_different_readings_is_ambiguous_fallback(self):
        entries = [
            {"lemma": "明日", "reading": "あした", "level": "N5"},
            {"lemma": "明日", "reading": "あす", "level": "N5"},
        ]
        lexicon = jlpt.load(self.write(payload(entries)))
        self.assertEqual(lexicon.lookup("明日", "あす"), "N5")
        self.assertIsNone(lexicon.lookup("明日"))
        self.assertIsNone(lexicon.lookup("明日", "みょうにち"))

    def test_unique_pair_allows_lemma_fallback_and_width_normalization(self):
        entries = [{"lemma": "ゲーム", "reading": "ゲーム", "level": "N4"}] * 2
        lexicon = jlpt.load(self.write(payload(entries)))
        self.assertEqual(lexicon.lookup("ｹﾞｰﾑ", "げーむ"), "N4")
        self.assertEqual(lexicon.lookup(" ゲーム "), "N4")

    def test_explicit_unlisted_reading_never_inherits_another_sense_level(self):
        lexicon = jlpt.load()
        self.assertEqual(lexicon.lookup("生物", "せいぶつ"), "N3")
        self.assertEqual(lexicon.lookup("生物"), "N3")
        self.assertIsNone(lexicon.lookup("生物", "なまもの"))
        self.assertIsNone(lexicon.lookup("生物", "ナマモノ"))

    def test_normalize_reading(self):
        for original, expected in [
            ("カンガエル", "かんがえる"), (" ｶﾞｯﾂﾎﾟｰｽﾞ ", "がっつぽーず"),
            ("ウ\u3099ァイオリン", "ゔぁいおりん"), ("ヷヸヹヺ", "わ゙ゐ゙ゑ゙を゙"),
            ("コーヒー", "こーひー"), ("ヽヾ", "ゝゞ"), ("かな", "かな"),
        ]:
            with self.subTest(original=original):
                self.assertEqual(jlpt.normalize_reading(original), expected)

    def test_invalid_schema_and_metadata(self):
        for key, value in [
            ("schema_version", 2), ("schema_version", True), ("version", ""),
            ("name", None), ("source_url", "local-file"), ("license", 7),
            ("entries_sha256", "not-a-digest"), ("entries", None),
        ]:
            with self.subTest(key=key, value=value):
                data = payload()
                data[key] = value
                with self.assertRaises(jlpt.LexiconError):
                    jlpt.load(self.write(data))

    def test_invalid_entry_and_empty_data(self):
        for entries in [[], [None], [{"lemma": "", "reading": "ご", "level": "N2"}],
                        [{"lemma": "語", "reading": "", "level": "N2"}],
                        [{"lemma": "語", "reading": "ご", "level": "N0"}],
                        [{"lemma": "語", "reading": "ご", "level": 2}]]:
            with self.subTest(entries=entries):
                with self.assertRaises(jlpt.LexiconError):
                    jlpt.load(self.write(payload(entries)))

    def test_entry_hash_detects_tampered_level(self):
        data = payload()
        data["entries"][0]["level"] = "N1"
        with self.assertRaisesRegex(jlpt.LexiconError, "SHA-256"):
            jlpt.load(self.write(data))

    def test_default_file_pin_detects_metadata_tampering(self):
        data = payload()
        self.write(data)
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        with mock.patch.object(jlpt, "DATA_PATH", self.path), \
             mock.patch.object(jlpt, "DATA_SHA256", digest), \
             mock.patch.object(jlpt, "DATA_VERSION", "test-v1"):
            self.assertEqual(jlpt.load().version, "test-v1")
            data["version"] = "test-v2"
            self.write(data)
            with self.assertRaisesRegex(jlpt.LexiconError, "SHA-256"):
                jlpt.load()

    def test_default_version_pin(self):
        self.write(payload())
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        with mock.patch.object(jlpt, "DATA_PATH", self.path), \
             mock.patch.object(jlpt, "DATA_SHA256", digest):
            with self.assertRaisesRegex(jlpt.LexiconError, "版本"):
                jlpt.load()

    def test_missing_and_malformed_files_are_actionable(self):
        with self.assertRaisesRegex(jlpt.LexiconError, "无法读取"):
            jlpt.load(self.path)
        for raw in (b"{", b"\xff", b"[]", b"null"):
            self.path.write_bytes(raw)
            with self.assertRaises(jlpt.LexiconError):
                jlpt.load(self.path)


if __name__ == "__main__":
    unittest.main()
