"""End-to-end highlights test with real ffmpeg/say and a fake model client.

Generates a short synthetic video and small SRTs, then runs generate() for
real. Skips when ffmpeg, `say`, or the configured voices are unavailable.
No network or real DeepSeek API is ever touched.
"""

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from ja_video_subtitles.config import (DEFAULT_FORCE_STYLE,
                                       DEFAULT_USER_TEMPLATE, Config)
from ja_video_subtitles.ffmpeg_util import find_ffmpeg, find_ffprobe, probe_duration
from ja_video_subtitles.highlights import generate
from ja_video_subtitles.highlights.timeline import valid_srt

FFMPEG = find_ffmpeg()
SAY = shutil.which("say")


def _voices():
    if SAY is None:
        return set()
    try:
        result = subprocess.run([SAY, "-v", "?"], capture_output=True,
                                text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return {line.split()[0] for line in result.stdout.splitlines()
            if line.split()}


VOICES = _voices()
REQUIRED = {"Kyoko", "Tingting"}

pytestmark = pytest.mark.skipif(
    FFMPEG is None or find_ffprobe(FFMPEG) is None or not REQUIRED <= VOICES,
    reason="requires ffmpeg with libass, ffprobe, `say`, and the "
           "Kyoko/Tingting voices")


def make_cfg(**overrides):
    values = dict(base_url="https://example.invalid", api_key="sk-test",
                  model="test-model", asr_model_id="test", prompt_system="",
                  prompt_user_template=DEFAULT_USER_TEMPLATE,
                  force_style=DEFAULT_FORCE_STYLE, video_bitrate="4M")
    values.update(overrides)
    return Config(**values)


def response(content):
    message = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=message,
                                                    finish_reason="stop")])


CANDIDATE = json.dumps({
    "topics": ["课堂练习"],
    "candidates": [{"type": "完整表达", "start_index": 3, "end_index": 5,
                    "title_zh": "完整回答问题", "reason_zh": "学生独立完成了完整回答",
                    "context_zh": "老师在前一条提问", "confidence": "high"}]},
    ensure_ascii=False)

SUMMARY = json.dumps({
    "theme_zh": "课堂练习", "practice_zh": "问答练习",
    "expressions_zh": ["～です"], "highlights_zh": ["完整回答问题"],
    "intro_sentences": [{"ja": "今日は練習をしました。", "zh": "今天做了练习。"},
                        {"ja": "よくできました。", "zh": "完成得很好。"}],
    "closing_zh": "下节课见。"}, ensure_ascii=False)


class FakeClient:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    def create(self, model, messages, **kwargs):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class ExplodingClient:
    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    def create(self, *args, **kwargs):
        raise AssertionError("the model must not be called on a cache hit")


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    root = tmp_path_factory.mktemp("highlights-media")
    video = root / "lesson.mp4"
    subprocess.run([
        str(FFMPEG), "-hide_banner", "-loglevel", "error", "-f", "lavfi",
        "-i", "testsrc=size=640x360:rate=30:duration=40", "-f", "lavfi",
        "-i", "sine=frequency=440:duration=40",
        "-c:v", "h264_videotoolbox", "-pix_fmt", "yuv420p", "-c:a", "aac",
        str(video)], check=True, capture_output=True, timeout=120)

    def srt_text(words):
        cues = []
        for index in range(1, 9):
            start, end = (index - 1) * 5, (index - 1) * 5 + 2
            cues.append(f"{index}\n00:00:{start:02d},000 --> "
                        f"00:00:{end:02d},000\n{words[index - 1]}\n")
        return "\n".join(cues) + "\n"

    ja = root / "lesson.ja.srt"
    zh = root / "lesson.zh.srt"
    ja.write_text(srt_text([f"テスト{i}です。" for i in range(1, 9)]),
                  encoding="utf-8")
    zh.write_text(srt_text([f"测试句子{i}。" for i in range(1, 9)]),
                  encoding="utf-8")
    return video, ja, zh


LAYOUT = ("summary.md", "index.html",
          "clips/lesson.clip-001.mp4", "subtitles/lesson.highlights.srt",
          "subtitles/clips/lesson.clip-001.srt", "analysis/transcript.json",
          "analysis/candidates.json", "plans/clips.json",
          "plans/highlights.json", "state.json", "report.json")


