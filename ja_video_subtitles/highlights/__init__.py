"""Classroom highlight pipeline: transcript pairing, analysis, clips, essence.

Runs after burn inside `run`; the essence video lands next to the burned
video at ``<video_dir>/<stem>.highlights.mp4`` and everything else under
``<video_dir>/highlights/``. Stage-level failures propagate to the caller;
essence-only failures degrade to ``essence_incomplete`` while keeping clips.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from ..api_util import safe_error
from ..ffmpeg_util import find_ffprobe, probe_duration
from ..layout import essence_path, highlights_dir
from . import analysis, artifacts, render, timeline, transcript, tts

PROMPT_VERSION = analysis.PROMPT_VERSION

STAGES = ("transcript", "analysis", "selection", "boundaries", "clips",
          "plan", "tts", "render", "check")
# Stage cache granularity: clips depend on the analysis inputs only; the
# essence stages add voices, the intro offset and the target duration.
_ANALYSIS_KEYS = ("video", "ja_srt", "zh_srt", "model", "prompt_version")
_ESSENCE_KEYS = _ANALYSIS_KEYS + ("ja_voice", "zh_voice",
                                  "intro_start_seconds", "target_seconds")
_STAGE_KEY_PARTS = {
    "transcript": _ANALYSIS_KEYS, "analysis": _ANALYSIS_KEYS,
    "selection": _ANALYSIS_KEYS, "boundaries": _ANALYSIS_KEYS,
    "clips": _ANALYSIS_KEYS, "plan": _ESSENCE_KEYS,
    "tts": _ESSENCE_KEYS, "render": _ESSENCE_KEYS, "check": _ESSENCE_KEYS,
}
ESSENCE_STAGES = ("plan", "tts", "render")


@dataclass
class HighlightsResult:
    clip_count: int
    essence_seconds: float | None
    essence_incomplete: bool
    output_dir: Path
    note: str = ""


class EssenceError(Exception):
    """The essence video cannot be finished; clips and analysis stay valid."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _key_parts(video: Path, ja_srt: Path, zh_srt: Path, cfg) -> dict:
    return {
        "video": _sha256(video),
        "ja_srt": _sha256(ja_srt),
        "zh_srt": _sha256(zh_srt),
        "model": cfg.model,
        "prompt_version": PROMPT_VERSION,
        "ja_voice": cfg.highlights_ja_voice,
        "zh_voice": cfg.highlights_zh_voice,
        "target_seconds": cfg.highlights_target_seconds,
        "intro_start_seconds": cfg.highlights_intro_start_seconds,
    }


