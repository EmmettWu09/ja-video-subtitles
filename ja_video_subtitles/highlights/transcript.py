"""Pair the pipeline's JA/ZH SRTs into one numbered transcript.

Japanese and Chinese cues with the same SRT index are one utterance. Pairing
problems are flagged, never guessed; unparsable input fails the stage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import srt

FLAG_MISSING_ZH = "missing_translation"
FLAG_MISSING_JA = "missing_japanese"
FLAG_TIME_MISMATCH = "time_mismatch"
TIME_MISMATCH_MS = 2000


@dataclass
class Entry:
    """One utterance: Japanese original plus its Chinese translation."""

    index: int
    start_ms: int
    end_ms: int
    ja: str
    zh: str
    flags: list[str] = field(default_factory=list)


def _read(path: Path) -> list[srt.Subtitle]:
    try:
        subs = list(srt.parse(path.read_text(encoding="utf-8-sig")))
    except (OSError, UnicodeError, srt.SRTParseError) as e:
        raise ValueError(f"highlights cannot parse subtitle {path}: {e}") from e
    if not subs:
        raise ValueError(f"highlights requires a nonempty subtitle: {path}")
    seen = set()
    for sub in subs:
        if type(sub.index) is not int or sub.index in seen:
            raise ValueError(
                f"highlights requires unique integer SRT indices: {path}")
        if sub.start.total_seconds() < 0 or sub.end <= sub.start:
            raise ValueError(f"highlights encountered invalid SRT timestamps: {path}")
        seen.add(sub.index)
    return subs


def build(ja_srt: Path, zh_srt: Path) -> list[Entry]:
    """Pair by SRT index; JA timing is authoritative (as in the merge stage)."""
    ja = {sub.index: sub for sub in _read(ja_srt)}
    zh = {sub.index: sub for sub in _read(zh_srt)}
    entries: list[Entry] = []
    for index in sorted(set(ja) | set(zh)):
        source = ja.get(index)
        target = zh.get(index)
        flags: list[str] = []
        if source is None:
            # A Chinese-only cue cannot be placed reliably; keep it flagged
            # with its own timing rather than dropping evidence silently.
            assert target is not None
            start_ms = round(target.start.total_seconds() * 1000)
            end_ms = round(target.end.total_seconds() * 1000)
            entries.append(Entry(index, start_ms, end_ms, "",
                                 target.content, [FLAG_MISSING_JA]))
            continue
        start_ms = round(source.start.total_seconds() * 1000)
        end_ms = round(source.end.total_seconds() * 1000)
        if target is None or not target.content.strip():
            flags.append(FLAG_MISSING_ZH)
        elif abs(round(target.start.total_seconds() * 1000) - start_ms) \
                > TIME_MISMATCH_MS:
            flags.append(FLAG_TIME_MISMATCH)
        entries.append(Entry(index, start_ms, end_ms, source.content,
                             target.content if target else "", flags))
    entries.sort(key=lambda entry: (entry.start_ms, entry.index))
    return entries


def to_json(entries: list[Entry]) -> list[dict]:
    return [{"index": e.index, "start_ms": e.start_ms, "end_ms": e.end_ms,
             "ja": e.ja, "zh": e.zh, "flags": list(e.flags)} for e in entries]


def write_json(entries: list[Entry], path: Path) -> None:
    path.write_text(json.dumps(to_json(entries), ensure_ascii=False, indent=2)
                    + "\n", encoding="utf-8")


def from_json(path: Path) -> list[Entry]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Entry(item["index"], item["start_ms"], item["end_ms"],
                  item["ja"], item["zh"], list(item.get("flags", [])))
            for item in raw]


def by_index(entries: list[Entry]) -> dict[int, Entry]:
    return {entry.index: entry for entry in entries}
