"""Japanese transcription: faster-whisper + kotoba-whisper-v2.0
-> <out>/xxx.ja.srt"""

import json
import sys
import time
from pathlib import Path

import srt
from tqdm import tqdm


def _is_hallucination(text: str, avg_logprob: float, no_speech_prob: float,
                      prev_text: str) -> bool:
    """Flag low-confidence silence or repetition of the last accepted segment."""
    if no_speech_prob > 0.6 and avg_logprob < -0.8:
        return True
    if text and text == prev_text:
        return True
    return False


_SENT_END = tuple("。！？!?")


def _split_segment(start: float, end: float, text: str,
                   max_chars: int = 20) -> list[tuple[float, float, str]]:
    """Split a long segment at sentence-ending punctuation; timestamps are
    distributed linearly by character count. Segments with no punctuation
    that are still very long are hard-split at max_chars so a whole
    paragraph never stays on screen at once."""
    parts, buf = [], ""
    for ch in text:
        buf += ch
        if ch in _SENT_END:
            parts.append(buf)
            buf = ""
    if buf:
        parts.append(buf)
    final: list[str] = []
    for p in parts:
        while len(p) > max_chars * 2:
            final.append(p[:max_chars])
            p = p[max_chars:]
        final.append(p)
    if len(final) <= 1:
        return [(start, end, text)]

    total_chars = sum(len(p) for p in final)
    out, cursor = [], start
    for p in final:
        dur = (end - start) * len(p) / total_chars
        out.append((cursor, min(end, cursor + dur), p))
        cursor += dur
    return out


_MODELS: dict = {}


def _get_model(model_id: str):
    """Cache one model instance per ID; batch runs load it only once."""
    from faster_whisper import WhisperModel

    if model_id not in _MODELS:
        _MODELS[model_id] = WhisperModel(model_id, device="cpu",
                                         compute_type="int8",
                                         local_files_only=True)
    return _MODELS[model_id]


def transcribe(media: Path, out_dir: Path, model_id: str) -> tuple[Path, int]:
    """Write Japanese SRT and recognition diagnostics into an existing directory.

    Use a locally cached model and return the SRT path plus the number of
    rejected segments. The adjacent JSON contains ASR diagnostics, not vocab.
    """
    model = _get_model(model_id)
    segments, info = model.transcribe(
        str(media),
        language="ja",
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500, threshold=0.5),
        condition_on_previous_text=False,
    )

    subs, debug, dropped, prev_text = [], [], 0, ""
    t0 = time.time()
    with tqdm(total=round(info.duration, 1), unit="s",
              desc=f"Transcribing {media.name}",
              bar_format="{l_bar}{bar}| {n:.0f}/{total:.0f}s") as bar:
        for seg in segments:
            bar.update(max(0.0, round(seg.end, 1) - bar.n))
            text = seg.text.strip()
            if not text:
                continue
            if _is_hallucination(text, seg.avg_logprob, seg.no_speech_prob,
                                 prev_text):
                dropped += 1
                continue
            prev_text = text
            for s, e, part in _split_segment(seg.start, seg.end, text):
                subs.append(srt.Subtitle(
                    index=len(subs) + 1,
                    start=srt.timedelta(seconds=s),
                    end=srt.timedelta(seconds=e),
                    content=part,
                ))
                debug.append({"start": s, "end": e, "text": part,
                              "avg_logprob": seg.avg_logprob,
                              "no_speech_prob": seg.no_speech_prob})
    if dropped:
        print(f"[transcribe] filtered {dropped} suspected hallucination "
              f"segment(s)", file=sys.stderr)

    out_srt = out_dir / f"{media.stem}.ja.srt"
    out_srt.write_text(srt.compose(subs), encoding="utf-8")
    out_srt.with_suffix(".json").write_text(
        json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[transcribe] {len(subs)} subtitles -> {out_srt} "
          f"({time.time() - t0:.0f}s)")
    return out_srt, dropped
