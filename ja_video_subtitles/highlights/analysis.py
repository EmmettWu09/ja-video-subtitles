"""Chunked classroom analysis with strict output validation and selection.

The model only references subtitle indices; times are mapped locally. Raw
responses are preserved under analysis/raw/ for every attempt.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..api_util import chat_options
from .transcript import Entry, by_index

PROMPT_VERSION = 1
CHUNK_MS = 300_000
OVERLAP_MS = 30_000
MAX_RETRIES = 2

HIGHLIGHT_TYPES = ("连贯交流", "完整表达", "主动交流", "老师认可",
                   "学以致用", "自我纠正", "提示后突破", "有趣互动")

# Isolated acknowledgements never count as teacher praise (local check mirrors
# the prompt rule).
_BARE_ACKS = {"はい", "そうですね", "そうです", "うん", "ええ", "ああ", "そう"}

_ANALYSIS_SYSTEM = """你是日语课堂录像分析助手。输入是一节日语初学者课堂的双语字幕片段，每行格式为「#编号 [开始-结束] 日语原文 / 中文译文」。老师与学生身份未知，不要按语言猜测身份，不要假设谁是老师。
任务：从原始字幕中发现值得记录的初学者课堂高光候选。高光类型仅限：连贯交流、完整表达、主动交流、老师认可、学以致用、自我纠正、提示后突破、有趣互动。
规则：
1. 只用 start_index/end_index 引用字幕编号，禁止返回任何时间码；
2. 每个候选必须是一个完整、可独立理解的事件，包含必要的上下文铺垫；同一事件只报一次；
3. 孤立的「はい」「そうですね」等简短应答不能当作老师认可或高光；老师认可必须有具体措辞与上下文；
4. 不要为凑数量拆分普通应答；没有合格候选就返回空列表；
5. 不做发音、流利度等语音层面评价，不把单节课表现解释为长期进步；
6. title_zh 用一句中性中文说明本段话题或看点，reason_zh 说明入选理由，context_zh 说明理解该事件所需的上下文；
7. 证据是否充分用 confidence 标注：证据完整为 "high"，证据不足或需人工复核为 "low"；
8. 只返回 JSON：{"topics": ["本块话题", ...], "candidates": [{"type": "...", "start_index": 0, "end_index": 0, "title_zh": "...", "reason_zh": "...", "context_zh": "...", "confidence": "high"}]}。"""

_SYNTHESIS_SYSTEM = """你是日语课堂总结助手。根据一节课的话题与已确认的高光事件，生成课堂总结与精华版片头摘要。
规则：
1. 只依据给定字幕证据，不编造评价，不断言长期进步；
2. intro_sentences 是精华版片头的日文配音稿：3 到 6 个简短、初学者能懂的日文短句，概括本次主题、练习内容和有字幕证据的亮点，每句附自然的中文译文，总朗读时长控制在 15 到 20 秒；
3. closing_zh 是一句简短的中文收尾语；
4. 只返回 JSON：{"theme_zh": "...", "practice_zh": "...", "expressions_zh": ["..."], "highlights_zh": ["..."], "intro_sentences": [{"ja": "...", "zh": "..."}], "closing_zh": "..."}。"""


@dataclass
class Candidate:
    type: str
    start_index: int
    end_index: int
    title_zh: str
    reason_zh: str
    context_zh: str = ""
    confidence: str = "low"

    def to_dict(self) -> dict:
        return {"type": self.type, "start_index": self.start_index,
                "end_index": self.end_index, "title_zh": self.title_zh,
                "reason_zh": self.reason_zh, "context_zh": self.context_zh,
                "confidence": self.confidence}

    @staticmethod
    def from_dict(data: dict) -> "Candidate":
        return Candidate(data["type"], data["start_index"], data["end_index"],
                         data["title_zh"], data["reason_zh"],
                         data.get("context_zh", ""),
                         data.get("confidence", "low"))


@dataclass
class Outcome:
    candidates: list[Candidate]
    summary: dict
    chunks: list[dict] = field(default_factory=list)


@dataclass
class Selection:
    kept: list[Candidate]
    review: list[dict]
    discarded: list[dict]
    decisions: list[dict]


def _time_text(milliseconds: int) -> str:
    seconds, ms = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02}:{seconds:02}.{ms:03}"


def chunk_entries(entries: list[Entry], chunk_ms: int = CHUNK_MS,
                  overlap_ms: int = OVERLAP_MS) -> list[list[Entry]]:
    """Split into ~5-minute windows with ~30 seconds of shared context."""
    if not entries:
        return []
    step = max(1, chunk_ms - overlap_ms)
    last_start = entries[-1].start_ms
    chunks: list[list[Entry]] = []
    window_start = 0
    while window_start <= last_start:
        window_end = window_start + chunk_ms
        chunk = [entry for entry in entries
                 if window_start <= entry.start_ms < window_end]
        if chunk:
            chunks.append(chunk)
        window_start += step
    return chunks


def _format_lines(chunk: list[Entry]) -> str:
    lines = []
    for entry in chunk:
        span = f"{_time_text(entry.start_ms)}-{_time_text(entry.end_ms)}"
        text = entry.ja if not entry.zh else f"{entry.ja} / {entry.zh}"
        lines.append(f"#{entry.index} [{span}] {text}")
    return "\n".join(lines)


def _call_model(client, cfg, system: str, user: str):
    """One structured-output call; returns (content, finish_reason)."""
    response = client.chat.completions.create(
        model=cfg.model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=0.2,
        response_format={"type": "json_object"},
        **chat_options(cfg),
    )
    choice = response.choices[0]
    return (choice.message.content or "",
            getattr(choice, "finish_reason", None))


def _call_validated(client, cfg, system: str, user: str, parse,
                    raw_dir: Path, label: str):
    """Call, validate, and retry at most MAX_RETRIES times, keeping raw text."""
    errors = []
    for attempt in range(1, MAX_RETRIES + 2):
        raw_path = raw_dir / f"{label}-attempt-{attempt}.txt"
        try:
            content, finish_reason = _call_model(client, cfg, system, user)
            raw_path.write_text(content, encoding="utf-8")
            if finish_reason == "length":
                raise ValueError("model response was truncated "
                                 "(finish_reason=length)")
            if not content.strip():
                raise ValueError("model returned an empty response")
            return parse(content), attempt, raw_path.name
        except Exception as e:  # transport, truncation, or validation errors
            if not raw_path.exists():
                raw_path.write_text(f"<no valid response: {e}>",
                                    encoding="utf-8")
            errors.append(f"attempt {attempt}: {e}")
            if attempt <= MAX_RETRIES:
                print(f"[highlights] {label} invalid ({e}), "
                      f"retry {attempt}/{MAX_RETRIES}")
                time.sleep(1)
    raise RuntimeError(f"highlights analysis failed for {label} after "
                       f"{MAX_RETRIES} retries: {'; '.join(errors)}")


def _is_int(value) -> bool:
    return type(value) is int


def _parse_candidates(text: str, valid_indices: set[int]) -> list[Candidate]:
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("candidates"), list):
        raise ValueError("response must be a JSON object with a candidates list")
    candidates = []
    for item in data["candidates"]:
        if not isinstance(item, dict):
            raise ValueError("each candidate must be an object")
        highlight_type = item.get("type")
        start, end = item.get("start_index"), item.get("end_index")
        if highlight_type not in HIGHLIGHT_TYPES:
            raise ValueError(f"unknown highlight type: {highlight_type!r}")
        if not _is_int(start) or not _is_int(end):
            raise ValueError("candidate indices must be integers")
        if start not in valid_indices or end not in valid_indices:
            raise ValueError(f"candidate references unknown subtitle "
                             f"indices {start}-{end}")
        if start > end:
            raise ValueError(f"candidate range is inverted: {start}-{end}")
        title, reason = item.get("title_zh"), item.get("reason_zh")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("candidate title_zh must be nonempty")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("candidate reason_zh must be nonempty")
        context = item.get("context_zh", "")
        confidence = item.get("confidence", "low")
        if confidence not in ("high", "low"):
            confidence = "low"
        candidates.append(Candidate(highlight_type, start, end, title.strip(),
                                    reason.strip(),
                                    context.strip() if isinstance(context, str)
                                    else "", confidence))
    return candidates


def _parse_summary(text: str) -> dict:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("summary must be a JSON object")
    for key in ("theme_zh", "practice_zh"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"summary {key} must be a nonempty string")
    for key in ("expressions_zh", "highlights_zh"):
        if not isinstance(data.get(key), list) or not all(
                isinstance(item, str) for item in data[key]):
            raise ValueError(f"summary {key} must be a list of strings")
    sentences = data.get("intro_sentences")
    if (not isinstance(sentences, list) or not 1 <= len(sentences) <= 8):
        raise ValueError("summary intro_sentences must contain 1-8 items")
    for sentence in sentences:
        if (not isinstance(sentence, dict)
                or not isinstance(sentence.get("ja"), str)
                or not sentence["ja"].strip()
                or not isinstance(sentence.get("zh"), str)
                or not sentence["zh"].strip()):
            raise ValueError("each intro sentence needs nonempty ja and zh")
    closing = data.get("closing_zh", "")
    return {"theme_zh": data["theme_zh"].strip(),
            "practice_zh": data["practice_zh"].strip(),
            "expressions_zh": [item.strip() for item in data["expressions_zh"]
                               if item.strip()],
            "highlights_zh": [item.strip() for item in data["highlights_zh"]
                              if item.strip()],
            "intro_sentences": [{"ja": s["ja"].strip(), "zh": s["zh"].strip()}
                                for s in sentences],
            "closing_zh": closing.strip() if isinstance(closing, str) else ""}


def analyze(client, cfg, entries: list[Entry], raw_dir: Path) -> Outcome:
    """Analyze every chunk from the raw subtitles, then synthesize a summary."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    valid_indices = {entry.index for entry in entries}
    chunks = chunk_entries(entries)
    candidates: list[Candidate] = []
    chunk_meta: list[dict] = []
    for number, chunk in enumerate(chunks):
        user = _format_lines(chunk)
        found, attempts, raw_name = _call_validated(
            client, cfg, _ANALYSIS_SYSTEM, user,
            lambda text: _parse_candidates(text, valid_indices),
            raw_dir, f"chunk-{number:03d}")
        candidates.extend(found)
        chunk_meta.append({
            "chunk": number,
            "entry_range": [chunk[0].index, chunk[-1].index],
            "attempts": attempts, "raw_response": f"analysis/raw/{raw_name}",
            "candidate_count": len(found)})
        print(f"[highlights] analysis chunk {number + 1}/{len(chunks)}: "
              f"{len(found)} candidate(s)", flush=True)

    digest = "\n".join(
        f"#{cand.start_index}-{cand.end_index} {cand.type} "
        f"{cand.title_zh}: {cand.reason_zh}" for cand in candidates)
    summary_user = (f"课堂字幕共 {len(entries)} 条。\n话题与高光候选：\n"
                    f"{digest or '（无候选）'}")
    summary, attempts, raw_name = _call_validated(
        client, cfg, _SYNTHESIS_SYSTEM, summary_user, _parse_summary,
        raw_dir, "synthesis")
    chunk_meta.append({"chunk": "synthesis", "attempts": attempts,
                       "raw_response": f"analysis/raw/{raw_name}"})
    return Outcome(candidates, summary, chunk_meta)


