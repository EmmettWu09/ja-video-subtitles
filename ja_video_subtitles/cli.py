"""CLI entry point: download, full pipeline (run), or existing subtitles (burn)."""

import argparse
import sys
import time
import unicodedata
from pathlib import Path
from typing import Callable

import srt

from . import __version__
from . import audio as audio_mod
from . import burn as burn_mod
from . import merge as merge_mod
from . import preflight, transcribe as transcribe_mod
from . import translate as translate_mod
from .config import ConfigError, load, load_burn, vocabulary_output_dir
from .api_util import safe_error
from .model import download
from .report import Reporter, StageRecord, VideoRecord

SUPPORTED_SUFFIXES = {".mp4", ".mov"}


def _path_arg(value: str) -> str:
    """argparse type: an explicit path must be nonempty, not blank, NUL-free."""
    if not value.strip() or "\x00" in value:
        raise argparse.ArgumentTypeError("expected a nonempty path")
    return value


def _required_option(cli_value: str | None, config_value: str | None,
                     cli_name: str, config_key: str) -> str:
    """CLI wins over config; merged required options have no hidden default."""
    if cli_value is not None:
        return cli_value
    if config_value is not None:
        return config_value
    raise ValueError(f"missing {cli_name}; pass it on the command line or set "
                     f"{config_key} in config.toml")


class _Tee:
    """Duplicate stdout/stderr writes into a log file."""

    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            s.write(data)
        return len(data)

    def flush(self):
        for s in self._streams:
            s.flush()


def collect_videos(path: Path) -> list[Path]:
    """Return one supported file or sorted, nonrecursive directory contents."""
    if path.is_file():
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(f"only mp4/mov files are supported: {path}")
        return [path]
    if not path.is_dir():
        raise ValueError(f"input path is not a file or directory: {path}")
    videos = sorted(p for p in path.iterdir()
                    if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES)
    if not videos:
        raise ValueError(f"no mp4/mov files found in directory: {path}")
    return videos


def collect_burn_videos(inputs: list[str]) -> list[Path]:
    """Expand inputs in order, deduplicate paths, and reject output collisions."""
    videos, seen, stems = [], set(), {}
    for raw in inputs:
        for video in collect_videos(Path(raw).expanduser()):
            resolved = video.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            key = unicodedata.normalize("NFC", video.stem).casefold()
            if key in stems:
                raise ValueError(
                    f"videos have the same output stem: {stems[key]} and "
                    f"{video}; rename one or use separate output directories")
            stems[key] = video
            videos.append(video.absolute())
    return videos


def burn_subtitles(videos: list[Path], out_dir: Path,
                   subtitles: str | None, subtitle_dir: str | None
                   ) -> dict[Path, Path]:
    """Resolve and fully validate every SRT before starting any encoder."""
    if subtitles and subtitle_dir:
        raise ValueError("--subtitles and --subtitle-dir are mutually exclusive")
    if subtitles and len(videos) != 1:
        raise ValueError("--subtitles requires exactly one video; "
                         "use --subtitle-dir for multiple videos")
    directory = Path(subtitle_dir).expanduser() if subtitle_dir else out_dir
    if subtitle_dir and not directory.is_dir():
        raise ValueError(f"subtitle directory does not exist: {directory}")
    result, errors = {}, []
    for video in videos:
        path = (Path(subtitles).expanduser() if subtitles else
                directory / f"{video.stem}.bilingual.srt").absolute()
        try:
            if path.suffix.lower() != ".srt":
                raise ValueError("expected an .srt file")
            subs = list(srt.parse(path.read_text(encoding="utf-8-sig")))
            if not subs or any(not sub.content.strip() or sub.start < srt.timedelta(0)
                               or sub.end <= sub.start for sub in subs):
                raise ValueError("SRT must contain nonempty cues with valid timestamps")
        except (OSError, UnicodeError, srt.SRTParseError, ValueError) as e:
            errors.append(f"{video.name}: invalid subtitle {path}: {e}")
        result[video] = path
    if errors:
        raise ValueError("\n".join(errors))
    return result


