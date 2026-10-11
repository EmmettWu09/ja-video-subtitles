"""ffmpeg rendering: title cards, event segments, clips, and the essence.

Every segment is rendered from the original source video with uniform
parameters; finished positions accumulate from measured media durations.
Failed renders never replace existing artifacts (temp file + replace).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from ..ffmpeg_util import (escape_filter_path, escape_filter_value,
                           probe_duration)
from . import timeline

CARD_BITRATE = "4M"


def _run_ffmpeg(ffmpeg: Path, cmd: list[str], what: str) -> None:
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8",
                                errors="replace") as err_file:
        try:
            proc = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                                  stderr=err_file, timeout=1800)
        except OSError as e:
            raise RuntimeError(f"could not start ffmpeg for {what}: {e}") from e
        if proc.returncode != 0:
            err_file.seek(0)
            raise RuntimeError(
                f"ffmpeg {what} failed (exit code {proc.returncode}):\n"
                f"{err_file.read()[-2000:]}")


def _probe(ffprobe: Path, media: Path) -> float:
    return probe_duration(ffprobe, media)


def _stream_info(ffprobe: Path, video: Path) -> dict:
    result = subprocess.run(
        [str(ffprobe), "-v", "error", "-show_entries",
         "stream=codec_type,width,height,avg_frame_rate", "-of", "json",
         str(video)],
        capture_output=True, text=True, timeout=60)
    info = {"width": 1280, "height": 720, "fps": 30, "audio": False}
    try:
        streams = json.loads(result.stdout).get("streams", [])
    except ValueError:
        streams = []
    for stream in streams:
        if stream.get("codec_type") == "video" and "width" in stream:
            info["width"] = stream["width"]
            info["height"] = stream["height"]
            rate = stream.get("avg_frame_rate", "30/1")
            try:
                num, _, den = rate.partition("/")
                fps = round(float(num) / float(den or 1))
                info["fps"] = fps if fps > 0 else 30
            except ValueError:
                pass
        elif stream.get("codec_type") == "audio":
            info["audio"] = True
    return info


def _subtitles_vf(srt_path: Path, cfg, fps: int) -> str:
    return (f"subtitles={escape_filter_path(srt_path)}"
            f":force_style={escape_filter_value(cfg.force_style)}"
            f",fps={fps},format=yuv420p")


def _write_cue_srt(cues: list[dict], path: Path) -> None:
    text = timeline.compose_srt(cues)
    if not timeline.valid_srt(text):
        raise RuntimeError(f"generated an invalid SRT for {path.name}")
    path.write_text(text, encoding="utf-8")


def _render_card(text: str, duration_s: float, out: Path, ffmpeg: Path,
                 cfg, width: int, height: int, fps: int,
                 voice: Path | None = None) -> None:
    """A title card: colored background, one burned caption, uniform A/V."""
    cue_srt = out.with_suffix(".card.srt")
    _write_cue_srt([{"start_ms": 0, "end_ms": round(duration_s * 1000),
                     "ja": "", "zh": text}], cue_srt)
    cmd = [str(ffmpeg), "-y", "-f", "lavfi", "-i",
           f"color=c=black:s={width}x{height}:r={fps}:d={duration_s:.3f}"]
    if voice is not None:
        cmd += ["-i", str(voice)]
        audio_filter = f"apad,loudnorm,atrim=0:{duration_s:.3f}"
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        audio_filter = f"atrim=0:{duration_s:.3f}"
    cmd += ["-map", "0:v", "-map", "1:a", "-vf",
            _subtitles_vf(cue_srt, cfg, fps),
            "-af", audio_filter,
            "-c:v", "h264_videotoolbox", "-b:v", CARD_BITRATE,
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-t", f"{duration_s:.3f}", str(out)]
    _run_ffmpeg(ffmpeg, cmd, f"title card render ({out.name})")
    cue_srt.unlink(missing_ok=True)


def _render_event(video: Path, start_ms: int, end_ms: int, cue_srt: Path | None,
                  out: Path, ffmpeg: Path, cfg, fps: int,
                  has_audio: bool) -> None:
    """Cut a source range, burn bilingual subtitles, normalize loudness."""
    start_s, duration_s = start_ms / 1000, (end_ms - start_ms) / 1000
    vf = (f"fps={fps},format=yuv420p" if cue_srt is None
          else _subtitles_vf(cue_srt, cfg, fps))
    cmd = [str(ffmpeg), "-y", "-ss", f"{start_s:.3f}", "-t", f"{duration_s:.3f}",
           "-i", str(video)]
    if has_audio:
        cmd += ["-map", "0:v", "-map", "0:a", "-af", "loudnorm"]
    else:
        cmd += ["-f", "lavfi", "-t", f"{duration_s:.3f}", "-i",
                "anullsrc=r=44100:cl=stereo",
                "-map", "0:v", "-map", "1:a"]
    cmd += ["-vf", vf, "-c:v", "h264_videotoolbox", "-b:v", cfg.video_bitrate,
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            str(out)]
    _run_ffmpeg(ffmpeg, cmd, f"event segment render ({out.name})")


def _render_intro(video: Path, source_start_ms: int, intro: dict,
                  hdir: Path, out: Path, ffmpeg: Path, cfg, fps: int,
                  work_dir: Path) -> None:
    """Opening footage whose audio track is entirely the summary voice-over."""
    duration_s = intro["total_ms"] / 1000
    cue_srt = work_dir / f"{out.stem}.intro.srt"
    _write_cue_srt(intro["sentences"], cue_srt)
    cmd = [str(ffmpeg), "-y", "-ss", f"{source_start_ms / 1000:.3f}",
           "-t", f"{duration_s:.3f}", "-i", str(video),
           "-i", str(hdir / intro["audio"]),
           "-map", "0:v", "-map", "1:a",
           "-vf", _subtitles_vf(cue_srt, cfg, fps),
           "-c:v", "h264_videotoolbox", "-b:v", cfg.video_bitrate,
           "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
           "-t", f"{duration_s:.3f}", str(out)]
    _run_ffmpeg(ffmpeg, cmd, "essence intro render")
    cue_srt.unlink(missing_ok=True)


def _concat(segments: list[Path], out: Path, ffmpeg: Path, cfg) -> None:
    inputs = [item for seg in segments for item in ("-i", str(seg))]
    joined = "".join(f"[{k}:v][{k}:a]" for k in range(len(segments)))
    graph = f"{joined}concat=n={len(segments)}:v=1:a=1[v][a]"
    cmd = [str(ffmpeg), "-y", *inputs, "-filter_complex", graph,
           "-map", "[v]", "-map", "[a]",
           "-c:v", "h264_videotoolbox", "-b:v", cfg.video_bitrate,
           "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
           str(out)]
    _run_ffmpeg(ffmpeg, cmd, f"concat of {len(segments)} segment(s)")


def _replace_rendered(ffmpeg: Path, segments: list[Path], final: Path,
                      cfg) -> None:
    """Concat into a temp file and replace only on success."""
    partial = final.with_name(f".{final.name}.partial.mp4")
    try:
        _concat(segments, partial, ffmpeg, cfg)
        os.replace(partial, final)
    finally:
        partial.unlink(missing_ok=True)


def render_clips(video: Path, entries: list, bounds: list[dict], hdir: Path,
                 cfg, ffmpeg: Path, ffprobe: Path) -> list[dict]:
    """Independent clips: ~3s Chinese title card + the complete event."""
    info = _stream_info(ffprobe, video)
    work = hdir / "work"
    clips = []
    for number, bound in enumerate(bounds, 1):
        name = f"clip-{number:03d}"
        card = work / f"{name}-card.mp4"
        _render_card(bound["title_zh"], timeline.CARD_NOMINAL_MS / 1000,
                     card, ffmpeg, cfg, info["width"], info["height"],
                     info["fps"])
        card_ms = round(_probe(ffprobe, card) * 1000)
        cue_srt = work / f"{name}.event.srt"
        _write_cue_srt(timeline.intersect_cues(
            entries, bound["start_index"], bound["end_index"],
            bound["start_ms"], bound["end_ms"], 0), cue_srt)
        event = work / f"{name}-event.mp4"
        _render_event(video, bound["start_ms"], bound["end_ms"], cue_srt,
                      event, ffmpeg, cfg, info["fps"], info["audio"])
        cue_srt.unlink(missing_ok=True)
        final = hdir / "clips" / f"{name}.mp4"
        _replace_rendered(ffmpeg, [card, event], final, cfg)
        duration_ms = round(_probe(ffprobe, final) * 1000)
        cues = ([{"start_ms": 0, "end_ms": card_ms, "ja": "",
                  "zh": bound["title_zh"]}]
                + timeline.intersect_cues(
                    entries, bound["start_index"], bound["end_index"],
                    bound["start_ms"], bound["end_ms"], card_ms))
        srt_path = hdir / "subtitles" / "clips" / f"{name}.srt"
        _write_cue_srt(cues, srt_path)
        clips.append({"clip": name, "event": bound["event"],
                      "type": bound["type"], "title_zh": bound["title_zh"],
                      "reason_zh": bound["reason_zh"],
                      "context_zh": bound["context_zh"],
                      "start_index": bound["start_index"],
                      "end_index": bound["end_index"],
                      "source_start_ms": bound["start_ms"],
                      "source_end_ms": bound["end_ms"],
                      "file": f"clips/{name}.mp4",
                      "srt": f"subtitles/clips/{name}.srt",
                      "duration_ms": duration_ms})
        print(f"[highlights] clip {name}: {bound['title_zh']} "
              f"({duration_ms / 1000:.0f}s)", flush=True)
    return clips


def render_essence(video: Path, entries: list, plan: dict, manifest: dict,
                   hdir: Path, cfg, ffmpeg: Path, ffprobe: Path) -> dict:
    """Render every segment from source material, measure, and concat.

    Returns the final plan: out positions accumulate from measured segment
    durations, and the exported SRT uses the same boundaries as the video.
    """
    info = _stream_info(ffprobe, video)
    work = hdir / "work"
    rendered: list[Path] = []
    cues: list[dict] = []
    cursor = 0
    for position, segment in enumerate(plan["segments"]):
        out = work / f"seg-{position:02d}.mp4"
        kind = segment["kind"]
        if kind == "intro":
            intro = manifest["intro"]
            _render_intro(video, segment["source_start_ms"], intro, hdir,
                          out, ffmpeg, cfg, info["fps"], work)
            segment["source_end_ms"] = (segment["source_start_ms"]
                                        + intro["total_ms"])
        elif kind == "event":
            cue_srt = work / f"seg-{position:02d}.event.srt"
            _write_cue_srt(timeline.intersect_cues(
                entries, segment["start_index"], segment["end_index"],
                segment["source_start_ms"], segment["source_end_ms"], 0),
                cue_srt)
            _render_event(video, segment["source_start_ms"],
                          segment["source_end_ms"], cue_srt, out, ffmpeg, cfg,
                          info["fps"], info["audio"])
            cue_srt.unlink(missing_ok=True)
        else:  # bridge / closing title cards with Chinese voice-over
            card = manifest["cards"][str(position)]
            _render_card(card["text_zh"], card["card_ms"] / 1000, out,
                         ffmpeg, cfg, info["width"], info["height"],
                         info["fps"], voice=hdir / card["audio"])
        duration_ms = round(_probe(ffprobe, out) * 1000)
        segment["out_start_ms"] = cursor
        segment["out_end_ms"] = cursor + duration_ms
        segment["duration_ms"] = duration_ms
        if kind == "intro":
            for sentence in manifest["intro"]["sentences"]:
                cues.append({"start_ms": sentence["start_ms"] + cursor,
                             "end_ms": sentence["end_ms"] + cursor,
                             "ja": sentence["ja"], "zh": sentence["zh"]})
        elif kind == "event":
            cues.extend(timeline.intersect_cues(
                entries, segment["start_index"], segment["end_index"],
                segment["source_start_ms"], segment["source_end_ms"], cursor))
        else:
            card = manifest["cards"][str(position)]
            cues.append({"start_ms": cursor, "end_ms": cursor + duration_ms,
                         "ja": "", "zh": card["text_zh"]})
        rendered.append(out)
        cursor += duration_ms
        print(f"[highlights] essence segment {kind} "
              f"{duration_ms / 1000:.1f}s", flush=True)
    if not rendered:
        raise RuntimeError("essence plan has no segments to render")
    final = hdir / "highlights.mp4"
    _replace_rendered(ffmpeg, rendered, final, cfg)
    plan["total_ms"] = cursor
    srt_text = timeline.compose_srt(cues)
    if not timeline.valid_srt(srt_text):
        raise RuntimeError("generated an invalid highlights.srt")
    (hdir / "subtitles" / "highlights.srt").write_text(srt_text,
                                                       encoding="utf-8")
    print(f"[highlights] essence -> {final} ({cursor / 1000:.0f}s)")
    return plan
