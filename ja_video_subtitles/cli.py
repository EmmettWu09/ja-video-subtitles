"""CLI entry point: ja-video-subtitles download / ja-video-subtitles run <path> -o <dir>."""

import argparse
import sys
import time
from pathlib import Path

import srt

from . import __version__
from . import burn as burn_mod
from . import merge as merge_mod
from . import preflight, transcribe as transcribe_mod
from . import translate as translate_mod
from .config import load
from .model import download
from .report import Reporter, StageRecord, VideoRecord

SUPPORTED_SUFFIXES = {".mp4", ".mov"}


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
    if path.is_file():
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise SystemExit(f"only mp4/mov files are supported: {path}")
        return [path]
    videos = sorted(p for p in path.iterdir()
                    if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES)
    if not videos:
        raise SystemExit(f"no mp4/mov files found in directory: {path}")
    return videos


def confirm_overwrites(videos: list[Path], out_dir: Path,
                       assume_yes: bool) -> tuple[list[Path], list[Path]]:
    """Return (to_process, skipped). All conflicts are resolved upfront,
    before any burning starts."""
    todo, skipped = [], []
    for v in videos:
        target = out_dir / f"{v.stem}.sub.mp4"
        if target.exists() and not assume_yes:
            try:
                ans = input(f"{target} already exists. Overwrite? [y/N] "
                            ).strip().lower()
            except EOFError:  # non-interactive session: keep the old file
                print(f"[skip] non-interactive session, "
                      f"keeping existing {target.name}")
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

    if force or not _valid_srt(bilingual):
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


def cmd_run(args: argparse.Namespace) -> int:
    src = Path(args.input)
    if not src.exists():
        print(f"input path does not exist: {src}", file=sys.stderr)
        return 2
    out_dir = Path(args.output_dir)
    videos = collect_videos(src)

    try:
        cfg, ffmpeg = preflight.run(videos, out_dir)
    except preflight.PreflightError as e:
        print(f"Preflight checks failed:\n{e}", file=sys.stderr)
        return 2

    # Tee all output into run.log once preflight passes, so long batch
    # runs leave a record even if the terminal is closed.
    log_fp = open(out_dir / "run.log", "a", encoding="utf-8")
    orig_out, orig_err = sys.stdout, sys.stderr
    sys.stdout = _Tee(orig_out, log_fp)
    sys.stderr = _Tee(orig_err, log_fp)
    try:
        todo, skipped = confirm_overwrites(
            videos, out_dir, assume_yes=args.yes or args.force)

        reporter = Reporter(out_dir, version=__version__,
                            asr_model=cfg.asr_model_id,
                            translate_model=cfg.model, base_url=cfg.base_url,
                            bitrate=cfg.video_bitrate)
        reporter.records.extend(
            VideoRecord(v.name, v.stem, status="skipped") for v in skipped)

        succeeded, failed = [], []
        for i, video in enumerate(todo, 1):
            print(f"\n===== [{i}/{len(todo)}] {video.name} =====")
            record = VideoRecord(video.name, video.stem)
            reporter.records.append(record)
            try:
                process_video(video, out_dir, cfg, ffmpeg, args.force, record)
                succeeded.append(video)
            except Exception as e:
                print(f"[error] failed to process {video.name}: {e}",
                      file=sys.stderr)
                record.status, record.error = "failed", str(e)
                failed.append(video)

        print(f"\n===== Summary: {len(succeeded)} succeeded, "
              f"{len(failed)} failed, {len(skipped)} skipped =====")
        for v in failed:
            print(f"  failed: {v.name}")
        for v in skipped:
            print(f"  skipped: {v.name}")
        report_path = reporter.write()
        print(f"[report] run report -> {report_path}")
        return 1 if failed else 0
    finally:
        sys.stdout, sys.stderr = orig_out, orig_err
        log_fp.close()


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="ja-video-subtitles",
        description="Japanese video -> JA/ZH bilingual hard subtitles "
                    "(macOS only)",
        epilog="Prerequisites: config.toml with api_key, and "
               "`ja-video-subtitles download` has been run once.")
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
        description="Transcribe -> translate -> bilingual merge -> burn. "
                    "All artifacts go into the -o directory.",
        epilog="examples:\n"
               "  ja-video-subtitles run video.mp4 -o out\n"
               "  ja-video-subtitles run ./videos -o out -y   # batch, auto-overwrite\n"
               "  ja-video-subtitles run video.mov -o out --force   # redo all stages",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p_run.add_argument("input", help="an mp4/mov file or a folder of them")
    p_run.add_argument("-o", "--output-dir", required=True,
                       help="directory for all output artifacts")
    p_run.add_argument("--force", action="store_true",
                       help="redo every stage, ignoring existing artifacts")
    p_run.add_argument("-y", "--yes", action="store_true",
                       help="overwrite existing outputs without asking")

    args = ap.parse_args()
    if args.command == "download":
        try:
            model_id = load().asr_model_id
        except Exception:
            from .config import DEFAULT_ASR_MODEL
            model_id = DEFAULT_ASR_MODEL
        download(model_id)
        return
    sys.exit(cmd_run(args))


if __name__ == "__main__":
    main()