def check_burn_targets(videos: list[Path], subtitles: dict[Path, Path],
                       out_dir: Path, report_path: Path | None = None) -> None:
    """Never let an output replace a source, even through a symlink/hardlink."""
    inputs = videos + list(subtitles.values())
    pending = [out_dir / f"{video.stem}.sub.mp4" for video in videos]
    pending.append(out_dir / "run.log")
    if report_path is not None:
        pending.append(report_path)
    _check_targets(inputs, pending)


def _check_targets(inputs: list[Path], pending: list[Path]) -> None:
    """Reject nonfile targets and input/output aliases before writes begin."""
    targets: list[Path] = []
    for target in pending:
        if target.exists() and not target.is_file():
            raise ValueError(f"output target is not a file: {target}")
        for path in inputs + targets:
            if (target.resolve() == path.resolve()
                    or (target.exists() and path.exists() and target.samefile(path))):
                raise ValueError(f"output target {target} would overwrite "
                                 f"an input or another output: {path}")
        targets.append(target)


def check_run_targets(videos: list[Path], out_dir: Path, cfg,
                      report_path: Path) -> None:
    """Validate every selected run target, including external vocabulary files."""
    stems: set[str] = set()
    pending = [out_dir / "run.log", report_path]
    vocab_dir = vocabulary_output_dir(cfg, out_dir)
    formats = (("md", "json") if getattr(cfg, "vocabulary_format", "both") == "both"
               else (cfg.vocabulary_format,))
    for video in videos:
        key = unicodedata.normalize("NFC", video.stem).casefold()
        if key in stems:
            raise ValueError(f"videos have the same output stem: {video.stem}; "
                             "rename one or use separate output directories")
        stems.add(key)
        pending.extend(out_dir / f"{video.stem}{suffix}" for suffix in
                       (".ja.srt", ".ja.json", ".zh.srt", ".bilingual.srt",
                        ".sub.mp4", ".mp3"))
        if getattr(cfg, "vocabulary_enabled", False):
            pending.extend(vocab_dir / f"{video.stem}.vocab.{fmt}" for fmt in formats)
    _check_targets(videos, pending)


def confirm_overwrites(videos: list[Path], out_dir: Path,
                       assume_yes: bool, *, include_audio: bool = False
                       ) -> tuple[list[Path], list[Path]]:
    """Return (to_process, skipped). All conflicts are resolved upfront,
    before any burning starts."""
    todo, skipped = [], []
    for v in videos:
        suffixes = (".sub.mp4", ".mp3") if include_audio else (".sub.mp4",)
        existing = [out_dir / f"{v.stem}{suffix}" for suffix in suffixes
                    if (out_dir / f"{v.stem}{suffix}").exists()]
        if existing and not assume_yes:
            names = ", ".join(str(target) for target in existing)
            try:
                ans = input(f"{names} already exists. Overwrite? [y/N] "
                            ).strip().lower()
            except EOFError:  # non-interactive session: keep the old file
                print(f"[skip] non-interactive session, "
                      f"keeping existing {names}")
                skipped.append(v)
                continue
            if ans not in ("y", "yes"):
                skipped.append(v)
                continue
        todo.append(v)
    return todo, skipped


def _valid_srt(path: Path) -> bool:
    """An intermediate artifact must parse to at least one subtitle,
    otherwise it is treated as corrupt and the stage is re-run."""
    try:
        return path.stat().st_size > 0 and any(
            srt.parse(path.read_text(encoding="utf-8")))
    except (OSError, srt.SRTParseError):
        return False


