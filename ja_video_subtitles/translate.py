"""JA->ZH translation via DeepSeek -> <out>/xxx.zh.srt.

Batches are numbered and the response must align line-by-line; on mismatch
we retry, then recursively halve the batch, and finally keep the original
text for a single failing line (with a warning) instead of aborting.
The chat call lives in _chat() so tests can stub it.
"""

import re
import sys
import time
from pathlib import Path

import srt
from tqdm import tqdm

from .config import Config

BATCH_MAX_ITEMS = 20
BATCH_MAX_CHARS = 800
CONTEXT_LINES = 2
MAX_RETRIES = 2

_NUMBERED = re.compile(r"^\s*(\d+)\s*[\.、．:：\)]\s*(.+?)\s*$")


def make_batches(subs: list[srt.Subtitle]) -> list[list[srt.Subtitle]]:
    batches, cur, chars = [], [], 0
    for sub in subs:
        if cur and (len(cur) >= BATCH_MAX_ITEMS
                    or chars + len(sub.content) > BATCH_MAX_CHARS):
            batches.append(cur)
            cur, chars = [], 0
        cur.append(sub)
        chars += len(sub.content)
    if cur:
        batches.append(cur)
    return batches


def parse_numbered(text: str, n: int) -> dict[int, str] | None:
    """Parse "N. translation" lines; return the index map only when every
    number 1..n is present, else None."""
    result: dict[int, str] = {}
    for line in text.splitlines():
        m = _NUMBERED.match(line)
        if m:
            idx = int(m.group(1))
            if 1 <= idx <= n and idx not in result:
                result[idx] = m.group(2)
    return result if len(result) == n else None


def _chat(client, cfg: Config, user: str) -> str:
    resp = client.chat.completions.create(
        model=cfg.model,
        messages=[{"role": "system", "content": cfg.prompt_system},
                  {"role": "user", "content": user}],
        temperature=0.3,
    )
    return resp.choices[0].message.content or ""


def _translate_batch(client, cfg: Config, texts: list[str],
                     context: list[str]) -> list[str]:
    lines = "\n".join(f"{i}. {t}" for i, t in enumerate(texts, 1))
    ctx = "\n".join(context) if context else "(none)"
    user = cfg.prompt_user_template.format(n=len(texts), context=ctx,
                                           lines=lines)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            parsed = parse_numbered(_chat(client, cfg, user), len(texts))
            if parsed is not None:
                return [parsed[i] for i in range(1, len(texts) + 1)]
            print(f"[translate] batch({len(texts)}) numbering misaligned, "
                  f"retry {attempt}", file=sys.stderr)
        except Exception as e:  # network/API errors retry the same way
            print(f"[translate] batch({len(texts)}) request failed: {e}, "
                  f"retry {attempt}", file=sys.stderr)
        if attempt < MAX_RETRIES:
            time.sleep(2 * attempt)

    if len(texts) == 1:
        print(f"[translate] warning: single-line translation failed, "
              f"keeping original: {texts[0][:30]}...", file=sys.stderr)
        return [texts[0]]
    mid = len(texts) // 2
    left = _translate_batch(client, cfg, texts[:mid], context)
    right = _translate_batch(client, cfg, texts[mid:],
                             texts[mid - CONTEXT_LINES:mid])
    return left + right


def translate(ja_srt: Path, out_dir: Path, client, cfg: Config) -> Path:
    subs = list(srt.parse(ja_srt.read_text(encoding="utf-8")))
    batches = make_batches(subs)
    translated: list[str] = []
    # Context is taken by list position, not by srt index, so hand-made
    # subtitle files with non-sequential indices still work.
    pos = {id(s): i for i, s in enumerate(subs)}
    with tqdm(total=len(batches), unit="batch",
              desc=f"Translating {ja_srt.name}") as bar:
        for batch in batches:
            first = pos[id(batch[0])]
            context = [s.content for s in subs[max(0, first - CONTEXT_LINES):first]]
            translated.extend(_translate_batch(
                client, cfg, [s.content for s in batch], context))
            bar.update(1)

    assert len(translated) == len(subs), "translation count mismatch"
    for sub, zh in zip(subs, translated):
        sub.content = zh
    out_srt = out_dir / ja_srt.name.replace(".ja.srt", ".zh.srt")
    out_srt.write_text(srt.compose(subs), encoding="utf-8")
    print(f"[translate] {len(subs)} translated -> {out_srt}")
    return out_srt
