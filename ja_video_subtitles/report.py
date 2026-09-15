"""Run report: each `run` or `burn` writes report-<timestamp>.md into the output dir.

Covers config summary, per-video stage durations/status, product listing
(name/size/subtitle count) and failure reasons. The api_key is never
written.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import srt

STAGE_LABELS = {"transcribe": "Transcribe", "translate": "Translate",
                "vocabulary": "Vocabulary",
                "merge": "Bilingual merge", "burn": "Burn", "audio": "MP3 export"}
PRODUCT_SUFFIXES = [".ja.srt", ".ja.json", ".zh.srt", ".bilingual.srt",
                    ".vocab.json", ".vocab.md", ".sub.mp4", ".mp3"]


@dataclass
class StageRecord:
    """One attempted pipeline stage and its timing or diagnostic note."""

    name: str            # transcribe / translate / vocabulary / merge / burn / audio
    status: str          # done / skipped / failed
    seconds: float = 0.0
    note: str = ""


@dataclass
class VideoRecord:
    """Aggregate stage results, including nonfatal auxiliary-stage failures."""

    name: str
    stem: str
    status: str = "done"  # done / partial / failed / skipped
    stages: list[StageRecord] = field(default_factory=list)
    error: str = ""
    subtitle_source: str = ""


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024


def _fmt_dur(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s" if m else f"{s}s"


def _count_srt(path: Path) -> int | None:
    try:
        return sum(1 for _ in srt.parse(path.read_text(encoding="utf-8")))
    except Exception:
        return None


class Reporter:
    """Build a local Markdown report using effective output settings and stages."""

    def __init__(self, out_dir: Path, *, version: str, asr_model: str,
                 translate_model: str, base_url: str, bitrate: str,
                 burn_only: bool = False, vocabulary_config: dict | None = None):
        self.out_dir = out_dir
        self.version = version
        self.asr_model = asr_model
        self.translate_model = translate_model
        self.base_url = base_url
        self.bitrate = bitrate
        self.burn_only = burn_only
        self.vocabulary_config = vocabulary_config
        self.start = datetime.now()
        self.path = self.out_dir / f"report-{self.start:%Y%m%d-%H%M%S}.md"
        self.records: list[VideoRecord] = []

    def write(self) -> Path:
        """Write the batch summary, stage results, and available selected products."""
        end = datetime.now()
        total = (end - self.start).total_seconds()
        done = [r for r in self.records if r.status == "done"]
        partial = [r for r in self.records if r.status == "partial"]
        failed = [r for r in self.records if r.status == "failed"]
        skipped = [r for r in self.records if r.status == "skipped"]

        L: list[str] = []
        L.append("# ja-video-subtitles Run Report")
        L.append("")
        L.append(f"- Started: {self.start:%Y-%m-%d %H:%M:%S}")
        L.append(f"- Finished: {end:%Y-%m-%d %H:%M:%S} "
                 f"(total {_fmt_dur(total)})")
        L.append(f"- Version: {self.version}")
        partial_summary = "" if self.burn_only else f" / {len(partial)} partial"
        L.append(f"- Summary: {len(done)} succeeded / {len(failed)} failed / "
                 f"{len(skipped)} skipped{partial_summary}, "
                 f"{len(self.records)} video(s)")
        L.append("")
        L.append("## Configuration")
        L.append("")
        L.append(f"- ASR model: `{self.asr_model}`")
        L.append(f"- Translator: `{self.translate_model}` ({self.base_url})")
        subtitle_kind = "existing SRT" if self.burn_only else "JA/ZH bilingual"
        L.append(f"- Burn: h264_videotoolbox @ {self.bitrate}, "
                 f"{subtitle_kind} hard subtitles")
        if self.vocabulary_config is not None:
            cfg = self.vocabulary_config
            L.append(f"- Vocabulary: enabled={cfg['enabled']}, "
                     f"learner={cfg['learner_level']}, "
                     f"include_unknown={cfg['include_unknown']}, "
                     f"max_examples={cfg['max_examples']}")
            L.append(f"- Vocabulary output: `{cfg.get('output_dir', self.out_dir)}`, "
                     f"format={cfg.get('format', 'both')}")
        L.append("")
        L.append("## Details")
        for r in self.records:
            L.append("")
            L.append(f"### {r.name} ({r.status})")
            if r.subtitle_source:
                L.append("")
                L.append(f"Subtitles: `{r.subtitle_source}`")
            if r.error:
                L.append("")
                L.append(f"Error: `{r.error}`")
            if r.stages:
                L.append("")
                L.append("| Stage | Status | Duration | Note |")
                L.append("|---|---|---|---|")
                for s in r.stages:
                    label = STAGE_LABELS.get(s.name, s.name)
                    st = ("skipped (artifact exists)" if s.status == "skipped"
                          else s.status)
                    dur = "-" if s.status == "skipped" else _fmt_dur(s.seconds)
                    L.append(f"| {label} | {st} | {dur} | {s.note} |")
            if r.status != "failed":
                L.extend(self._product_lines(r))
        L.append("")
        L.append("Full log: `run.log` in this directory.")
        L.append("")

        self.path.write_text("\n".join(L), encoding="utf-8")
        return self.path

    def _product_lines(self, record: VideoRecord) -> list[str]:
        """List selected outputs at their actual paths, excluding failed audio."""
        rows = []
        for suffix in ([".sub.mp4"] if self.burn_only else PRODUCT_SUFFIXES):
            directory = self.out_dir
            if suffix.startswith(".vocab.") and self.vocabulary_config is not None:
                # Format switches leave old files intact; list only this selection.
                cfg = self.vocabulary_config
                if not cfg["enabled"]:
                    continue
                if cfg.get("format", "both") not in ("both", suffix.rsplit(".", 1)[1]):
                    continue
                directory = Path(cfg.get("output_dir", self.out_dir))
            if suffix == ".mp3" and any(
                    stage.name == "audio" and stage.status == "failed"
                    for stage in record.stages):
                continue
            p = directory / f"{record.stem}{suffix}"
            if not p.is_file():
                continue
            display_path = p.name if directory.resolve() == self.out_dir.resolve() else str(p.absolute())
            line = f"- `{display_path}` ({_fmt_size(p.stat().st_size)}"
            if suffix.endswith(".srt"):
                n = _count_srt(p)
                if n is not None:
                    line += f", {n} subtitles"
            rows.append(line + ")")
        if not rows:
            return []
        return ["", "Products:", ""] + rows