def process_video(video: Path, out_dir: Path, cfg, ffmpeg: Path,
                  force: bool, record: VideoRecord) -> None:
    """Resume subtitle stages, generate selected vocabulary, burn, and export MP3.

    Vocabulary and audio errors mark the record partial. Subtitle or burn
    errors propagate to the batch runner, which continues with other videos.
    """
    ja_srt = out_dir / f"{video.stem}.ja.srt"
    zh_srt = out_dir / f"{video.stem}.zh.srt"
    bilingual = out_dir / f"{video.stem}.bilingual.srt"

    if force or not _valid_srt(ja_srt):
        t0 = time.monotonic()
        _, dropped = transcribe_mod.transcribe(video, out_dir, cfg.asr_model_id)
        record.stages.append(StageRecord(
            "transcribe", "done", time.monotonic() - t0,
            f"filtered {dropped} suspected hallucination(s)" if dropped else ""))
    else:
        print(f"[skip] exists: {ja_srt.name}")
        record.stages.append(StageRecord("transcribe", "skipped"))

    if force or not _valid_srt(zh_srt):
        from openai import OpenAI
        client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key, timeout=120)
        t0 = time.monotonic()
        translate_mod.translate(ja_srt, out_dir, client, cfg)
        record.stages.append(StageRecord("translate", "done",
                                         time.monotonic() - t0))
    else:
        print(f"[skip] exists: {zh_srt.name}")
        record.stages.append(StageRecord("translate", "skipped"))

    if cfg.vocabulary_enabled:
        t0 = time.monotonic()
        try:
            from . import vocabulary
            result = vocabulary.generate(
                ja_srt, zh_srt, vocabulary_output_dir(cfg, out_dir), cfg, force=force)
            levels = [level for level in ("N5", "N4", "N3", "N2", "N1", "未分级")
                      if result.counts.get(level, 0) or level in ("N2", "N1", "未分级")]
            counts = ", ".join(f"{level}={result.counts.get(level, 0)}" for level in levels)
            note = (f"{result.total_count} words; {counts or 'no target words'}; "
                    f"degraded={result.degraded_count}")
            if not result.total_count:
                note += "; no target words"
            print(f"[vocabulary] {result.status}: {note}")
            record.stages.append(StageRecord(
                "vocabulary", result.status, time.monotonic() - t0, note))
        except Exception as e:
            message = safe_error(e, cfg.api_key)
            print(f"[vocabulary] failed: {message}; continuing merge/burn",
                  file=sys.stderr)
            record.status, record.error = "partial", f"vocabulary: {message}"
            record.stages.append(StageRecord(
                "vocabulary", "failed", time.monotonic() - t0, message))

    if force or not merge_mod.is_fresh(ja_srt, zh_srt, bilingual):
        t0 = time.monotonic()
        merge_mod.merge(ja_srt, zh_srt, out_dir)
        record.stages.append(StageRecord("merge", "done", time.monotonic() - t0))
    else:
        print(f"[skip] exists: {bilingual.name}")
        record.stages.append(StageRecord("merge", "skipped"))

    t0 = time.monotonic()
    burn_mod.burn(video, bilingual, out_dir, ffmpeg, cfg.force_style,
                  cfg.video_bitrate)
    record.stages.append(StageRecord("burn", "done", time.monotonic() - t0))

    t0 = time.monotonic()
    try:
        audio_mod.export(video, out_dir, ffmpeg)
        record.stages.append(StageRecord("audio", "done", time.monotonic() - t0))
    except Exception as e:
        message = safe_error(e, cfg.api_key)
        print(f"[audio] failed: {message}", file=sys.stderr)
        record.status = "partial"
        record.error = "; ".join(filter(None, (record.error, f"audio: {message}")))
        record.stages.append(StageRecord(
            "audio", "failed", time.monotonic() - t0, message))


