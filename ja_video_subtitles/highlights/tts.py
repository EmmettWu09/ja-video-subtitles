"""Local macOS `say` voice-over synthesis for the essence video.

The intro is Japanese short sentences with inter-sentence pauses totaling
15-25 seconds; when it runs long, the text is shortened and re-synthesized
(at most 2 rounds) instead of speeding up speech.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ..ffmpeg_util import probe_duration

INTRO_MIN_S = 15.0
INTRO_MAX_S = 25.0
BASE_PAUSE_S = 0.6
MAX_PAUSE_S = 2.5
MAX_SHORTEN_ROUNDS = 2
CARD_MIN_S = 3.0
CARD_TAIL_S = 0.5


def _say(text: str, voice: str, out_aiff: Path) -> None:
    try:
        result = subprocess.run(
            ["say", "-v", voice, "-o", str(out_aiff), text],
            capture_output=True, text=True, timeout=120)
    except OSError as e:
        raise RuntimeError(f"cannot run the macOS `say` command: {e}") from e
    if result.returncode != 0 or not out_aiff.exists():
        raise RuntimeError(
            f"`say` failed for voice {voice}: {result.stderr.strip()[-300:]}. "
            "Check highlights.ja_voice/zh_voice (`say -v ?` lists voices), "
            "or disable highlights with --no-highlights")


def _duration(ffprobe: Path, media: Path) -> float:
    return probe_duration(ffprobe, media)


def _mix_sentences(aiffs: list[Path], offsets_s: list[float], total_s: float,
                   out_m4a: Path, ffmpeg: Path) -> None:
    """Combine sentence audio at the given offsets; loudness-normalized."""
    inputs = [item for aiff in aiffs for item in ("-i", str(aiff))]
    if len(aiffs) == 1:
        graph = f"[0:a]loudnorm,apad,atrim=0:{total_s:.3f}[aout]"
    else:
        parts = [f"[{k}:a]adelay={round(offset * 1000)}[d{k}]"
                 for k, offset in enumerate(offsets_s)]
        joined = "".join(f"[d{k}]" for k in range(len(aiffs)))
        parts.append(f"{joined}amix=inputs={len(aiffs)}:normalize=0,"
                     f"loudnorm,apad,atrim=0:{total_s:.3f}[aout]")
        graph = ";".join(parts)
    result = subprocess.run(
        [str(ffmpeg), "-y", *inputs, "-filter_complex", graph,
         "-map", "[aout]", "-ar", "44100", "-ac", "2",
         "-c:a", "aac", "-b:a", "192k", str(out_m4a)],
        capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg intro audio mix failed:\n"
                           f"{result.stderr[-1000:]}")


def _build_intro(sentences: list[dict], voice: str, tts_dir: Path,
                 ffmpeg: Path, ffprobe: Path) -> dict:
    """Synthesize sentence audio; returns total time and per-sentence cues."""
    aiffs, durations = [], []
    for number, sentence in enumerate(sentences):
        aiff = tts_dir / f"intro-{number:02d}.aiff"
        _say(sentence["ja"], voice, aiff)
        aiffs.append(aiff)
        durations.append(_duration(ffprobe, aiff))
    speech = sum(durations)
    gaps = max(0, len(aiffs) - 1)
    pause = BASE_PAUSE_S
    if gaps and speech + pause * gaps < INTRO_MIN_S:
        pause = min(MAX_PAUSE_S, pause + (INTRO_MIN_S - speech - pause * gaps)
                    / gaps)
    total = speech + pause * gaps
    pad = max(0.0, INTRO_MIN_S - total)
    total += pad
    offsets, cues, cursor = [], [], 0.0
    for sentence, duration in zip(sentences, durations):
        offsets.append(cursor)
        cues.append({"ja": sentence["ja"], "zh": sentence["zh"],
                     "start_ms": round(cursor * 1000),
                     "end_ms": round((cursor + duration) * 1000)})
        cursor += duration + pause
    out = tts_dir / "intro.m4a"
    _mix_sentences(aiffs, offsets, total, out, ffmpeg)
    actual = _duration(ffprobe, out)
    return {"audio": "tts/intro.m4a", "total_ms": round(actual * 1000),
            "sentences": cues}


def _synthesize_intro(sentences: list[dict], voice: str, tts_dir: Path,
                      ffmpeg: Path, ffprobe: Path) -> dict:
    """Build the intro, shortening the script (not the speech) when too long."""
    current = list(sentences)
    for round_number in range(MAX_SHORTEN_ROUNDS + 1):
        intro = _build_intro(current, voice, tts_dir, ffmpeg, ffprobe)
        if intro["total_ms"] <= INTRO_MAX_S * 1000:
            if round_number:
                print(f"[highlights] intro shortened to {len(current)} "
                      f"sentence(s) to fit 15-25s")
            return intro
        if round_number >= MAX_SHORTEN_ROUNDS or len(current) <= 1:
            raise RuntimeError(
                f"intro voice-over is {intro['total_ms'] / 1000:.1f}s, beyond "
                f"25s after {MAX_SHORTEN_ROUNDS} shortening round(s); "
                "essence marked incomplete")
        current = current[:-1]  # drop the last JA/ZH sentence pair together
    raise AssertionError("unreachable")


def _installed_voices() -> set[str]:
    try:
        result = subprocess.run(["say", "-v", "?"], capture_output=True,
                                text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"cannot list `say` voices: {e}") from e
    return {line.split()[0] for line in result.stdout.splitlines()
            if line.split()}


def synthesize_all(plan: dict, cfg, tts_dir: Path, ffmpeg: Path,
                   ffprobe: Path) -> dict:
    """Synthesize intro, bridge, and closing voices; write manifest.json."""
    tts_dir.mkdir(parents=True, exist_ok=True)
    # `say -v <missing>` silently falls back to the default voice, so the
    # configured voices are verified explicitly before synthesizing.
    missing = sorted({cfg.highlights_ja_voice, cfg.highlights_zh_voice}
                     - _installed_voices())
    if missing:
        raise RuntimeError(
            f"highlights voice(s) not installed: {', '.join(missing)}; set "
            "highlights.ja_voice / highlights.zh_voice to voices listed by "
            "`say -v ?`, or disable highlights with --no-highlights")
    intro_segment = next(seg for seg in plan["segments"]
                         if seg["kind"] == "intro")
    video_ms = plan["video_ms"]
    intro = _synthesize_intro(intro_segment["sentences"],
                              cfg.highlights_ja_voice, tts_dir, ffmpeg, ffprobe)
    intro_end = intro_segment["source_start_ms"] + intro["total_ms"]
    if intro_end > video_ms:
        raise RuntimeError(
            f"the source has no continuous intro footage for "
            f"{intro['total_ms'] / 1000:.1f}s from "
            f"{intro_segment['source_start_ms'] / 1000:.1f}s "
            f"(video {video_ms / 1000:.1f}s); adjust "
            "highlights.intro_start_seconds")
    cards: dict[str, dict] = {}
    for position, segment in enumerate(plan["segments"]):
        if segment["kind"] not in ("bridge", "closing"):
            continue
        text = segment["text_zh"]
        aiff = tts_dir / f"card-{position:02d}.aiff"
        _say(text, cfg.highlights_zh_voice, aiff)
        voice_ms = round(_duration(ffprobe, aiff) * 1000)
        cards[str(position)] = {
            "audio": f"tts/card-{position:02d}.aiff", "text_zh": text,
            "voice_ms": voice_ms,
            "card_ms": max(round(CARD_MIN_S * 1000),
                           voice_ms + round(CARD_TAIL_S * 1000))}
    manifest = {"intro": intro, "cards": cards}
    (tts_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"[highlights] tts: intro {intro['total_ms'] / 1000:.1f}s, "
          f"{len(cards)} voice card(s)")
    return manifest


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
