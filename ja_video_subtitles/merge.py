"""Bilingual merge: align ja + zh by position -> <out>/xxx.bilingual.srt."""

from pathlib import Path

import srt


def merge(ja_srt: Path, zh_srt: Path, out_dir: Path) -> Path:
    ja = list(srt.parse(ja_srt.read_text(encoding="utf-8")))
    zh = {s.index: s.content for s in srt.parse(zh_srt.read_text(encoding="utf-8"))}

    for sub in ja:
        zh_text = zh.get(sub.index)
        sub.content = f"{sub.content}\n{zh_text}" if zh_text else sub.content

    out_srt = out_dir / ja_srt.name.replace(".ja.srt", ".bilingual.srt")
    out_srt.write_text(srt.compose(ja), encoding="utf-8")
    print(f"[merge] {len(ja)} bilingual subtitles -> {out_srt}")
    return out_srt