def cmd_run(args: argparse.Namespace) -> int:
    """Prepare a full run; return 2 for startup errors or the batch exit code."""
    try:
        cfg = load()
    except ConfigError as e:
        print(f"Configuration error: {safe_error(e)}", file=sys.stderr)
        return 2
    try:
        input_raw = _required_option(args.input, cfg.run_input,
                                     "input", "run.input")
        output_raw = _required_option(args.output_dir, cfg.run_output_dir,
                                      "-o/--output-dir", "run.output_dir")
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    # Apply only explicitly supplied CLI values, before destination checks.
    if args.vocab_output_dir is not None:
        cfg.vocabulary_output_dir = args.vocab_output_dir
    if args.vocab_format is not None:
        cfg.vocabulary_format = args.vocab_format
    force = args.force if args.force is not None else cfg.run_force
    yes = args.yes if args.yes is not None else cfg.run_yes

    src = Path(input_raw).expanduser()
    if not src.exists():
        print(f"input path does not exist: {src}", file=sys.stderr)
        return 2
    out_dir = Path(output_raw).expanduser()
    try:
        videos = collect_videos(src)
    except (ValueError, OSError) as e:
        print(f"invalid input: {e}", file=sys.stderr)
        return 2

    try:
        cfg, ffmpeg = preflight.run(videos, out_dir, cfg)
    except preflight.PreflightError as e:
        print(f"Preflight checks failed:\n{safe_error(e)}", file=sys.stderr)
        return 2

    reporter = Reporter(out_dir, version=__version__,
                        asr_model=cfg.asr_model_id,
                        translate_model=cfg.model, base_url=cfg.base_url,
                        bitrate=cfg.video_bitrate,
                        vocabulary_config={
                            "enabled": getattr(cfg, "vocabulary_enabled", False),
                            "learner_level": getattr(cfg, "learner_level", "N3"),
                            "include_unknown": getattr(cfg, "include_unknown", True),
                            "max_examples": getattr(cfg, "max_examples", 3),
                            "output_dir": str(vocabulary_output_dir(cfg, out_dir)),
                            "format": getattr(cfg, "vocabulary_format", "both")})
    try:
        check_run_targets(videos, out_dir, cfg, reporter.path)
    except (ValueError, OSError) as e:
        print(f"Output checks failed:\n{safe_error(e)}", file=sys.stderr)
        return 2
    return _run_batch(videos, out_dir, reporter, yes or force,
                      lambda video, record: process_video(
                          video, out_dir, cfg, ffmpeg, force, record),
                      include_audio=True)


def cmd_burn(args: argparse.Namespace) -> int:
    """Validate existing subtitles and run the local burn-only batch."""
    try:
        cfg = load_burn()
    except ConfigError as e:
        print(f"Configuration error: {safe_error(e)}", file=sys.stderr)
        return 2
    try:
        inputs = args.inputs or cfg.inputs
        if not inputs:
            raise ValueError("missing inputs; pass mp4/mov files or folders on "
                             "the command line or set burn.inputs in config.toml")
        output_raw = _required_option(args.output_dir, cfg.output_dir,
                                      "-o/--output-dir", "burn.output_dir")
        if args.subtitles is not None or args.subtitle_dir is not None:
            # An explicit CLI source replaces the whole configured source group.
            subtitles, subtitle_dir = args.subtitles, args.subtitle_dir
        else:
            if cfg.subtitles and cfg.subtitle_dir:
                raise ValueError("burn.subtitles and burn.subtitle_dir in "
                                 "config.toml are mutually exclusive; set only "
                                 "one or pass -s/--subtitles or --subtitle-dir")
            subtitles = cfg.subtitles or None
            subtitle_dir = cfg.subtitle_dir or None
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    yes = args.yes if args.yes is not None else cfg.yes
    out_dir = Path(output_raw).expanduser().absolute()
    try:
        videos = collect_burn_videos(inputs)
        subtitle_map = burn_subtitles(videos, out_dir, subtitles, subtitle_dir)
        check_burn_targets(videos, subtitle_map, out_dir)
        cfg, ffmpeg = preflight.run_burn(videos, out_dir, cfg)
    except (ValueError, OSError, preflight.PreflightError) as e:
        print(f"Burn checks failed:\n{e}", file=sys.stderr)
        return 2

    def process(video: Path, record: VideoRecord) -> None:
        subtitle = subtitle_map[video]
        print(f"[burn] subtitles: {subtitle}")
        t0 = time.monotonic()
        burn_mod.burn(video, subtitle, out_dir, ffmpeg, cfg.force_style,
                      cfg.video_bitrate)
        record.stages.append(StageRecord("burn", "done",
                                         time.monotonic() - t0))

    reporter = Reporter(out_dir, version=__version__,
                        asr_model="N/A (burn only)",
                        translate_model="N/A (burn only)", base_url="N/A",
                        bitrate=cfg.video_bitrate, burn_only=True)
    try:
        check_burn_targets(videos, subtitle_map, out_dir, reporter.path)
    except (ValueError, OSError) as e:
        print(f"Burn checks failed:\n{e}", file=sys.stderr)
        return 2
    return _run_batch(videos, out_dir, reporter, yes, process, subtitle_map)