def _bare_acks_only(candidate: Candidate, index: dict[int, Entry]) -> bool:
    """True when every Japanese line in range is an isolated acknowledgement."""
    texts = [index[i].ja for i in range(candidate.start_index,
                                        candidate.end_index + 1)
             if i in index and index[i].ja.strip()]
    if not texts:
        return False
    normalized = [text.strip().rstrip("。！!、 ") for text in texts]
    return all(text in _BARE_ACKS for text in normalized)


def select(entries: list[Entry], candidates: list[Candidate]) -> Selection:
    """Evidence checks, cross-chunk merge/dedup, and the pending-review list."""
    index = by_index(entries)
    decisions: list[dict] = []
    review: list[dict] = []
    discarded: list[dict] = []
    provisional: list[Candidate] = []
    for candidate in candidates:
        label = f"#{candidate.start_index}-{candidate.end_index} {candidate.type}"
        if (candidate.type == "老师认可"
                and _bare_acks_only(candidate, index)):
            reason = "仅以孤立应答（如「はい」「そうですね」）作为认可证据，舍弃"
            discarded.append({"candidate": candidate.to_dict(), "reason": reason})
            decisions.append({"action": "discarded", "target": label,
                              "reason": reason})
        elif candidate.confidence != "high" or not candidate.context_zh:
            reason = ("证据不足或缺少必要上下文，留待人工复核"
                      if candidate.confidence != "high"
                      else "缺少所需上下文，留待人工复核")
            review.append({"candidate": candidate.to_dict(), "reason": reason})
            decisions.append({"action": "review", "target": label,
                              "reason": reason})
        else:
            provisional.append(candidate)
            decisions.append({"action": "kept", "target": label,
                              "reason": candidate.reason_zh})

    # Merge overlapping ranges: overlap implies the same event reported twice.
    provisional.sort(key=lambda c: (c.start_index, c.end_index))
    kept: list[Candidate] = []
    for candidate in provisional:
        if kept and candidate.start_index <= kept[-1].end_index:
            previous = kept[-1]
            merged = Candidate(
                previous.type, previous.start_index,
                max(previous.end_index, candidate.end_index),
                previous.title_zh,
                f"{previous.reason_zh}；{candidate.reason_zh}",
                previous.context_zh or candidate.context_zh,
                "high" if "high" in (previous.confidence, candidate.confidence)
                else "low")
            decisions.append({
                "action": "merged",
                "target": f"#{merged.start_index}-{merged.end_index} "
                          f"{merged.type}",
                "reason": f"与候选 #{candidate.start_index}-"
                          f"{candidate.end_index} 区间重叠，属于同一事件，合并"})
            kept[-1] = merged
        else:
            kept.append(candidate)
    return Selection(kept, review, discarded, decisions)


def to_json(outcome: Outcome, selection: Selection) -> dict:
    return {"prompt_version": PROMPT_VERSION,
            "chunks": outcome.chunks,
            "candidates": [c.to_dict() for c in outcome.candidates],
            "kept": [c.to_dict() for c in selection.kept],
            "review": selection.review,
            "discarded": selection.discarded,
            "decisions": selection.decisions,
            "summary": outcome.summary}


def outcome_from_json(data: dict) -> Outcome:
    return Outcome([Candidate.from_dict(c) for c in data.get("candidates", [])],
                   data.get("summary", {}),
                   data.get("chunks", []))


def selection_from_json(data: dict) -> Selection:
    return Selection([Candidate.from_dict(c) for c in data.get("kept", [])],
                     data.get("review", []),
                     data.get("discarded", []),
                     data.get("decisions", []))
