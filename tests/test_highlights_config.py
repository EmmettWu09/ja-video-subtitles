"""Offline [highlights] config validation: defaults, strictness, burn isolation."""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ja_video_subtitles import cli, config


def invoke(*arguments):
    stdout, stderr = io.StringIO(), io.StringIO()
    argv = ["ja-video-subtitles", *map(str, arguments)]
    with mock.patch("sys.argv", argv), redirect_stdout(stdout), \
            redirect_stderr(stderr), unittest.TestCase().assertRaises(SystemExit) as result:
        cli.main()
    return result.exception.code, stdout.getvalue(), stderr.getvalue()


class TestHighlightsConfig(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory) / "config.toml"

    def load(self, text=""):
        self.path.write_text(text, encoding="utf-8")
        return config.load(self.path)

    def load_burn(self, text=""):
        self.path.write_text(text, encoding="utf-8")
        return config.load_burn(self.path)

    def test_defaults_without_section(self):
        cfg = self.load('[deepseek]\napi_key = "k"\n')
        self.assertIs(cfg.highlights_enabled, False)
        self.assertEqual(cfg.highlights_target_seconds, 240)
        self.assertEqual(cfg.highlights_intro_start_seconds, 0)
        self.assertEqual(cfg.highlights_ja_voice, "Kyoko")
        self.assertEqual(cfg.highlights_zh_voice, "Tingting")
        self.assertIs(cfg.highlights_keep_artifacts, False)

    def test_explicit_values(self):
        cfg = self.load('[highlights]\nenabled = false\ntarget_seconds = 300\n'
                        'intro_start_seconds = 20\nja_voice = "Otoya"\n'
                        'zh_voice = "Meijia"\nkeep_artifacts = true\n')
        self.assertIs(cfg.highlights_enabled, False)
        self.assertEqual(cfg.highlights_target_seconds, 300)
        self.assertEqual(cfg.highlights_intro_start_seconds, 20)
        self.assertEqual(cfg.highlights_ja_voice, "Otoya")
        self.assertEqual(cfg.highlights_zh_voice, "Meijia")
        self.assertIs(cfg.highlights_keep_artifacts, True)

    def test_intro_accepts_float(self):
        cfg = self.load('[highlights]\nintro_start_seconds = 1.5\n')
        self.assertEqual(cfg.highlights_intro_start_seconds, 1.5)

    def test_section_must_be_a_table(self):
        for value in ('"invalid"', "true", "[]", "3"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                        config.ConfigError, "highlights .* must be a TOML table"):
                    self.load(f"highlights = {value}\n")

    def test_enabled_must_be_boolean(self):
        for value in ('"true"', "1", "0", "[]"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                        config.ConfigError,
                        "highlights.enabled .* must be a boolean"):
                    self.load(f"[highlights]\nenabled = {value}\n")

    def test_keep_artifacts_must_be_boolean(self):
        for value in ('"true"', "1", "0", "[]"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                        config.ConfigError,
                        "highlights.keep_artifacts .* must be a boolean"):
                    self.load(f"[highlights]\nkeep_artifacts = {value}\n")

    def test_target_seconds_range_and_type(self):
        for value in ("59", "901", '"240"', "true", "1.5", "[]"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                        config.ConfigError,
                        "highlights.target_seconds .* integer from 60 to 900"):
                    self.load(f"[highlights]\ntarget_seconds = {value}\n")
        for value in ("60", "900"):
            cfg = self.load(f"[highlights]\ntarget_seconds = {value}\n")
            self.assertEqual(cfg.highlights_target_seconds, int(value))

    def test_intro_start_must_be_nonnegative_number(self):
        for value in ("-1", "-0.5", "true", '"20"', "[]"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                        config.ConfigError,
                        "highlights.intro_start_seconds .* number >= 0"):
                    self.load(f"[highlights]\nintro_start_seconds = {value}\n")

    def test_voices_must_be_nonempty_strings(self):
        for field in ("ja_voice", "zh_voice"):
            for value in ('""', '"   "', '"bad\\u0000voice"', "3", "true", "[]"):
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(
                            config.ConfigError,
                            rf"highlights\.{field} .* nonempty voice name"):
                        self.load(f"[highlights]\n{field} = {value}\n")

    def test_burn_ignores_highlights_section(self):
        cfg = self.load_burn('highlights = "broken"\n')
        self.assertIs(cfg.yes, False)
        cfg = self.load_burn('[highlights]\nenabled = "yes"\n'
                             'target_seconds = "240"\nja_voice = ""\n')
        self.assertIs(cfg.yes, False)


class TestInvalidHighlightsConfigNotMaskedByCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config_path = self.root / "config.toml"
        patcher = mock.patch("ja_video_subtitles.cli.load",
                             side_effect=lambda: config.load(self.config_path))
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_invalid_highlights_config_fails_even_with_cli_switch(self):
        video = self.root / "a.mp4"
        video.write_bytes(b"video")
        cases = ('[highlights]\ntarget_seconds = "240"\n',
                 '[highlights]\nja_voice = ""\n',
                 '[highlights]\nenabled = 1\n',
                 'highlights = "invalid"\n')
        for text in cases:
            with self.subTest(text=text):
                self.config_path.write_text(text, encoding="utf-8")
                code, _, stderr = invoke("run", video, "-o", self.root / "out",
                                         "--highlights")
                self.assertEqual(code, 2)
                self.assertIn("highlights", stderr)


if __name__ == "__main__":
    unittest.main()