def _run_batch(videos: list[Path], out_dir: Path, reporter: Reporter,
               assume_yes: bool,
               process: Callable[[Path, VideoRecord], None],
               subtitle_sources: dict[Path, Path] | None = None, *,
               include_audio: bool = False) -> int:
    """Confirm all overwrites, process videos independently, and persist results.

    Return 1 if any video fails or is partial, otherwise 0. Restore terminal
    streams even if processing/report writing is interrupted.
    """
    def make_record(video: Path, status: str = "done") -> VideoRecord:
        return VideoRecord(
            video.name, video.stem, status=status,
            subtitle_source=str(subtitle_sources[video]) if subtitle_sources else "")

    # Tee all output into run.log once preflight passes, so long batch
    # runs leave a record even if the terminal is closed.
    log_fp = open(out_dir / "run.log", "a", encoding="utf-8")
    orig_out, orig_err = sys.stdout, sys.stderr
    sys.stdout = _Tee(orig_out, log_fp)
    sys.stderr = _Tee(orig_err, log_fp)
    try:
        todo, skipped = confirm_overwrites(
            videos, out_dir, assume_yes=assume_yes, include_audio=include_audio)
        reporter.records.extend(
            make_record(v, "skipped") for v in skipped)

        succeeded, partial, failed = [], [], []
        for i, video in enumerate(todo, 1):
            print(f"\n===== [{i}/{len(todo)}] {video.name} =====")
            record = make_record(video)
            reporter.records.append(record)
            try:
                process(video, record)
                (partial if record.status == "partial" else succeeded).append(video)
            except Exception as e:
                message = safe_error(e)
                print(f"[error] failed to process {video.name}: {message}",
                      file=sys.stderr)
                record.status = "failed"
                record.error = "; ".join(filter(None, (record.error, message)))
                failed.append(video)

        partial_summary = "" if reporter.burn_only else f", {len(partial)} partial"
        print(f"\n===== Summary: {len(succeeded)} succeeded, "
              f"{len(failed)} failed, {len(skipped)} skipped{partial_summary} =====")
        for v in partial:
            print(f"  partial: {v.name}")
        for v in failed:
            print(f"  failed: {v.name}")
        for v in skipped:
            print(f"  skipped: {v.name}")
        report_path = reporter.write()
        print(f"[report] run report -> {report_path}")
        return 1 if failed or partial else 0
    finally:
        sys.stdout, sys.stderr = orig_out, orig_err
        log_fp.close()


