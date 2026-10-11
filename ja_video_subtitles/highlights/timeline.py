"""Boundary adjudication, the single essence timeline, and SRT time math.

Source-material times and finished-video times are kept apart; everything is
in milliseconds. `plans/highlights.json` is the one timeline shared by
rendering, subtitle burning, and SRT export.
"""

from __future__ import annotations

from datetime import timedelta

import srt

from .analysis import Candidate
from .transcript import Entry, by_index

PAD_MS = 1500
MIN_EVENT_MS = 500
MAX_BRIDGES = 6
INTRO_NOMINAL_MS = 20_000
CARD_NOMINAL_MS = 3000
DRAFT_THRESHOLD_MS = 180_000


def adjudicate(kept: list[Candidate], entries: list[Entry], video_ms: int,
               pad_ms: int = PAD_MS) -> list[dict]:
    """Map index ranges to real times with padding, clamped and non-overlapping."""
    index = by_index(entries)
    bounds = []
    for number, candidate in enumerate(kept):
        first = index[candidate.start_index]
        last = index[candidate.end_index]
        start = max(0, first.start_ms - pad_ms)
        end = min(video_ms, last.end_ms + pad_ms)
        bounds.append({"event": number, "type": candidate.type,
                       "title_zh": candidate.title_zh,
                       "reason_zh": candidate.reason_zh,
                       "context_zh": candidate.context_zh,
                       "start_index": candidate.start_index,
                       "end_index": candidate.end_index,
                       "start_ms": start, "end_ms": end})
    # Adjacent events must not overlap: split at the midpoint of the gap
    # between the underlying utterances.
    for previous, current in zip(bounds, bounds[1:]):
        if current["start_ms"] < previous["end_ms"]:
            prev_last = index[previous["end_index"]].end_ms
            next_first = index[current["start_index"]].start_ms
            midpoint = (prev_last + next_first) // 2
            previous["end_ms"] = min(previous["end_ms"], midpoint)
            current["start_ms"] = max(current["start_ms"], midpoint)
    for bound in bounds:
        if bound["end_ms"] - bound["start_ms"] < MIN_EVENT_MS:
            bound["end_ms"] = min(video_ms, bound["start_ms"] + MIN_EVENT_MS)
    return [bound for bound in bounds if bound["end_ms"] > bound["start_ms"]]


def intersect_cues(entries: list[Entry], start_index: int, end_index: int,
                   src_start_ms: int, src_end_ms: int,
                   dest_start_ms: int) -> list[dict]:
    """Clip cues to the adjudicated source range, then shift into the finished
    timeline: out = clipped_source_time - segment_source_start + segment_out_start.
    No negative times, no zero-length cues."""
    index = by_index(entries)
    cues = []
    for entry_index in range(start_index, end_index + 1):
        entry = index.get(entry_index)
        if entry is None or not entry.ja.strip():
            continue
        start = max(entry.start_ms, src_start_ms)
        end = min(entry.end_ms, src_end_ms)
        if end <= start:
            continue
        cues.append({"start_ms": start - src_start_ms + dest_start_ms,
                     "end_ms": end - src_start_ms + dest_start_ms,
                     "ja": entry.ja, "zh": entry.zh})
    return cues


def compose_srt(cues: list[dict]) -> str:
    """Compose a valid SRT: nonempty cues, non-decreasing positive times."""
    subs = []
    for number, cue in enumerate(cues, 1):
        content = "\n".join(part for part in (cue.get("ja", ""), cue.get("zh", ""))
                            if part)
        subs.append(srt.Subtitle(
            number, timedelta(milliseconds=cue["start_ms"]),
            timedelta(milliseconds=cue["end_ms"]), content))
    return srt.compose(subs)


def valid_srt(text: str) -> bool:
    """Every exported SRT must parse with nonempty cues and increasing times."""
    try:
        subs = list(srt.parse(text))
    except srt.SRTParseError:
        return False
    if not subs:
        return False
    previous_start = timedelta(0)
    for sub in subs:
        if not sub.content.strip() or sub.start < timedelta(0) \
                or sub.end <= sub.start or sub.start < previous_start:
            return False
        previous_start = sub.start
    return True


def build_essence_plan(summary: dict, bounds: list[dict],
                       target_seconds: int, intro_start_ms: int,
                       video_ms: int) -> dict:
    """Pick events for the essence under the target budget (nominal times).

    The intro keeps the source's continuous opening footage; bridges are
    capped and dropped first when over budget; a complete event is never cut
    to fit a ratio. Returns the provisional plan that TTS and rendering
    refine with measured media durations.
    """
    if intro_start_ms < 0 or intro_start_ms >= max(0, video_ms - 1000):
        raise RuntimeError(
            f"highlights intro start {intro_start_ms / 1000:.1f}s is outside "
            f"the video ({video_ms / 1000:.1f}s); adjust "
            "highlights.intro_start_seconds")
    target_ms = target_seconds * 1000
    segments: list[dict] = [{
        "kind": "intro", "source_start_ms": intro_start_ms,
        "sentences": summary["intro_sentences"],
        "nominal_ms": INTRO_NOMINAL_MS}]
    total = INTRO_NOMINAL_MS + CARD_NOMINAL_MS  # closing reserved
    bridges = 0
    selected = 0
    for bound in bounds:
        event_ms = bound["end_ms"] - bound["start_ms"]
        bridge_ms = (CARD_NOMINAL_MS if selected > 0 and bridges < MAX_BRIDGES
                     else 0)
        fits = total + bridge_ms + event_ms <= target_ms
        if not fits and selected > 0:
            continue  # over budget: prefer dropping解说/重复事件, keep events whole
        if bridge_ms:
            segments.append({"kind": "bridge",
                             "text_zh": f"高光时刻：{bound['title_zh']}",
                             "nominal_ms": CARD_NOMINAL_MS})
            bridges += 1
            total += bridge_ms
        segments.append({"kind": "event", "event": bound["event"],
                         "title_zh": bound["title_zh"],
                         "start_index": bound["start_index"],
                         "end_index": bound["end_index"],
                         "source_start_ms": bound["start_ms"],
                         "source_end_ms": bound["end_ms"],
                         "nominal_ms": event_ms})
        total += event_ms
        selected += 1
    closing_text = summary.get("closing_zh") or "本节课的高光就到这里。"
    segments.append({"kind": "closing", "text_zh": closing_text,
                     "nominal_ms": CARD_NOMINAL_MS})
    draft = ""
    if total < DRAFT_THRESHOLD_MS:
        draft = ("素材不足，精华版为较短草稿"
                 f"（预计 {total // 1000} 秒，低于通常的 180–300 秒）")
    return {"version": 1, "target_seconds": target_seconds,
            "video_ms": video_ms, "total_ms": None,
            "draft": draft, "segments": segments}
