"""Standalone burning must remain usable without ASR or API setup."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ja_video_subtitles import config, preflight


class TestBurnConfig(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory) / "config.toml"

    def test_missing_config_uses_burn_defaults(self):
        cfg = config.load_burn(self.path)
        self.assertEqual(cfg, config.BurnConfig(
            config.DEFAULT_FORCE_STYLE, config.DEFAULT_VIDEO_BITRATE))
        self.assertFalse(self.path.exists())

    def test_only_burn_sections_are_read(self):
        self.path.write_text(
            'deepseek = "unused"\nasr = 123\nprompt = false\n'
            '[style]\nforce_style = "FontSize=28"\n'
            '[video]\nbitrate = "4.5M"\n', encoding="utf-8")
        self.assertEqual(config.load_burn(self.path),
                         config.BurnConfig("FontSize=28", "4.5M"))

    def test_empty_style_allows_ffmpeg_defaults(self):
        self.path.write_text('[style]\nforce_style = ""\n', encoding="utf-8")
        self.assertEqual(config.load_burn(self.path).force_style, "")

    def test_bitrate_formats(self):
        for bitrate in ("8M", "8000k", "8000000", "0.5M"):
            with self.subTest(bitrate=bitrate):
                self.path.write_text(f'[video]\nbitrate = "{bitrate}"\n',
                                     encoding="utf-8")
                self.assertEqual(config.load_burn(self.path).video_bitrate,
                                 bitrate)

    def test_malformed_toml_is_clear(self):
        self.path.write_text("[style", encoding="utf-8")
        with self.assertRaisesRegex(config.ConfigError, "invalid TOML"):
            config.load_burn(self.path)

    def test_invalid_burn_values_are_clear(self):
        cases = (
            ('style = "bad"', "style .* must be a TOML table"),
            ('video = []', "video .* must be a TOML table"),
            ('[style]\nforce_style = 20', "style.force_style .* must be a string"),
            ('[video]\nbitrate = 8000000', "video.bitrate .* positive bitrate"),
            ('[video]\nbitrate = ""', "video.bitrate .* positive bitrate"),
            ('[video]\nbitrate = "0M"', "video.bitrate .* positive bitrate"),
            ('[video]\nbitrate = "-2M"', "video.bitrate .* positive bitrate"),
            ('[video]\nbitrate = "fast"', "video.bitrate .* positive bitrate"),
        )
        for text, message in cases:
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(config.ConfigError, message):
                    config.load_burn(self.path)


class TestBurnPreflight(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(directory)
        self.video = self.root / "video.mp4"
        self.video.write_bytes(b"video")
        self.out = self.root / "nested" / "out"
        self.enterContext(mock.patch.object(config, "PROJECT_ROOT", self.root))
        self.enterContext(mock.patch.object(preflight.sys, "platform", "darwin"))
        self.enterContext(mock.patch.object(preflight.sys, "version_info", (3, 12)))
        self.import_module = self.enterContext(mock.patch.object(
            preflight.importlib, "import_module", side_effect=self.local_import))
        self.ffmpeg = Path("/test/ffmpeg")
        self.find_ffmpeg = self.enterContext(mock.patch.object(
            preflight, "find_ffmpeg", return_value=self.ffmpeg))
        self.find_ffprobe = self.enterContext(mock.patch.object(
            preflight, "find_ffprobe", return_value=Path("/test/ffprobe")))
        self.disk_usage = self.enterContext(mock.patch.object(
            preflight.shutil, "disk_usage", return_value=SimpleNamespace(free=1024)))
        self.api_key_valid = self.enterContext(mock.patch.object(
            preflight, "api_key_valid", side_effect=AssertionError("API key checked")))
        self.model_ready = self.enterContext(mock.patch.object(
            preflight.model_mod, "model_ready",
            side_effect=AssertionError("ASR model checked")))

    def load_cfg(self):
        return config.load_burn(self.root / "config.toml")

    def run_burn(self, videos=None):
        return preflight.run_burn(
            [self.video] if videos is None else videos, self.out, self.load_cfg())

    @staticmethod
    def local_import(name):
        if name in ("srt", "tqdm"):
            return object()
        raise AssertionError(f"unexpected dependency import: {name}")

    def test_defaults_need_only_local_dependencies(self):
        cfg, ffmpeg = self.run_burn()
        self.assertEqual(cfg, config.BurnConfig(
            config.DEFAULT_FORCE_STYLE, config.DEFAULT_VIDEO_BITRATE))
        self.assertEqual(ffmpeg, self.ffmpeg)
        self.assertTrue(self.out.is_dir())
        self.assertEqual(self.import_module.call_args_list,
                         [mock.call("srt"), mock.call("tqdm")])
        self.api_key_valid.assert_not_called()
        self.model_ready.assert_not_called()

    def test_preflight_never_reloads_the_config_file(self):
        cfg = self.load_cfg()
        with mock.patch.object(config, "load_burn",
                               side_effect=AssertionError("reloaded")), \
                mock.patch.object(config, "load",
                                  side_effect=AssertionError("reloaded")):
            result, _ = preflight.run_burn([self.video], self.out, cfg)
        self.assertIs(result, cfg)

    def test_placeholder_api_key_and_missing_model_do_not_block(self):
        (self.root / "config.toml").write_text(
            '[deepseek]\napi_key = "your-api-key"\n'
            '[asr]\nmodel_id = "not-downloaded"\n'
            '[video]\nbitrate = "3M"\n', encoding="utf-8")
        cfg, _ = self.run_burn()
        self.assertEqual(cfg.video_bitrate, "3M")
        self.api_key_valid.assert_not_called()
        self.model_ready.assert_not_called()

    def test_output_probe_preserves_existing_user_file(self):
        self.out.mkdir(parents=True)
        probe = self.out / ".write_probe"
        probe.write_text("keep me", encoding="utf-8")
        self.run_burn()
        self.assertEqual(probe.read_text(encoding="utf-8"), "keep me")
        self.assertEqual(list(self.out.iterdir()), [probe])

    def test_disk_requirement_includes_all_inputs(self):
        second = self.root / "second.mov"
        second.write_bytes(b"video")
        self.disk_usage.return_value.free = 15
        with self.assertRaisesRegex(preflight.PreflightError, "insufficient disk space"):
            self.run_burn([self.video, second])

    def test_local_prerequisite_errors_are_reported_together(self):
        self.find_ffmpeg.return_value = None
        self.import_module.side_effect = ImportError("missing")
        with mock.patch.object(preflight.sys, "platform", "linux"), \
                mock.patch.object(preflight.sys, "version_info", (3, 11)):
            with self.assertRaises(preflight.PreflightError) as raised:
                self.run_burn()
        message = str(raised.exception)
        self.assertIn("macOS only", message)
        self.assertIn("Python >= 3.12", message)
        self.assertIn("missing packages: srt, tqdm", message)
        self.assertIn("no ffmpeg with the subtitles filter", message)

    def test_broken_config_fails_before_preflight(self):
        (self.root / "config.toml").write_text("[video", encoding="utf-8")
        with self.assertRaisesRegex(config.ConfigError, "invalid TOML"):
            self.load_cfg()

    def test_missing_ffprobe_is_a_preflight_error(self):
        self.find_ffprobe.return_value = None
        with self.assertRaisesRegex(preflight.PreflightError, "no ffprobe found"):
            self.run_burn()
        self.find_ffprobe.assert_called_once_with(self.ffmpeg)

    def test_unwritable_output_is_a_preflight_error(self):
        with mock.patch.object(preflight.tempfile, "TemporaryFile",
                               side_effect=PermissionError("blocked")):
            with self.assertRaisesRegex(preflight.PreflightError, "is not writable"):
                self.run_burn()


if __name__ == "__main__":
    unittest.main()