def main() -> None:
    """Parse CLI input and dispatch download, full run, or standalone burn."""
    ap = argparse.ArgumentParser(
        prog="ja-video-subtitles",
        description="Japanese video -> JA/ZH bilingual hard subtitles "
                    "(macOS only)",
        epilog="For run: config.toml with api_key and "
               "`ja-video-subtitles download` are required. "
               "For burn: existing SRT subtitles and ffmpeg with libass.")
    ap.add_argument("--version", action="version",
                    version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("download",
                   help="download the ASR model (~1.5GB, one-time)",
                   description="Download the Japanese ASR model into the "
                               "project-local .cache/hf/. Defaults to the "
                               "hf-mirror.com mirror; override with "
                               "HF_ENDPOINT.")

    p_run = sub.add_parser(
        "run", help="process videos",
        description="Transcribe -> translate -> vocabulary -> bilingual merge -> burn. "
                    "Export MP3 audio alongside the subtitled video. "
                    "Explicit CLI options override config.toml, which overrides "
                    "built-in defaults; vocabulary output location and format "
                    "are configurable.",
        epilog="examples:\n"
               "  ja-video-subtitles run video.mp4 -o out\n"
               "  ja-video-subtitles run ./videos -o out -y   # batch, auto-overwrite\n"
               "  ja-video-subtitles run video.mp4 -o out --vocab-output-dir words --vocab-format md\n"
               "  ja-video-subtitles run video.mov -o out --force   # redo all stages\n"
               "  ja-video-subtitles run   # input/output from [run] in config.toml\n"
               "  ja-video-subtitles run -o out   # only the output dir from the CLI\n"
               "  ja-video-subtitles run --no-force --no-yes   # disable configured switches",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p_run.add_argument("input", nargs="?", type=_path_arg,
                       help="an mp4/mov file or a folder of them "
                            "(default: run.input in config.toml)")
    p_run.add_argument("-o", "--output-dir", type=_path_arg,
                       help="directory for subtitles, sub.mp4, MP3, log, and "
                            "report (default: run.output_dir in config.toml)")
    p_run.add_argument("--vocab-output-dir", metavar="DIR", type=_path_arg,
                       help="vocabulary directory (default: vocabulary.output_dir "
                            "in config.toml, or output-dir alongside sub.mp4)")
    p_run.add_argument("--vocab-format", choices=("md", "json", "both"),
                       help="vocabulary file format (default: vocabulary.format "
                            "in config.toml, or both)")
    force_group = p_run.add_mutually_exclusive_group()
    force_group.add_argument("--force", action="store_true", default=None,
                             help="redo every stage, ignoring existing artifacts "
                                  "(default: run.force in config.toml, or false)")
    force_group.add_argument("--no-force", action="store_false", dest="force",
                             help="disable force even when run.force is true "
                                  "in config.toml")
    yes_group = p_run.add_mutually_exclusive_group()
    yes_group.add_argument("-y", "--yes", action="store_true", default=None,
                           help="overwrite existing outputs without asking "
                                "(default: run.yes in config.toml, or false)")
    yes_group.add_argument("--no-yes", action="store_false", dest="yes",
                           help="ask before overwriting even when run.yes is "
                                "true in config.toml")

    p_burn = sub.add_parser(
        "burn", help="burn existing SRT subtitles into one or more videos",
        description="Burn existing subtitles locally, without ASR or translation. "
                    "Explicit CLI options override config.toml. "
                    "Outputs: <output-dir>/<video-stem>.sub.mp4.",
        epilog="examples:\n"
               "  ja-video-subtitles burn video.mp4 -o out\n"
               "  ja-video-subtitles burn video.mp4 -s captions.srt -o out\n"
               "  ja-video-subtitles burn a.mp4 b.mov -o out\n"
               "  ja-video-subtitles burn ./videos --subtitle-dir ./subs -o out -y\n"
               "  ja-video-subtitles burn   # inputs/output from [burn] in config.toml\n"
               "  ja-video-subtitles burn -o out --no-yes   # override configured options",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p_burn.add_argument("inputs", nargs="*", type=_path_arg,
                        help="one or more mp4/mov files or folders "
                             "(nonrecursive) (default: burn.inputs in config.toml)")
    p_burn.add_argument("-o", "--output-dir", type=_path_arg,
                        help="directory for output videos, log, and report "
                             "(default: burn.output_dir in config.toml)")
    subtitle_source = p_burn.add_mutually_exclusive_group()
    subtitle_source.add_argument("-s", "--subtitles", type=_path_arg,
                                 help="explicit SRT path (one video only; "
                                      "default: burn.subtitles in config.toml)")
    subtitle_source.add_argument(
        "--subtitle-dir", type=_path_arg,
        help="directory of <video-stem>.bilingual.srt files "
             "(default: burn.subtitle_dir in config.toml, or output-dir)")
    burn_yes_group = p_burn.add_mutually_exclusive_group()
    burn_yes_group.add_argument("-y", "--yes", action="store_true", default=None,
                                help="overwrite existing outputs without asking "
                                     "(default: burn.yes in config.toml, or false)")
    burn_yes_group.add_argument("--no-yes", action="store_false", dest="yes",
                                help="ask before overwriting even when burn.yes "
                                     "is true in config.toml")

    args = ap.parse_args()
    if args.command == "download":
        try:
            model_id = load().asr_model_id
        except Exception as e:
            from .config import DEFAULT_ASR_MODEL
            print(f"cannot read config ({safe_error(e)}); using the default "
                  f"ASR model {DEFAULT_ASR_MODEL}", file=sys.stderr)
            model_id = DEFAULT_ASR_MODEL
        download(model_id)
        return
    sys.exit(cmd_burn(args) if args.command == "burn" else cmd_run(args))


if __name__ == "__main__":
    main()
