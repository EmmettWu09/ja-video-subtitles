"""Bilingual merge: align ja + zh by index -> <out>/xxx.bilingual.srt."""

from pathlib import Path

import srt


def _compose(ja_srt: Path, zh_srt: Path) -> tuple[str, int]:
    ja = list(srt.parse(ja_srt.read_text(encoding="utf-8-sig")))
    zh = {s.index: s.content for s in srt.parse(zh_srt.read_text(encoding="utf-8-sig"))}
    for sub in ja:
        zh_text = zh.get(sub.index)
        sub.content = f"{sub.content}\n{zh_text}" if zh_text else sub.content
    return srt.compose(ja), len(ja)


def is_fresh(ja_srt: Path, zh_srt: Path, bilingual: Path) -> bool:
    """A valid but stale bilingual file must not disagree with glossary context."""
    try:
        expected, count = _compose(ja_srt, zh_srt)
        return count > 0 and bilingual.read_text(encoding="utf-8-sig") == expected
    except (OSError, UnicodeError, srt.SRTParseError):
        return False


def merge(ja_srt: Path, zh_srt: Path, out_dir: Path) -> Path:
    content, count = _compose(ja_srt, zh_srt)

    out_srt = out_dir / ja_srt.name.replace(".ja.srt", ".bilingual.srt")
    out_srt.write_text(content, encoding="utf-8")
    print(f"[merge] {count} bilingual subtitles -> {out_srt}")
    return out_srt
