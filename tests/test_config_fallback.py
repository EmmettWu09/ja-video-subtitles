"""Offline config-fallback tests: CLI > config.toml > built-in defaults.

No encoder, ASR model, or API calls; heavy stages are mocked.
"""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ja_video_subtitles import cli, config

SRT = "1\n00:00:00,000 --> 00:00:01,000\n日本語\n中文字幕\n\n"


def invoke(*arguments):
    stdout, stderr = io.StringIO(), io.StringIO()
    argv = ["ja-video-subtitles", *map(str, arguments)]
    with mock.patch("sys.argv", argv), redirect_stdout(stdout), \
            redirect_stderr(stderr), unittest.TestCase().assertRaises(SystemExit) as result:
        cli.main()
    return result.exception.code, stdout.getvalue(), stderr.getvalue()


class TestConfigSections(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory) / "config.toml"

    def load(self, text=""):
        self.path.write_text(text, encoding="utf-8")
        return config.load(self.path)

    def load_burn(self, text=""):
        self.path.write_text(text, encoding="utf-8")
        return config.load_burn(self.path)

    def test_run_section_mapping(self):
        cfg = self.load('[run]\ninput = "videos"\noutput_dir = "out"\n'
                        'force = true\nyes = true\n')
        self.assertEqual(cfg.run_input, "videos")
        self.assertEqual(cfg.run_output_dir, "out")
        self.assertIs(cfg.run_force, True)
        self.assertIs(cfg.run_yes, True)

    def test_burn_section_mapping(self):
        cfg = self.load_burn('[burn]\ninputs = ["a.mp4", "b.mov"]\n'
                             'output_dir = "burned"\nsubtitles = "edited.srt"\n'
                             'yes = true\n')
        self.assertEqual(cfg.inputs, ["a.mp4", "b.mov"])
        self.assertEqual(cfg.output_dir, "burned")
        self.assertEqual(cfg.subtitles, "edited.srt")
        self.assertEqual(cfg.subtitle_dir, "")
        self.assertIs(cfg.yes, True)

    def test_legacy_config_without_new_sections_keeps_defaults(self):
        cfg = self.load('[deepseek]\napi_key = "k"\n')
        self.assertIsNone(cfg.run_input)
        self.assertIsNone(cfg.run_output_dir)
        self.assertIs(cfg.run_force, False)
        self.assertIs(cfg.run_yes, False)
        burn = config.load_burn(self.path)
        self.assertIsNone(burn.inputs)
        self.assertIsNone(burn.output_dir)
        self.assertEqual(burn.subtitles, "")
        self.assertEqual(burn.subtitle_dir, "")
        self.assertIs(burn.yes, False)

    def test_command_sections_must_be_tables(self):
        for loader, name in ((self.load, "run"), (self.load_burn, "burn")):
            for value in ('"invalid"', "true", "[]", "3"):
                with self.subTest(name=name, value=value):
                    with self.assertRaisesRegex(
                            config.ConfigError, rf"{name} .* must be a TOML table"):
                        loader(f"{name} = {value}\n")

    def test_boolean_switches_are_strict(self):
        cases = ((self.load, "run", "force"), (self.load, "run", "yes"),
                 (self.load_burn, "burn", "yes"))
        for loader, section, field in cases:
            for value in ('"true"', "1", "0", "[]"):
                with self.subTest(section=section, field=field, value=value):
                    with self.assertRaisesRegex(
                            config.ConfigError,
                            rf"{section}\.{field} .* must be a boolean"):
                        loader(f"[{section}]\n{field} = {value}\n")

    def test_main_paths_must_be_nonempty_path_strings(self):
        cases = ((self.load, "run", "input"), (self.load, "run", "output_dir"),
                 (self.load_burn, "burn", "output_dir"))
        for loader, section, field in cases:
            for value in ('""', '"   "', '"bad\\u0000path"', "true", "[]", "3"):
                with self.subTest(section=section, field=field, value=value):
                    with self.assertRaisesRegex(
                            config.ConfigError,
                            rf"{section}\.{field} .* nonempty path string"):
                        loader(f"[{section}]\n{field} = {value}\n")

    def test_burn_inputs_element_strictness(self):
        for value in ('"a.mp4"', "[]", '["a.mp4", 3]', '["a.mp4", true]',
                      '[""]', '["  "]', '["bad\\u0000path"]', "3", "true"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(config.ConfigError, "burn.inputs"):
                    self.load_burn(f"[burn]\ninputs = {value}\n")

    def test_optional_paths_allow_only_exact_empty_string(self):
        cases = ((self.load_burn, "burn", "subtitles"),
                 (self.load_burn, "burn", "subtitle_dir"),
                 (self.load, "vocabulary", "output_dir"))
        for loader, section, field in cases:
            for value in ('" "', '"\t"', '"bad\\u0000path"', "true", "[]", "3"):
                with self.subTest(section=section, field=field, value=value):
                    with self.assertRaisesRegex(
                            config.ConfigError, rf"{section}\.{field}"):
                        loader(f"[{section}]\n{field} = {value}\n")

    def test_run_ignores_burn_section(self):
        cfg = self.load('burn = "broken"\n[run]\ninput = "videos"\n')
        self.assertEqual(cfg.run_input, "videos")
        cfg = self.load('[burn]\ninputs = "not-a-list"\nyes = 1\n')
        self.assertIsNone(cfg.run_input)

    def test_burn_ignores_pipeline_sections(self):
        cfg = self.load_burn(
            'run = "broken"\ndeepseek = 123\nasr = false\nprompt = []\n'
            'vocabulary = "broken"\n[burn]\nyes = true\n')
        self.assertIs(cfg.yes, True)

    def test_toml_syntax_error_fails_both_commands(self):
        self.path.write_text("[run", encoding="utf-8")
        for loader in (config.load, config.load_burn):
            with self.subTest(loader=loader.__name__):
                with self.assertRaisesRegex(config.ConfigError, "invalid TOML"):
                    loader(self.path)

    def test_unreadable_config_is_a_config_error(self):
        self.path.mkdir()  # a directory cannot be read as a TOML file
        for loader in (config.load, config.load_burn):
            with self.subTest(loader=loader.__name__):
                with self.assertRaisesRegex(config.ConfigError, "cannot read"):
                    loader(self.path)
        self.path.rmdir()
        self.path.write_bytes(b"\xff\xfe")  # not valid UTF-8
        for loader in (config.load, config.load_burn):
            with self.subTest(loader=loader.__name__, kind="utf-8"):
                with self.assertRaisesRegex(config.ConfigError, "cannot read"):
                    loader(self.path)

    def test_example_template_parses_with_safe_defaults(self):
        from ja_video_subtitles import PROJECT_ROOT
        template = PROJECT_ROOT / "config.example.toml"
        cfg = config.load(template)
        self.assertIs(cfg.run_force, False)
        self.assertIs(cfg.run_yes, False)
        self.assertIsNone(cfg.run_input)
        burn = config.load_burn(template)
        self.assertIsNone(burn.inputs)
        self.assertEqual(burn.subtitles, "")
        self.assertEqual(burn.subtitle_dir, "")
        self.assertIs(burn.yes, False)


class TestRunFallback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config_path = self.root / "config.toml"
        self.ffmpeg = Path("/mock/ffmpeg")

        def preflight(videos, out_dir, cfg):
            out_dir.mkdir(parents=True, exist_ok=True)
            return cfg, self.ffmpeg

        self.preflight = self.patch("ja_video_subtitles.cli.preflight.run",
                                    side_effect=preflight)
        self.process = self.patch("ja_video_subtitles.cli.process_video")
        self.patch("ja_video_subtitles.cli.preflight.run_burn",
                   side_effect=AssertionError("burn preflight used"))
        self.load = self.patch("ja_video_subtitles.cli.load",
                               side_effect=lambda: config.load(self.config_path))

    def patch(self, target, **kwargs):
        patcher = mock.patch(target, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def write_config(self, text):
        self.config_path.write_text(text, encoding="utf-8")

    def video(self, name="a.mp4", directory=None):
        path = (directory or self.root) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"original video")
        return path

    def run(self, *arguments):
        return invoke("run", *arguments)

    def test_config_only_run_uses_all_mapped_options(self):
        video = self.video()
        out = self.root / "media"
        out.mkdir()
        (out / "a.sub.mp4").write_bytes(b"old output")
        self.write_config(f'[run]\ninput = "{video}"\noutput_dir = "{out}"\n'
                          'force = true\nyes = true\n')
        with mock.patch("builtins.input", side_effect=AssertionError("prompted")):
            code, _, stderr = self.run()
        self.assertEqual((code, stderr), (0, ""))
        videos, out_dir, cfg = self.preflight.call_args.args
        self.assertEqual(videos, [video])
        self.assertEqual(out_dir, out)
        self.assertIs(cfg.run_force, True)
        self.assertEqual(self.process.call_args.args[2].run_yes, True)
        self.assertEqual(self.process.call_args.args[4], True)
        self.assertEqual((out / "a.sub.mp4").read_bytes(), b"old output")

    def test_cli_overrides_only_the_given_fields(self):
        video, cli_video = self.video("saved.mp4"), self.video("cli.mp4")
        cli_out = self.root / "cli-out"
        self.write_config(f'[run]\ninput = "{video}"\noutput_dir = "saved-out"\n'
                          'force = true\nyes = true\n'
                          '[vocabulary]\noutput_dir = "words"\nformat = "json"\n')
        code, _, _ = self.run(cli_video, "-o", cli_out, "--vocab-format", "md")
        self.assertEqual(code, 0)
        videos, out_dir, cfg = self.preflight.call_args.args
        self.assertEqual((videos, out_dir), ([cli_video], cli_out))
        self.assertEqual(cfg.vocabulary_format, "md")
        self.assertEqual(cfg.vocabulary_output_dir, "words")
        self.assertIs(cfg.run_force, True)
        self.assertIs(cfg.run_yes, True)
        self.assertFalse((self.root / "saved-out").exists())

    def test_mixed_sources_fill_required_options(self):
        video = self.video()
        out = self.root / "out"
        self.write_config(f'[run]\ninput = "{video}"\n')
        self.assertEqual(self.run("-o", out)[0], 0)
        self.assertEqual(self.preflight.call_args.args[:2], ([video], out))

    def test_missing_output_after_merge_is_an_error_without_side_effects(self):
        video = self.video()
        self.write_config(f'[run]\ninput = "{video}"\n')
        code, _, stderr = self.run()
        self.assertEqual(code, 2)
        self.assertIn("-o/--output-dir", stderr)
        self.assertIn("run.output_dir", stderr)
        self.preflight.assert_not_called()
        self.process.assert_not_called()
        self.assertEqual(list(self.root.iterdir()),
                         [self.config_path, self.root / "a.mp4"])

    def test_missing_input_after_merge_is_an_error(self):
        self.write_config('[run]\noutput_dir = "out"\n')
        code, _, stderr = self.run("-o", self.root / "cli-out")
        self.assertEqual(code, 2)
        self.assertIn("input", stderr)
        self.assertIn("run.input", stderr)
        self.preflight.assert_not_called()
        self.assertFalse((self.root / "out").exists())
        self.assertFalse((self.root / "cli-out").exists())

    def test_boolean_tri_state_merge(self):
        video = self.video()
        out = self.root / "out"
        out.mkdir()
        (out / "a.sub.mp4").write_bytes(b"old output")
        self.write_config(f'[run]\ninput = "{video}"\noutput_dir = "{out}"\n'
                          'force = true\nyes = true\n')
        with mock.patch("builtins.input", return_value="n") as prompt:
            code, _, _ = self.run("--no-force", "--no-yes")
        self.assertEqual(code, 0)
        prompt.assert_called_once()
        self.process.assert_not_called()
        self.assertIn("skipped", (out / "run.log").read_text(encoding="utf-8"))

    def test_no_yes_does_not_cancel_force_and_vice_versa(self):
        video = self.video()
        out = self.root / "out"
        out.mkdir()
        (out / "a.sub.mp4").write_bytes(b"old output")
        self.write_config(f'[run]\ninput = "{video}"\noutput_dir = "{out}"\n'
                          'force = true\nyes = true\n')
        for options, expected_force in ((("--no-yes",), True),
                                        (("--no-force",), False)):
            with self.subTest(options=options):
                self.process.reset_mock()
                with mock.patch("builtins.input",
                                side_effect=AssertionError("prompted")):
                    code, _, _ = self.run(*options)
                self.assertEqual(code, 0)
                self.assertEqual(self.process.call_args.args[4], expected_force)

    def test_explicit_switches_beat_configured_false(self):
        video = self.video()
        out = self.root / "out"
        out.mkdir()
        (out / "a.sub.mp4").write_bytes(b"old output")
        self.write_config(f'[run]\ninput = "{video}"\noutput_dir = "{out}"\n'
                          'force = false\nyes = false\n')
        with mock.patch("builtins.input", side_effect=AssertionError("prompted")):
            code, _, _ = self.run("--force", "-y")
        self.assertEqual(code, 0)
        self.assertEqual(self.process.call_args.args[4], True)

    def test_conflicting_boolean_switches_are_rejected(self):
        video = self.video()
        self.write_config("")
        for options in (("--force", "--no-force"), ("--no-force", "--force"),
                        ("-y", "--no-yes"), ("--yes", "--no-yes")):
            with self.subTest(options=options):
                code, _, stderr = self.run(video, "-o", self.root / "out", *options)
                self.assertEqual(code, 2)
        self.load.assert_not_called()
        self.process.assert_not_called()

    def test_explicit_blank_and_nul_paths_are_rejected(self):
        video = self.video()
        self.write_config(f'[run]\ninput = "{video}"\noutput_dir = "saved"\n')
        for bad in ("", "   ", "bad\x00path"):
            with self.subTest(bad=bad):
                code, _, _ = self.run(video, "-o", bad)
                self.assertEqual(code, 2)
                code, _, _ = self.run(bad, "-o", self.root / "out")
                self.assertEqual(code, 2)
        self.preflight.assert_not_called()
        self.assertFalse((self.root / "saved").exists())

    def test_invalid_config_values_are_not_masked_by_cli(self):
        video = self.video()
        cases = ('[run]\nforce = "true"\n',
                 '[vocabulary]\nformat = "csv"\n',
                 'run = "invalid"\n')
        for text in cases:
            with self.subTest(text=text):
                self.write_config(text)
                code, _, stderr = self.run(video, "-o", self.root / "out",
                                           "--no-force", "--vocab-format", "md")
                self.assertEqual(code, 2)
        self.preflight.assert_not_called()
        self.process.assert_not_called()

    def test_run_requires_a_config_file_even_with_full_cli(self):
        video = self.video()
        code, _, stderr = self.run(video, "-o", self.root / "out", "--force", "-y")
        self.assertEqual(code, 2)
        self.assertIn("config file", stderr)
        self.preflight.assert_not_called()
        self.assertFalse((self.root / "out").exists())

    def test_unreadable_config_exits_two_without_a_traceback(self):
        self.config_path.mkdir()  # read_text raises IsADirectoryError
        video = self.video()
        code, _, stderr = self.run(video, "-o", self.root / "out")
        self.assertEqual(code, 2)
        self.assertIn("cannot read config file", stderr)
        self.assertNotIn("Traceback", stderr)
        self.preflight.assert_not_called()
        self.assertFalse((self.root / "out").exists())

    def test_broken_toml_fails_run(self):
        video = self.video()
        self.write_config("[run")
        code, _, stderr = self.run(video, "-o", self.root / "out")
        self.assertEqual(code, 2)
        self.assertIn("invalid TOML", stderr)
        self.preflight.assert_not_called()

    def test_run_ignores_invalid_burn_section(self):
        video = self.video()
        self.write_config(f'[burn]\ninputs = "not-a-list"\nyes = 1\n'
                          f'[run]\ninput = "{video}"\noutput_dir = "out"\n')
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(self.root)
        code, _, stderr = self.run()
        self.assertEqual((code, stderr), (0, ""))

    def test_replaced_config_paths_are_not_checked_or_created(self):
        video = self.video()
        out = self.root / "real-out"
        self.write_config('[run]\ninput = "ghost/missing.mp4"\n'
                          'output_dir = "ghost-out"\n')
        code, _, stderr = self.run(video, "-o", out)
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(self.preflight.call_args.args[:2], ([video], out))
        self.assertFalse((self.root / "ghost-out").exists())

    def test_explicit_cli_input_never_falls_back_to_config(self):
        self.video("saved.mp4")
        self.write_config(f'[run]\ninput = "{self.root / "saved.mp4"}"\n'
                          'output_dir = "out"\n')
        code, _, stderr = self.run(self.root / "missing.mp4", "-o",
                                   self.root / "out")
        self.assertEqual(code, 2)
        self.assertIn("input path does not exist", stderr)
        self.preflight.assert_not_called()

    def test_tilde_expansion_for_cli_and_config_paths(self):
        home = self.root / "home"
        video = self.video("a.mp4", home / "vids")
        out = home / "out"
        self.write_config('[run]\ninput = "~/vids/a.mp4"\noutput_dir = "~/out"\n')

        def expanduser(path):
            text = str(path)
            if text == "~":
                return home
            if text.startswith("~/"):
                return home / text[2:]
            return path

        with mock.patch.object(Path, "expanduser", expanduser):
            code, _, stderr = self.run()
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(self.preflight.call_args.args[:2], ([video], out))

    def test_relative_config_paths_use_the_caller_cwd(self):
        video = self.video("a.mp4", self.root / "videos")
        self.write_config('[run]\ninput = "videos/a.mp4"\noutput_dir = "out"\n')
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(self.root)
        code, _, stderr = self.run()
        self.assertEqual((code, stderr), (0, ""))
        videos, out_dir, _ = self.preflight.call_args.args
        self.assertEqual(videos, [Path("videos/a.mp4")])
        self.assertEqual(out_dir, Path("out"))

    def test_vocabulary_defaults_follow_the_final_output_dir(self):
        video = self.video()
        cli_out = self.root / "cli-media"
        self.write_config(f'[run]\ninput = "{video}"\noutput_dir = "saved-media"\n'
                          '[vocabulary]\noutput_dir = ""\n')
        code, _, _ = self.run("-o", cli_out)
        self.assertEqual(code, 0)
        videos, out_dir, cfg = self.preflight.call_args.args
        self.assertEqual(out_dir, cli_out)
        self.assertEqual(config.vocabulary_output_dir(cfg, out_dir), cli_out)
        self.assertFalse((self.root / "saved-media").exists())

    def test_config_paths_with_spaces_and_cjk(self):
        video = self.video("日语 视频.mp4", self.root / "输入 目录")
        out = self.root / "输出 目录"
        self.write_config(f'[run]\ninput = "{video}"\noutput_dir = "{out}"\n')
        code, _, stderr = self.run()
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(self.preflight.call_args.args[:2], ([video], out))

    def test_config_switches_cannot_bypass_target_protection(self):
        video = self.video()
        out = self.root / "out"
        out.mkdir()
        (out / "a.sub.mp4").symlink_to(video)
        self.write_config(f'[run]\ninput = "{video}"\noutput_dir = "{out}"\n'
                          'force = true\nyes = true\n')
        code, _, stderr = self.run()
        self.assertEqual(code, 2)
        self.assertIn("would overwrite", stderr)
        self.assertEqual(video.read_bytes(), b"original video")
        self.process.assert_not_called()


class TestBurnFallback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config_path = self.root / "config.toml"
        self.ffmpeg = Path("/mock/ffmpeg")

        def preflight(videos, out_dir, cfg):
            out_dir.mkdir(parents=True, exist_ok=True)
            return cfg, self.ffmpeg

        self.preflight = self.patch("ja_video_subtitles.cli.preflight.run_burn",
                                    side_effect=preflight)
        self.encoder = self.patch("ja_video_subtitles.cli.burn_mod.burn",
                                  side_effect=self.encode)
        self.patch("ja_video_subtitles.cli.preflight.run",
                   side_effect=AssertionError("run preflight used"))
        self.load_burn = self.patch(
            "ja_video_subtitles.cli.load_burn",
            side_effect=lambda: config.load_burn(self.config_path))

    def patch(self, target, **kwargs):
        patcher = mock.patch(target, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def write_config(self, text):
        self.config_path.write_text(text, encoding="utf-8")

    def video(self, name="a.mp4", directory=None):
        path = (directory or self.root) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"original video")
        return path

    def subtitle(self, video, directory, text=SRT):
        path = directory / f"{video.stem}.bilingual.srt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    @staticmethod
    def encode(video, subtitle, output, ffmpeg, style, bitrate):
        target = output / f"{video.stem}.sub.mp4"
        target.write_bytes(b"encoded video")
        return target

    def burn(self, *arguments):
        return invoke("burn", *arguments)

    def test_config_only_burn_uses_all_mapped_options(self):
        videos = [self.video("a.mp4"), self.video("b.mov")]
        subs = self.root / "subs"
        for video in videos:
            self.subtitle(video, subs)
        out = self.root / "burned"
        out.mkdir()
        (out / "a.sub.mp4").write_bytes(b"old output")
        self.write_config(
            f'[burn]\ninputs = ["{videos[0]}", "{videos[1]}"]\n'
            f'output_dir = "{out}"\nsubtitle_dir = "{subs}"\nyes = true\n')
        with mock.patch("builtins.input", side_effect=AssertionError("prompted")):
            code, _, stderr = self.burn()
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual([c.args[0] for c in self.encoder.call_args_list],
                         [v.absolute() for v in videos])
        self.assertEqual([c.args[1] for c in self.encoder.call_args_list],
                         [subs / "a.bilingual.srt", subs / "b.bilingual.srt"])
        self.assertEqual((out / "a.sub.mp4").read_bytes(), b"encoded video")

    def test_cli_input_list_replaces_config_list_wholesale(self):
        cli_a, cli_b = self.video("cli-a.mp4"), self.video("cli-b.mov")
        out = self.root / "out"
        out.mkdir()
        for video in (cli_a, cli_b):
            self.subtitle(video, out)
        self.write_config('[burn]\ninputs = ["ghost/saved-a.mp4", '
                          f'"ghost/saved-b.mov"]\noutput_dir = "{out}"\n')
        code, _, stderr = self.burn(cli_a, cli_b)
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual([c.args[0] for c in self.encoder.call_args_list],
                         [cli_a.absolute(), cli_b.absolute()])

    def test_missing_burn_inputs_or_output_are_errors(self):
        self.write_config("")
        code, _, stderr = self.burn("-o", self.root / "out")
        self.assertEqual(code, 2)
        self.assertIn("burn.inputs", stderr)
        video = self.video()
        code, _, stderr = self.burn(video)
        self.assertEqual(code, 2)
        self.assertIn("-o/--output-dir", stderr)
        self.assertIn("burn.output_dir", stderr)
        self.preflight.assert_not_called()
        self.encoder.assert_not_called()

    def test_cli_subtitle_file_overrides_config_subtitle_dir(self):
        video = self.video()
        out = self.root / "out"
        out.mkdir()
        subtitle = self.root / "edited.srt"
        subtitle.write_text(SRT, encoding="utf-8")
        self.write_config(f'[burn]\noutput_dir = "{out}"\n'
                          'subtitle_dir = "ghost-subs"\n')
        code, _, stderr = self.burn(video, "-s", subtitle)
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(self.encoder.call_args.args[1], subtitle.absolute())

    def test_cli_subtitle_dir_overrides_config_subtitle_file(self):
        videos = [self.video("first.mp4"), self.video("second.mov")]
        subs = self.root / "cli-subs"
        for video in videos:
            self.subtitle(video, subs)
        out = self.root / "out"
        self.write_config(f'[burn]\noutput_dir = "{out}"\n'
                          'subtitles = "ghost.srt"\n')
        code, _, stderr = self.burn(*videos, "--subtitle-dir", subs)
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual([c.args[1].parent for c in self.encoder.call_args_list],
                         [subs.absolute()] * 2)

    def test_config_dual_source_conflict_needs_a_cli_source(self):
        video = self.video()
        out = self.root / "out"
        out.mkdir()
        self.subtitle(video, out)
        subs = self.root / "subs"
        self.subtitle(video, subs)
        self.write_config(f'[burn]\noutput_dir = "{out}"\n'
                          f'subtitles = "{out / "a.bilingual.srt"}"\n'
                          f'subtitle_dir = "{subs}"\n')
        code, _, stderr = self.burn(video)
        self.assertEqual(code, 2)
        self.assertIn("burn.subtitles", stderr)
        self.assertIn("burn.subtitle_dir", stderr)
        self.encoder.assert_not_called()
        code, _, stderr = self.burn(video, "--subtitle-dir", subs)
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(self.encoder.call_args.args[1],
                         subs / "a.bilingual.srt")

    def test_cli_sources_remain_mutually_exclusive(self):
        video = self.video()
        self.write_config("")
        code, _, _ = self.burn(video, "-s", "x.srt", "--subtitle-dir", "subs",
                               "-o", self.root / "out")
        self.assertEqual(code, 2)
        self.load_burn.assert_not_called()
        self.encoder.assert_not_called()

    def test_default_subtitle_mapping_follows_the_final_output_dir(self):
        video = self.video("clip.mp4")
        cli_out = self.root / "cli-out"
        cli_out.mkdir()
        subtitle = self.subtitle(video, cli_out)
        self.write_config('[burn]\noutput_dir = "saved-out"\n')
        code, _, stderr = self.burn(video, "-o", cli_out)
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(self.encoder.call_args.args[1], subtitle.absolute())
        self.assertFalse((self.root / "saved-out").exists())

    def test_config_subtitle_file_still_requires_exactly_one_video(self):
        videos = [self.video("a.mp4"), self.video("b.mp4")]
        out = self.root / "out"
        subtitle = self.root / "captions.srt"
        subtitle.write_text(SRT, encoding="utf-8")
        self.write_config(f'[burn]\noutput_dir = "{out}"\n'
                          f'subtitles = "{subtitle}"\n')
        code, _, stderr = self.burn(*videos)
        self.assertEqual(code, 2)
        self.assertIn("exactly one video", stderr)
        self.encoder.assert_not_called()

    def test_config_yes_and_no_yes_control_overwrite_prompts(self):
        video = self.video()
        out = self.root / "out"
        out.mkdir()
        self.subtitle(video, out)
        target = out / "a.sub.mp4"
        target.write_bytes(b"old output")
        self.write_config(f'[burn]\noutput_dir = "{out}"\nyes = true\n')
        with mock.patch("builtins.input", side_effect=AssertionError("prompted")):
            self.assertEqual(self.burn(video)[0], 0)
        self.assertEqual(target.read_bytes(), b"encoded video")
        self.encoder.reset_mock()
        target.write_bytes(b"old output")
        with mock.patch("builtins.input", side_effect=EOFError):
            code, stdout, _ = self.burn(video, "--no-yes")
        self.assertEqual(code, 0)
        self.assertIn("1 skipped", stdout)
        self.encoder.assert_not_called()
        self.assertEqual(target.read_bytes(), b"old output")

    def test_burn_ignores_invalid_pipeline_sections(self):
        video = self.video()
        out = self.root / "out"
        out.mkdir()
        self.subtitle(video, out)
        self.write_config('run = "broken"\ndeepseek = 123\nasr = false\n'
                          'prompt = []\nvocabulary = "broken"\n'
                          f'[burn]\noutput_dir = "{out}"\n')
        code, _, stderr = self.burn(video)
        self.assertEqual((code, stderr), (0, ""))

    def test_broken_toml_fails_burn_even_with_full_cli(self):
        video = self.video()
        self.write_config("[burn")
        code, _, stderr = self.burn(video, "-o", self.root / "out", "-y")
        self.assertEqual(code, 2)
        self.assertIn("invalid TOML", stderr)
        self.preflight.assert_not_called()
        self.encoder.assert_not_called()

    def test_missing_config_burn_uses_cli_and_builtin_defaults(self):
        video = self.video()
        out = self.root / "out"
        out.mkdir()
        self.subtitle(video, out)
        target = out / "a.sub.mp4"
        target.write_bytes(b"old output")
        with mock.patch("builtins.input", side_effect=EOFError):
            code, stdout, _ = self.burn(video, "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("1 skipped", stdout)
        self.assertEqual(target.read_bytes(), b"old output")
        _, _, cfg = self.preflight.call_args.args
        self.assertEqual(cfg.video_bitrate, config.DEFAULT_VIDEO_BITRATE)
        self.assertIs(cfg.yes, False)

    def test_burn_tilde_expansion_for_config_inputs(self):
        home = self.root / "home"
        video = self.video("a.mp4", home / "vids")
        out = home / "out"
        out.mkdir(parents=True)
        self.subtitle(video, out)
        self.write_config('[burn]\ninputs = ["~/vids/a.mp4"]\n'
                          'output_dir = "~/out"\n')

        def expanduser(path):
            text = str(path)
            if text == "~":
                return home
            if text.startswith("~/"):
                return home / text[2:]
            return path

        with mock.patch.object(Path, "expanduser", expanduser):
            code, _, stderr = self.burn()
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(self.encoder.call_args.args[0], video.absolute())

    def test_config_directory_input_expands_sorted_and_dedupes(self):
        directory = self.root / "videos"
        b = self.video("b.mp4", directory)
        a = self.video("a.MOV", directory)
        self.video("ignored.txt", directory)
        out = self.root / "out"
        out.mkdir()
        for video in (a, b):
            self.subtitle(video, out)
        self.write_config(f'[burn]\ninputs = ["{directory}", "{directory}"]\n'
                          f'output_dir = "{out}"\n')
        code, _, stderr = self.burn()
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual([c.args[0] for c in self.encoder.call_args_list],
                         [a.absolute(), b.absolute()])

    def test_config_yes_cannot_bypass_target_protection(self):
        video = self.video()
        out = self.root / "out"
        out.mkdir()
        self.subtitle(video, out)
        (out / "a.sub.mp4").symlink_to(video)
        self.write_config(f'[burn]\noutput_dir = "{out}"\nyes = true\n')
        code, _, stderr = self.burn(video)
        self.assertEqual(code, 2)
        self.assertIn("would overwrite", stderr)
        self.assertEqual(video.read_bytes(), b"original video")
        self.encoder.assert_not_called()


class TestHelpAndVersionIgnoreConfig(unittest.TestCase):
    def test_help_and_version_never_read_config(self):
        with mock.patch("ja_video_subtitles.cli.load",
                        side_effect=AssertionError("config read")), \
                mock.patch("ja_video_subtitles.cli.load_burn",
                           side_effect=AssertionError("config read")):
            for argv in (("--help",), ("run", "--help"), ("burn", "--help"),
                         ("download", "--help"), ("--version",)):
                with self.subTest(argv=argv):
                    code, stdout, _ = invoke(*argv)
                    self.assertEqual(code, 0)
                    self.assertTrue(stdout.strip())

    def test_download_falls_back_to_default_model_with_a_warning(self):
        stderr = io.StringIO()
        with mock.patch("sys.argv", ["ja-video-subtitles", "download"]), \
                mock.patch("ja_video_subtitles.cli.load",
                           side_effect=config.ConfigError("broken")), \
                mock.patch("ja_video_subtitles.cli.download") as download, \
                redirect_stderr(stderr):
            cli.main()  # download returns normally, without sys.exit
        self.assertIn("default", stderr.getvalue())
        download.assert_called_once_with(config.DEFAULT_ASR_MODEL)


if __name__ == "__main__":
    unittest.main()
