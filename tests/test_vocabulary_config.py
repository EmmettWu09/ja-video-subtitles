"""Vocabulary settings and optional-dependency preflight isolation."""

import builtins
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

import ja_video_subtitles
from ja_video_subtitles import config, preflight


class TestVocabularyConfig(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory) / "config.toml"

    def write(self, text=""):
        self.path.write_text(text, encoding="utf-8")
        return config.load(self.path)

    def test_default_settings_and_existing_constructor(self):
        loaded = self.write('[deepseek]\napi_key = "test-key"\n')
        constructed = config.Config("", "", "", "", "", "", "", "8M")
        for cfg in (loaded, constructed):
            self.assertIs(cfg.vocabulary_enabled, True)
            self.assertEqual(cfg.learner_level, "N3")
            self.assertIs(cfg.include_unknown, True)
            self.assertEqual(cfg.max_examples, 3)
            self.assertEqual(cfg.vocabulary_output_dir, "")
            self.assertEqual(cfg.vocabulary_format, "both")

    def test_output_settings_and_cli_path_convention(self):
        for fmt in ("md", "json", "both"):
            cfg = self.write(f'[vocabulary]\noutput_dir = "words"\nformat = "{fmt}"\n')
            self.assertEqual(cfg.vocabulary_format, fmt)
            self.assertEqual(config.vocabulary_output_dir(cfg, Path("out")), Path("words"))
        cfg.vocabulary_output_dir = ""
        self.assertEqual(config.vocabulary_output_dir(cfg, Path("out")), Path("out"))

    def test_invalid_output_settings(self):
        for field, values in (("format", ('"csv"', '"MD"', '""', "true", "[]", "1")),
                              ("output_dir", ("true", "[]", "1", '"bad\\u0000path"'))):
            for value in values:
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(config.ConfigError, f"vocabulary.{field}"):
                        self.write(f"[vocabulary]\n{field} = {value}\n")

    def test_disabled_output_directory_is_not_resolved(self):
        cfg = self.write('[vocabulary]\nenabled = false\noutput_dir = "~/words"\n')
        with mock.patch.object(Path, "expanduser", side_effect=AssertionError("resolved")):
            self.assertEqual(config.vocabulary_output_dir(cfg, Path("out")), Path("out"))

    def test_explicit_settings_and_bounds(self):
        for level in ("N5", "N4", "N3", "N2", "N1"):
            for examples in (1, 10):
                with self.subTest(level=level, examples=examples):
                    cfg = self.write(
                        '[vocabulary]\nenabled = false\ninclude_unknown = false\n'
                        f'learner_level = "{level}"\nmax_examples = {examples}\n')
                    self.assertIs(cfg.vocabulary_enabled, False)
                    self.assertIs(cfg.include_unknown, False)
                    self.assertEqual(cfg.learner_level, level)
                    self.assertEqual(cfg.max_examples, examples)

    def test_vocabulary_requires_table(self):
        for value in ('"yes"', "true", "[]", "3"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(config.ConfigError, "must be a TOML table"):
                    self.write(f"vocabulary = {value}\n")

    def test_boolean_settings_are_strict(self):
        for field in ("enabled", "include_unknown"):
            for value in ('"true"', "1", "0", "[]"):
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(
                            config.ConfigError, rf"vocabulary.{field} .* boolean"):
                        self.write(f"[vocabulary]\n{field} = {value}\n")

    def test_level_validation_lists_legal_values(self):
        for value in ('"n3"', '"N0"', '""', "3", "true", "[]"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(config.ConfigError, "N5/N4/N3/N2/N1"):
                    self.write(f"[vocabulary]\nlearner_level = {value}\n")

    def test_max_examples_requires_bounded_integer(self):
        for value in ("0", "11", "-1", "3.0", "true", '"3"', "[]"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(config.ConfigError, "integer from 1 to 10"):
                    self.write(f"[vocabulary]\nmax_examples = {value}\n")

    def test_default_config_location_remains_project_root(self):
        self.write('[vocabulary]\nlearner_level = "N2"\n')
        with mock.patch.object(config, "PROJECT_ROOT", self.path.parent):
            self.assertEqual(config.load().learner_level, "N2")

    def test_standalone_burn_ignores_invalid_vocabulary_settings(self):
        for text in ('vocabulary = "broken"\n',
                     '[vocabulary]\nenabled = 1\nlearner_level = "bad"\n'
                     'include_unknown = 7\nmax_examples = -1\n'):
            with self.subTest(text=text):
                self.path.write_text(text + '[video]\nbitrate = "4M"\n',
                                     encoding="utf-8")
                self.assertEqual(config.load_burn(self.path).video_bitrate, "4M")


class TestVocabularyPreflight(unittest.TestCase):
    def setUp(self):
        self.cfg = config.Config(
            config.DEFAULT_BASE_URL, "test-key", config.DEFAULT_MODEL,
            "test-model", "", "", "", "8M")
        self.enterContext(mock.patch.object(preflight, "_check_runtime", return_value=[]))
        self.outputs = self.enterContext(mock.patch.object(
            preflight, "_check_output", return_value=[]))
        self.enterContext(mock.patch.object(preflight, "find_ffmpeg", return_value=Path("ffmpeg")))
        self.mp3_encoder = self.enterContext(mock.patch.object(
            preflight.audio, "has_mp3_encoder", return_value=True))
        self.enterContext(mock.patch.object(preflight.model_mod, "model_ready", return_value=True))
        self.client = mock.Mock()
        self.openai = ModuleType("openai")
        self.openai.OpenAI = mock.Mock(return_value=self.client)
        self.enterContext(mock.patch.dict("sys.modules", {"openai": self.openai}))
        self.vocabulary = ModuleType("ja_video_subtitles.vocabulary")
        self.vocabulary.check_ready = mock.Mock()
        self.enterContext(mock.patch.object(
            ja_video_subtitles, "vocabulary", self.vocabulary, create=True))
        self.enterContext(mock.patch.dict(
            "sys.modules", {"ja_video_subtitles.vocabulary": self.vocabulary}))

    def run_preflight(self, cfg=None, out_dir="out"):
        return preflight.run([], Path(out_dir), cfg or self.cfg)

    def use_config_file(self, vocabulary_settings):
        """Load real config the way the command entry does, once."""
        directory = self.enterContext(tempfile.TemporaryDirectory())
        path = Path(directory) / "config.toml"
        path.write_text('[deepseek]\napi_key = "test-key"\n'
                        '[vocabulary]\n' + vocabulary_settings, encoding="utf-8")
        return config.load(path)

    def test_enabled_checks_local_tokenizer_and_lexicon_once(self):
        cfg, ffmpeg = self.run_preflight()
        self.assertIs(cfg, self.cfg)
        self.assertEqual(ffmpeg, Path("ffmpeg"))
        self.vocabulary.check_ready.assert_called_once_with()

    def test_config_file_output_options_reach_directory_checks(self):
        cfg = self.use_config_file('output_dir = "configured-words"\nformat = "json"\n')
        self.run_preflight(cfg)
        self.assertEqual(cfg.vocabulary_format, "json")
        self.assertEqual(config.vocabulary_output_dir(cfg, Path("out")),
                         Path("configured-words"))
        self.assertEqual(self.outputs.call_args_list,
                         [mock.call([], Path("out")),
                          mock.call([], Path("configured-words"))])

    def test_merged_format_override_keeps_config_file_output_directory(self):
        cfg = self.use_config_file('output_dir = "configured-words"\nformat = "json"\n')
        cfg.vocabulary_format = "md"  # applied by the command entry, not preflight
        self.run_preflight(cfg)
        self.assertEqual(config.vocabulary_output_dir(cfg, Path("out")),
                         Path("configured-words"))
        self.outputs.assert_has_calls([mock.call([], Path("out")),
                                       mock.call([], Path("configured-words"))])

    def test_merged_directory_override_keeps_config_file_format(self):
        cfg = self.use_config_file('output_dir = "configured-words"\nformat = "json"\n')
        cfg.vocabulary_output_dir = "cli-words"
        self.run_preflight(cfg)
        self.assertEqual(cfg.vocabulary_format, "json")
        self.assertEqual(config.vocabulary_output_dir(cfg, Path("out")),
                         Path("cli-words"))
        self.assertEqual(self.outputs.call_args_list,
                         [mock.call([], Path("out")), mock.call([], Path("cli-words"))])

    def test_missing_config_output_keys_default_to_both_in_video_output_directory(self):
        cfg = self.use_config_file('learner_level = "N2"\n')
        self.run_preflight(cfg, "custom-video-output")
        self.assertEqual(cfg.vocabulary_format, "both")
        self.assertEqual(config.vocabulary_output_dir(cfg, Path("custom-video-output")),
                         Path("custom-video-output"))
        self.outputs.assert_called_once_with([], Path("custom-video-output"))

    def test_merged_output_options_apply_before_directory_checks(self):
        self.cfg.vocabulary_output_dir = "cli-words"
        self.cfg.vocabulary_format = "md"
        with mock.patch.object(preflight, "_check_output", return_value=[]) as outputs:
            self.run_preflight()
        self.assertEqual(outputs.call_args_list,
                         [mock.call([], Path("out")), mock.call([], Path("cli-words"))])

    def test_disabled_vocabulary_does_not_check_custom_directory(self):
        self.cfg.vocabulary_enabled = False
        self.cfg.vocabulary_output_dir = "unwritable"
        with mock.patch.object(preflight, "_check_output", return_value=[]) as outputs:
            self.run_preflight()
        outputs.assert_called_once_with([], Path("out"))

    def test_bad_custom_directory_fails_before_processing(self):
        self.cfg.vocabulary_output_dir = "bad-dir"
        with mock.patch.object(preflight, "_check_output",
                               side_effect=[[], ["output directory bad-dir is not writable"]]):
            with self.assertRaisesRegex(preflight.PreflightError, "bad-dir is not writable"):
                self.run_preflight()

    def test_unresolvable_directory_is_a_preflight_error(self):
        self.cfg.vocabulary_output_dir = "~/words"
        with mock.patch.object(Path, "expanduser", side_effect=RuntimeError("unknown home")):
            with self.assertRaisesRegex(preflight.PreflightError, "cannot resolve vocabulary"):
                self.run_preflight()

    def test_missing_mp3_encoder_has_repair_guidance(self):
        self.mp3_encoder.return_value = False
        with self.assertRaisesRegex(preflight.PreflightError, "libmp3lame MP3 encoder"):
            self.run_preflight()

    def test_disabled_never_imports_vocabulary_dependencies(self):
        self.cfg.vocabulary_enabled = False
        real_import = builtins.__import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            forbidden = {"vocabulary", "jlpt_lexicon", "sudachipy", "sudachidict_core"}
            if name.split(".")[-1] in forbidden or forbidden.intersection(fromlist):
                raise AssertionError(f"optional dependency imported: {name} {fromlist}")
            return real_import(name, globals, locals, fromlist, level)

        with mock.patch("builtins.__import__", side_effect=guarded_import):
            self.run_preflight()
        self.vocabulary.check_ready.assert_not_called()

    def test_missing_or_corrupt_resources_have_repair_guidance(self):
        for error in (ImportError("SudachiPy missing"),
                      RuntimeError("Sudachi dictionary damaged"),
                      ValueError("JLPT data hash mismatch")):
            with self.subTest(error=error):
                self.vocabulary.check_ready.side_effect = error
                with self.assertRaises(preflight.PreflightError) as raised:
                    self.run_preflight()
                text = str(raised.exception)
                self.assertIn(str(error), text)
                self.assertIn("uv pip install --python .venv/bin/python", text)
                self.assertIn("restore the bundled JLPT data", text)
                self.assertIn("vocabulary.enabled = false", text)

    def test_burn_ignores_vocabulary_even_when_enabled(self):
        self.vocabulary.check_ready.side_effect = AssertionError("unexpected vocabulary check")
        with mock.patch.object(preflight, "find_ffprobe", return_value=Path("ffprobe")):
            preflight.run_burn([], Path("out"), config.BurnConfig("", "8M"))
        self.vocabulary.check_ready.assert_not_called()
        self.openai.OpenAI.assert_not_called()
        self.mp3_encoder.assert_not_called()

    def test_connectivity_uses_non_thinking_options_for_deepseek(self):
        self.run_preflight()
        kwargs = self.client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["extra_body"], {"thinking": {"type": "disabled"}})

    def test_connectivity_error_does_not_expose_key(self):
        self.client.chat.completions.create.side_effect = RuntimeError(
            f"Rejected credential {self.cfg.api_key}")
        with self.assertRaises(preflight.PreflightError) as raised:
            self.run_preflight()
        self.assertIn("connectivity check failed", str(raised.exception))
        self.assertNotIn(self.cfg.api_key, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