def _stage_key(parts: dict, stage: str) -> str:
    selected = {name: parts[name] for name in _STAGE_KEY_PARTS[stage]}
    payload = json.dumps(selected, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_state(hdir: Path) -> dict:
    try:
        data = json.loads((hdir / "state.json").read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("stages"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"version": 1, "stages": {}}


def _save_state(hdir: Path, state: dict) -> None:
    (hdir / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _should_skip(state: dict, stage: str, key: str, force: bool) -> bool:
    if force:
        return False
    record = state["stages"].get(stage)
    return (isinstance(record, dict) and record.get("status") == "done"
            and record.get("key") == key)


def _mark_done(state: dict, stage: str, key: str) -> None:
    state["stages"][stage] = {"status": "done", "key": key}


def _remove_stale_essence(video_dir: Path, hdir: Path, stem: str) -> None:
    """Drop finished essence artifacts before a rerun so an interrupted run
    never leaves a stale <stem>.highlights.mp4 that looks successful."""
    essence_path(video_dir, stem).unlink(missing_ok=True)
    (hdir / "subtitles" / f"{stem}.highlights.srt").unlink(missing_ok=True)
    for path in (hdir / "work").glob("seg-*.mp4"):
        path.unlink(missing_ok=True)


def _remove_stale_clips(hdir: Path, stem: str) -> None:
    for pattern in (f"clips/{stem}.clip-*.mp4",
                    f"subtitles/clips/{stem}.clip-*.srt"):
        for path in hdir.glob(pattern):
            path.unlink(missing_ok=True)


def _make_client(cfg):
    from openai import OpenAI
    return OpenAI(base_url=cfg.base_url, api_key=cfg.api_key,
                  timeout=120.0, max_retries=0)


def generate(video: Path, ja_srt: Path, zh_srt: Path, video_dir: Path,
             cfg, ffmpeg: Path, client=None, *, force: bool = False
             ) -> HighlightsResult:
    """Run the highlight pipeline for a video folder (<out>/<stem>/).

    The essence video is written to ``video_dir/<stem>.highlights.mp4``;
    all other artifacts go to ``video_dir/highlights/``. Prerequisite-stage
    failures (transcript/analysis/clips) raise. Essence failures
    (plan/TTS/render) keep clips and return essence_incomplete.
    """
    hdir = highlights_dir(video_dir)
    for sub in ("analysis/raw", "plans", "clips", "subtitles/clips", "tts",
                "work"):
        (hdir / sub).mkdir(parents=True, exist_ok=True)
    ffprobe = find_ffprobe(ffmpeg)
    if ffprobe is None:
        raise RuntimeError("ffprobe is required for the highlights stage")

    parts = _key_parts(video, ja_srt, zh_srt, cfg)
    state = _load_state(hdir)
    state["cache_key_parts"] = parts

    def key(stage: str) -> str:
        return _stage_key(parts, stage)

    # 1. Transcript pairing
    if _should_skip(state, "transcript", key("transcript"), force):
        entries = transcript.from_json(hdir / "analysis" / "transcript.json")
        print("[highlights] transcript: reused")
    else:
        entries = transcript.build(ja_srt, zh_srt)
        transcript.write_json(entries, hdir / "analysis" / "transcript.json")
        _mark_done(state, "transcript", key("transcript"))
        _save_state(hdir, state)
        print(f"[highlights] transcript: {len(entries)} paired cues")

    owned_client = None
    if client is None:
        client = owned_client = _make_client(cfg)
    plan: dict | None = None
    try:
        # 2. Chunked classroom analysis + summary synthesis
        if _should_skip(state, "analysis", key("analysis"), force):
            outcome = analysis.outcome_from_json(
                json.loads((hdir / "analysis" / "candidates.json")
                           .read_text(encoding="utf-8")))
            print("[highlights] analysis: reused")
        else:
            outcome = analysis.analyze(client, cfg, entries,
                                       hdir / "analysis" / "raw")
            _mark_done(state, "analysis", key("analysis"))
            _save_state(hdir, state)
            print(f"[highlights] analysis: {len(outcome.candidates)} candidates")

        # 3. Global selection: evidence checks, merge, dedup, review list
        if _should_skip(state, "selection", key("selection"), force):
            selection = analysis.selection_from_json(
                json.loads((hdir / "analysis" / "candidates.json")
                           .read_text(encoding="utf-8")))
        else:
            selection = analysis.select(entries, outcome.candidates)
            (hdir / "analysis" / "candidates.json").write_text(
                json.dumps(analysis.to_json(outcome, selection),
                           ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            _mark_done(state, "selection", key("selection"))
            _save_state(hdir, state)
        print(f"[highlights] selection: {len(selection.kept)} kept, "
              f"{len(selection.review)} to review, "
              f"{len(selection.discarded)} discarded")

        # 4. Boundary adjudication against the real video duration
        video_ms = round(probe_duration(ffprobe, video) * 1000)
        if _should_skip(state, "boundaries", key("boundaries"), force):
            bounds = state["bounds"]
        else:
            bounds = timeline.adjudicate(selection.kept, entries, video_ms)
            state["bounds"] = bounds
            _mark_done(state, "boundaries", key("boundaries"))
            _save_state(hdir, state)

        # 5. Independent clips (prerequisite stage: failures raise)
        if _should_skip(state, "clips", key("clips"), force):
            clips_plan = json.loads((hdir / "plans" / "clips.json")
                                    .read_text(encoding="utf-8"))
            print("[highlights] clips: reused")
        else:
            _remove_stale_clips(hdir, video.stem)
            clips_plan = render.render_clips(
                video, entries, bounds, hdir, cfg, ffmpeg, ffprobe)
            (hdir / "plans" / "clips.json").write_text(
                json.dumps(clips_plan, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            _mark_done(state, "clips", key("clips"))
            _save_state(hdir, state)
            print(f"[highlights] clips: {len(clips_plan)} exported")

        # 6-8. Essence: provisional plan, local voices, single timeline render
        essence_seconds: float | None = None
        essence_incomplete = False
        note = ""
        try:
            if _should_skip(state, "plan", key("plan"), force):
                plan = json.loads((hdir / "plans" / "highlights.json")
                                  .read_text(encoding="utf-8"))
                print("[highlights] plan: reused")
            else:
                _remove_stale_essence(video_dir, hdir, video.stem)
                plan = timeline.build_essence_plan(
                    outcome.summary, bounds,
                    cfg.highlights_target_seconds,
                    round(cfg.highlights_intro_start_seconds * 1000), video_ms)
                (hdir / "plans" / "highlights.json").write_text(
                    json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
                _mark_done(state, "plan", key("plan"))
                _save_state(hdir, state)

            if _should_skip(state, "tts", key("tts"), force):
                manifest = tts.load_manifest(hdir / "tts" / "manifest.json")
                print("[highlights] tts: reused")
            else:
                manifest = tts.synthesize_all(
                    plan, cfg, hdir / "tts", ffmpeg, ffprobe)
                _mark_done(state, "tts", key("tts"))
                _save_state(hdir, state)

            if _should_skip(state, "render", key("render"), force):
                plan = json.loads((hdir / "plans" / "highlights.json")
                                  .read_text(encoding="utf-8"))
                essence_seconds = plan["total_ms"] / 1000
                print("[highlights] render: reused")
            else:
                plan = render.render_essence(
                    video, entries, plan, manifest, hdir,
                    essence_path(video_dir, video.stem), cfg, ffmpeg, ffprobe)
                (hdir / "plans" / "highlights.json").write_text(
                    json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
                _mark_done(state, "render", key("render"))
                _save_state(hdir, state)
                essence_seconds = plan["total_ms"] / 1000
        except Exception as e:
            essence_incomplete = True
            note = safe_error(e, cfg.api_key)
            state["essence_error"] = note
            _save_state(hdir, state)
            print(f"[highlights] essence incomplete: {note}")
        else:
            state.pop("essence_error", None)
            _save_state(hdir, state)
            if plan.get("draft"):
                note = plan["draft"]
            print(f"[highlights] essence: {essence_seconds:.0f}s"
                  + (f" ({note})" if note else ""))

        # 9. Check + human-facing artifacts (always refreshed from final state)
        report = artifacts.write_all(
            hdir, video, entries, outcome, selection, bounds, clips_plan,
            None if essence_incomplete else plan, essence_incomplete, note,
            ffmpeg, ffprobe)
        state["essence_incomplete"] = essence_incomplete
        _mark_done(state, "check", key("check"))
        _save_state(hdir, state)
        if report.get("anomalies"):
            print(f"[highlights] check: {len(report['anomalies'])} "
                  "anomalie(s) recorded in report.json")
    finally:
        if owned_client is not None:
            owned_client.close()

    return HighlightsResult(
        clip_count=len(clips_plan),
        essence_seconds=essence_seconds,
        essence_incomplete=essence_incomplete,
        output_dir=hdir,
        note=note,
    )
