"""Human-facing artifacts: summary.md, index.html, and report.json checks."""

from __future__ import annotations

import html
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import timeline

SUBTITLE_NOTICE = "视频已含字幕；SRT 供编辑或其他用途，观看时关闭外挂字幕"


def _mmss(milliseconds: int) -> str:
    seconds = milliseconds // 1000
    return f"{seconds // 60:02}:{seconds % 60:02}"


def _probe_media(ffprobe: Path, path: Path) -> dict:
    result = subprocess.run(
        [str(ffprobe), "-v", "error", "-show_entries",
         "stream=codec_type:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60)
    streams, duration = [], None
    try:
        data = json.loads(result.stdout)
        streams = [s.get("codec_type") for s in data.get("streams", [])]
        duration = float(data["format"]["duration"])
    except (ValueError, KeyError, TypeError):
        pass
    return {"streams": streams, "duration_ms":
            round(duration * 1000) if duration is not None else None}


def _check_media(hdir: Path, relatives: list[str], ffprobe: Path,
                 anomalies: list[str]) -> list[dict]:
    checks = []
    for relative in relatives:
        path = hdir / relative
        check = {"file": relative, "exists": path.is_file()}
        if check["exists"]:
            probe = _probe_media(ffprobe, path)
            check["duration_ms"] = probe["duration_ms"]
            check["video_stream"] = "video" in probe["streams"]
            check["audio_stream"] = "audio" in probe["streams"]
            if not check["video_stream"]:
                anomalies.append(f"{relative}: no video stream")
            if probe["duration_ms"] is None:
                anomalies.append(f"{relative}: cannot read duration")
        else:
            anomalies.append(f"{relative}: expected product is missing")
        checks.append(check)
    return checks


def _check_srts(hdir: Path, relatives: list[str], media_ms: dict[str, int],
                anomalies: list[str]) -> list[dict]:
    checks = []
    for relative in relatives:
        path = hdir / relative
        check = {"file": relative, "exists": path.is_file()}
        if check["exists"]:
            text = path.read_text(encoding="utf-8")
            valid = timeline.valid_srt(text)
            check["valid"] = valid
            if not valid:
                anomalies.append(f"{relative}: invalid SRT "
                                 "(empty cues or bad timestamps)")
                checks.append(check)
                continue
            import srt
            cues = list(srt.parse(text))
            check["cues"] = len(cues)
            last_end = round(cues[-1].end.total_seconds() * 1000)
            check["last_end_ms"] = last_end
            bound = media_ms.get(relative)
            if bound is not None and last_end > bound + 1000:
                anomalies.append(
                    f"{relative}: subtitles run past the media end "
                    f"({last_end}ms > {bound}ms)")
        else:
            anomalies.append(f"{relative}: expected SRT is missing")
        checks.append(check)
    return checks


def _summary_md(video_name: str, summary: dict, clips_plan: list[dict],
                selection, essence_seconds: float | None,
                essence_incomplete: bool, note: str) -> str:
    lines = [f"# 课堂总结：{video_name}", ""]
    lines += [f"- 主题：{summary.get('theme_zh', '（未生成）')}",
              f"- 练习内容：{summary.get('practice_zh', '（未生成）')}", ""]
    if summary.get("expressions_zh"):
        lines += ["## 重点表达", ""]
        lines += [f"- {item}" for item in summary["expressions_zh"]] + [""]
    lines += ["## 表现亮点", ""]
    if clips_plan:
        for clip in clips_plan:
            lines.append(
                f"- **{clip['title_zh']}**（{clip['type']}，原视频 "
                f"{_mmss(clip['source_start_ms'])}–"
                f"{_mmss(clip['source_end_ms'])}）：{clip['reason_zh']}")
    else:
        lines.append("（本节课未筛选出合格的高光事件）")
    lines.append("")
    if summary.get("highlights_zh"):
        lines += ["## 解说摘要", ""]
        lines += [f"- {item}" for item in summary["highlights_zh"]] + [""]
    if selection.review:
        lines += ["## 待复核", ""]
        for item in selection.review:
            cand = item["candidate"]
            lines.append(f"- #{cand['start_index']}-{cand['end_index']} "
                         f"{cand['type']}：{item['reason']}")
        lines.append("")
    lines += ["## 精华版", ""]
    if essence_incomplete:
        lines.append(f"精华版未完成：{note or '原因见 report.json'}。"
                     "独立切片与分析产物已保留。")
    elif essence_seconds is not None:
        lines.append(f"精华版时长 {essence_seconds:.0f} 秒。"
                     + (f"{note}" if note else ""))
    if note and not essence_incomplete and essence_seconds is None:
        lines.append(note)
    lines.append("")
    lines.append(f"> {SUBTITLE_NOTICE}")
    return "\n".join(lines) + "\n"


def _index_html(video_name: str, clips_plan: list[dict], selection,
                plan: dict | None, essence_incomplete: bool, note: str,
                anomalies: list[str]) -> str:
    esc = html.escape
    parts = ["<!DOCTYPE html><html lang=\"zh-CN\"><head>",
             "<meta charset=\"utf-8\">",
             f"<title>课堂高光 - {esc(video_name)}</title>",
             "<style>body{font-family:-apple-system,sans-serif;max-width:56em;"
             "margin:2em auto;padding:0 1em;line-height:1.6}"
             "table{border-collapse:collapse;width:100%}"
             "td,th{border:1px solid #ccc;padding:.4em;text-align:left}"
             ".notice{background:#fff8dc;padding:.8em;border:1px solid #e0c060}"
             ".warn{color:#a33}</style></head><body>",
             f"<h1>课堂高光：{esc(video_name)}</h1>",
             f"<p class=\"notice\">{esc(SUBTITLE_NOTICE)}</p>"]
    if essence_incomplete:
        parts.append(f"<p class=\"warn\">精华版未完成：{esc(note or '原因见 report.json')}；"
                     "以下独立切片与分析产物已保留。</p>")
    elif plan is not None:
        essence_name = f"{Path(video_name).stem}.highlights.mp4"
        srt_name = f"{Path(video_name).stem}.highlights.srt"
        parts.append(f"<h2>精华版（{plan['total_ms'] // 1000} 秒）</h2>")
        parts.append(f'<p><a href="../{esc(essence_name)}">{esc(essence_name)}</a> · '
                     f'<a href="subtitles/{esc(srt_name)}">配套 SRT</a></p>')
        if plan.get("draft"):
            parts.append(f"<p class=\"warn\">{esc(plan['draft'])}</p>")
    parts.append(f"<h2>独立高光切片（{len(clips_plan)}）</h2>")
    if clips_plan:
        parts.append("<table><tr><th>切片</th><th>标题</th><th>类型</th>"
                     "<th>源区间</th><th>入选理由</th><th>文件</th></tr>")
        for clip in clips_plan:
            parts.append(
                f"<tr><td>{esc(clip['clip'])}</td>"
                f"<td>{esc(clip['title_zh'])}</td>"
                f"<td>{esc(clip['type'])}</td>"
                f"<td>{_mmss(clip['source_start_ms'])}–"
                f"{_mmss(clip['source_end_ms'])}</td>"
                f"<td>{esc(clip['reason_zh'])}</td>"
                f"<td><a href=\"{esc(clip['file'])}\">mp4</a> · "
                f"<a href=\"{esc(clip['srt'])}\">srt</a></td></tr>")
        parts.append("</table>")
    else:
        parts.append("<p>本节课未筛选出合格的高光事件。</p>")
    if selection.review:
        parts.append(f"<h2>待复核（{len(selection.review)}）</h2><ul>")
        for item in selection.review:
            cand = item["candidate"]
            parts.append(f"<li>#{cand['start_index']}-{cand['end_index']} "
                         f"{esc(cand['type'])}：{esc(item['reason'])}</li>")
        parts.append("</ul>")
    if anomalies:
        parts.append("<h2>异常提示</h2><ul>")
        parts += [f"<li class=\"warn\">{esc(item)}</li>" for item in anomalies]
        parts.append("</ul>")
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


def write_all(hdir: Path, video: Path, entries: list, outcome, selection,
              bounds: list[dict], clips_plan: list[dict], plan: dict | None,
              essence_incomplete: bool, note: str, ffmpeg: Path,
              ffprobe: Path) -> dict:
    """Write summary.md, index.html and report.json; return the report.

    The essence video lives one level above ``hdir`` (``../<stem>.highlights.mp4``),
    so media checks reference it with a parent-relative path.
    """
    anomalies: list[str] = []
    flagged = [{"index": e.index, "flags": e.flags} for e in entries if e.flags]
    if flagged:
        anomalies.append(f"{len(flagged)} subtitle cue(s) flagged during "
                         "pairing (see transcript.flagged)")
    essence_rel = f"../{video.stem}.highlights.mp4"
    essence_srt_rel = f"subtitles/{video.stem}.highlights.srt"
    media_files = [clip["file"] for clip in clips_plan]
    if plan is not None:
        media_files.append(essence_rel)
    media_checks = _check_media(hdir, media_files, ffprobe, anomalies)
    media_ms = {}
    for clip, check in zip(clips_plan, media_checks):
        if check.get("duration_ms") is not None:
            media_ms[clip["srt"]] = check["duration_ms"]
    if plan is not None and media_checks[-1].get("duration_ms") is not None:
        media_ms[essence_srt_rel] = media_checks[-1]["duration_ms"]
    srt_files = [clip["srt"] for clip in clips_plan]
    if plan is not None:
        srt_files.append(essence_srt_rel)
    srt_checks = _check_srts(hdir, srt_files, media_ms, anomalies)
    if plan is not None and media_ms.get(essence_srt_rel) is not None:
        declared = plan["total_ms"]
        actual = media_ms[essence_srt_rel]
        if abs(actual - declared) > 1500:
            anomalies.append(
                f"{video.stem}.highlights.mp4 duration {actual}ms differs "
                f"from the plan timeline {declared}ms")
    for clip, check in zip(clips_plan, media_checks):
        expected = (clip["source_end_ms"] - clip["source_start_ms"]
                    + timeline.CARD_NOMINAL_MS)
        if (check.get("duration_ms") is not None
                and abs(check["duration_ms"] - expected) > 3000):
            anomalies.append(
                f"{clip['file']}: duration {check['duration_ms']}ms differs "
                f"from the expected {expected}ms")

    essence_seconds = plan["total_ms"] / 1000 if plan is not None else None
    (hdir / "summary.md").write_text(
        _summary_md(video.name, outcome.summary, clips_plan, selection,
                    essence_seconds, essence_incomplete, note),
        encoding="utf-8")
    (hdir / "index.html").write_text(
        _index_html(video.name, clips_plan, selection, plan,
                    essence_incomplete, note, anomalies),
        encoding="utf-8")

    report = {
        "video": video.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "essence_incomplete": essence_incomplete,
        "note": note,
        "essence_seconds": essence_seconds,
        "clip_count": len(clips_plan),
        "counts": {"candidates": len(outcome.candidates),
                   "kept": len(selection.kept),
                   "review": len(selection.review),
                   "discarded": len(selection.discarded)},
        "transcript": {"entries": len(entries), "flagged": flagged},
        "media_checks": media_checks,
        "srt_checks": srt_checks,
        "anomalies": anomalies,
    }
    (hdir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return report