def test_generate_end_to_end_and_resume(media, tmp_path):
    video, ja, zh = media
    video_dir = tmp_path / "out" / "lesson"
    video_dir.mkdir(parents=True)
    client = FakeClient(response(CANDIDATE), response(SUMMARY))
    result = generate(video, ja, zh, video_dir, make_cfg(), FFMPEG,
                      client=client)

    hdir = video_dir / "highlights"
    assert result.output_dir == hdir
    for relative in LAYOUT:
        assert (hdir / relative).is_file(), f"missing {relative}"
    essence_path = video_dir / "lesson.highlights.mp4"
    assert essence_path.is_file()  # next to the burned video, not in highlights/
    assert result.clip_count == 1
    assert not result.essence_incomplete
    assert result.essence_seconds is not None
    assert client.calls == 2  # one chunk analysis + one synthesis

    ffprobe = find_ffprobe(FFMPEG)
    essence = probe_duration(ffprobe, essence_path)
    assert essence == pytest.approx(result.essence_seconds, abs=1.5)
    # Intro (15-25s) + ~15s event + ~3s closing.
    assert 25 <= essence <= 60
    clip = probe_duration(ffprobe, hdir / "clips" / "lesson.clip-001.mp4")
    assert 15 <= clip <= 25  # ~3s title card + ~15s event

    for relative in ("subtitles/lesson.highlights.srt",
                     "subtitles/clips/lesson.clip-001.srt"):
        text = (hdir / relative).read_text(encoding="utf-8")
        assert valid_srt(text), f"invalid SRT: {relative}"
        assert "テスト" in text
    # Intro region carries the summary narration, not classroom dialogue.
    highlights_srt = (hdir / "subtitles" / "lesson.highlights.srt") \
        .read_text(encoding="utf-8")
    assert "今日は練習をしました。" in highlights_srt

    index_html = (hdir / "index.html").read_text(encoding="utf-8")
    assert "观看时关闭外挂字幕" in index_html
    assert "完整回答问题" in index_html
    assert 'href="../lesson.highlights.mp4"' in index_html
    summary_md = (hdir / "summary.md").read_text(encoding="utf-8")
    assert "课堂练习" in summary_md
    assert "草稿" in summary_md  # short material: marked as a shorter draft

    report = json.loads((hdir / "report.json").read_text(encoding="utf-8"))
    assert report["clip_count"] == 1
    assert not report["essence_incomplete"]
    assert all(check["valid"] for check in report["srt_checks"])
    plan = json.loads((hdir / "plans" / "highlights.json")
                      .read_text(encoding="utf-8"))
    assert plan["total_ms"] == pytest.approx(essence * 1000, abs=1500)
    positions = [(seg["out_start_ms"], seg["out_end_ms"])
                 for seg in plan["segments"]]
    assert positions[0][0] == 0
    for (prev_start, prev_end), (next_start, _) in zip(positions,
                                                       positions[1:]):
        assert prev_end == next_start  # one continuous timeline
        assert prev_end > prev_start

    # Resume with identical inputs: no API call, products reused.
    resumed = generate(video, ja, zh, video_dir, make_cfg(), FFMPEG,
                       client=ExplodingClient())
    assert resumed.clip_count == 1
    assert resumed.essence_seconds == pytest.approx(result.essence_seconds,
                                                    abs=0.1)

    # force=True reruns everything (needs the model again).
    forced = generate(video, ja, zh, video_dir, make_cfg(), FFMPEG,
                      client=FakeClient(response(CANDIDATE),
                                        response(SUMMARY)), force=True)
    assert forced.clip_count == 1
    assert not forced.essence_incomplete


def test_essence_failure_keeps_clips_and_recovers(media, tmp_path):
    video, ja, zh = media
    video_dir = tmp_path / "out" / "lesson"
    video_dir.mkdir(parents=True)
    cfg = make_cfg(highlights_ja_voice="No-Such-Voice")
    client = FakeClient(response(CANDIDATE), response(SUMMARY))
    result = generate(video, ja, zh, video_dir, cfg, FFMPEG, client=client)

    hdir = video_dir / "highlights"
    essence_path = video_dir / "lesson.highlights.mp4"
    assert result.essence_incomplete
    assert result.essence_seconds is None
    assert result.clip_count == 1
    assert (hdir / "clips" / "lesson.clip-001.mp4").is_file()
    assert not essence_path.exists()
    summary_md = (hdir / "summary.md").read_text(encoding="utf-8")
    assert "精华版未完成" in summary_md
    index_html = (hdir / "index.html").read_text(encoding="utf-8")
    assert "精华版未完成" in index_html
    report = json.loads((hdir / "report.json").read_text(encoding="utf-8"))
    assert report["essence_incomplete"]

    # Fixing the voice resumes from the failed stage without new API calls.
    recovered = generate(video, ja, zh, video_dir, make_cfg(), FFMPEG,
                         client=ExplodingClient())
    assert not recovered.essence_incomplete
    assert recovered.essence_seconds is not None
    assert essence_path.is_file()
    # Clips were reused, not re-rendered: the state file records done stages.
    state = json.loads((hdir / "state.json").read_text(encoding="utf-8"))
    assert state["stages"]["clips"]["status"] == "done"
    assert state["stages"]["render"]["status"] == "done"
