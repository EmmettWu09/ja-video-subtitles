"""Run report: each `run` writes report-<timestamp>.md into the output dir.

Covers config summary, per-video stage durations/status, product listing
(name/size/subtitle count) and failure reasons. The api_key is never
written.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import srt

STAGE_LABELS = {"transcribe": "Transcribe", "translate": "Translate",
                "merge": "Bilingual merge", "burn": "Burn"}
PRODUCT_SUFFIXES = [".ja.srt", ".ja.json", ".zh.srt", ".bilingual.srt",
                    ".sub.mp4"]


@dataclass
class StageRecord:
    name: str            # transcribe / translate / merge / burn
    status: str          # done / skipped
    seconds: float = 0.0
    note: str = ""


@dataclass
class VideoRecord:
    name: str
    stem: str
    status: str = "done"  # done / failed / skipped
    stages: list[StageRecord] = field(default_factory=list)
    error: str = ""


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
    def __init__(self, out_dir: Path, *, version: str, asr_model: str,
                 translate_model: str, base_url: str, bitrate: str):
        self.out_dir = out_dir
        self.version = version
        self.asr_model = asr_model
        self.translate_model = translate_model
        self.base_url = base_url
        self.bitrate = bitrate
        self.start = datetime.now()
        self.records: list[VideoRecord] = []

    def write(self) -> Path:
        end = datetime.now()
        total = (end - self.start).total_seconds()
        done = [r for r in self.records if r.status == "done"]
        failed = [r for r in self.records if r.status == "failed"]
        skipped = [r for r in self.records if r.status == "skipped"]

        L: list[str] = []
        L.append("# ja-video-subtitles Run Report")
        L.append("")
        L.append(f"- Started: {self.start:%Y-%m-%d %H:%M:%S}")
        L.append(f"- Finished: {end:%Y-%m-%d %H:%M:%S} "
                 f"(total {_fmt_dur(total)})")
        L.append(f"- Version: {self.version}")
        L.append(f"- Summary: {len(done)} succeeded / {len(failed)} failed / "
                 f"{len(skipped)} skipped, {len(self.records)} video(s)")
        L.append("")
        L.append("## Configuration")
        L.append("")
        L.append(f"- ASR model: `{self.asr_model}`")
        L.append(f"- Translator: `{self.translate_model}` ({self.base_url})")
        L.append(f"- Burn: h264_videotoolbox @ {self.bitrate}, "
                 f"JA/ZH bilingual hard subtitles")
        L.append("")
        L.append("## Details")
        for r in self.records:
            L.append("")
            L.append(f"### {r.name} ({r.status})")
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
                          else "done")
                    dur = "-" if s.status == "skipped" else _fmt_dur(s.seconds)
                    L.append(f"| {label} | {st} | {dur} | {s.note} |")
            if r.status != "failed":
                L.extend(self._product_lines(r.stem))
        L.append("")
        L.append("Full log: `run.log` in this directory.")
        L.append("")

        path = self.out_dir / f"report-{self.start:%Y%m%d-%H%M%S}.md"
        path.write_text("\n".join(L), encoding="utf-8")
        return path

    def _product_lines(self, stem: str) -> list[str]:
        rows = []
        for suffix in PRODUCT_SUFFIXES:
            p = self.out_dir / f"{stem}{suffix}"
            if not p.exists():
                continue
            line = f"- `{p.name}` ({_fmt_size(p.stat().st_size)}"
            if suffix.endswith(".srt"):
                n = _count_srt(p)
                if n is not None:
                    line += f", {n} subtitles"
            rows.append(line + ")")
        if not rows:
            return []
        return ["", "Products:", ""] + rows
