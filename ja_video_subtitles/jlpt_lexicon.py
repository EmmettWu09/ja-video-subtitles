"""Versioned, offline JLPT reference data. Levels are unofficial estimates.

The bundled dataset's source, transformations and license are documented in
``data/README.md``. Importing this module does not load data or a tokenizer.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


DATA_PATH = Path(__file__).with_name("data") / "jlpt_vocab.json"
DATA_VERSION = "b062d4e38c4bdd0950ae1d4ec55f04b176182e03-v1"
# The complete file pin protects attribution/version as well as vocabulary.
DATA_SHA256 = "5758786713ad5ebbe8f3b78906bb921d6076b61d1042558dcf9e218ac7da6b8a"
LEVELS = frozenset({"N1", "N2", "N3", "N4", "N5"})


class LexiconError(ValueError):
    """A missing, corrupt, or unsupported JLPT dataset."""


def normalize_reading(reading: str) -> str:
    """Normalize width and voiced marks, then convert katakana to hiragana.

    Long-vowel marks are preserved: expanding them would guess pronunciation.
    """
    normalized = unicodedata.normalize("NFKC", reading).strip()
    result = []
    for char in normalized:
        code = ord(char)
        if 0x30A1 <= code <= 0x30F6 or code in (0x30FD, 0x30FE):
            result.append(chr(code - 0x60))
        elif 0x30F7 <= code <= 0x30FA:
            result.append(chr(code - 0x68) + "\u3099")
        else:
            result.append(char)
    return unicodedata.normalize("NFC", "".join(result))


def _normalize_lemma(lemma: str) -> str:
    return unicodedata.normalize("NFKC", lemma).strip()


def entries_sha256(entries: list[dict]) -> str:
    """Canonical entry hash, shared with the reproducible dataset converter."""
    encoded = json.dumps(
        entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class Lexicon:
    """Validated reference metadata and indexes retaining ambiguous level evidence."""

    name: str
    version: str
    source_url: str
    license: str
    entry_count: int
    _exact: dict[tuple[str, str], frozenset[str]] = field(repr=False)
    _lemmas: dict[str, frozenset[tuple[str, str]]] = field(repr=False)

    def lookup(self, lemma: str, reading: str = "") -> str | None:
        """Return one supported level, never resolve conflicting evidence.

        Exact spelling/reading evidence wins. A spelling-only fallback requires
        an absent input reading, and a single reading AND level in this reference.
        An explicit different reading is contrary evidence, even if the reference
        has only one sense; multiple readings are ambiguous even at the same level.
        """
        lemma = _normalize_lemma(lemma)
        reading = normalize_reading(reading)
        exact = self._exact.get((lemma, reading))
        if exact is not None:
            return next(iter(exact)) if len(exact) == 1 else None
        if reading:
            return None
        candidates = self._lemmas.get(lemma, frozenset())
        if len(candidates) == 1:
            return next(iter(candidates))[1]
        return None


def _required_text(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LexiconError(f"JLPT 数据字段 {key} 必须为非空字符串")
    return value


def load(path: Path | None = None) -> Lexicon:
    """Load and validate bundled or explicitly supplied schema-1 JSON data.

    Every dataset carries a canonical entries hash. The bundled file additionally
    has a complete-file SHA-256 and fixed version pin in this module.
    """
    source = DATA_PATH if path is None else Path(path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise LexiconError(f"无法读取 JLPT 数据 {source}: {exc}") from exc
    if source.resolve() == DATA_PATH.resolve():
        if hashlib.sha256(raw).hexdigest() != DATA_SHA256:
            raise LexiconError("内置 JLPT 数据 SHA-256 不匹配，请恢复数据文件")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise LexiconError(f"JLPT 数据不是有效 UTF-8 JSON: {source}") from exc
    if not isinstance(payload, dict):
        raise LexiconError("JLPT 数据顶层必须为对象")
    if type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        raise LexiconError("不支持的 JLPT 数据 schema_version")
    name = _required_text(payload, "name")
    version = _required_text(payload, "version")
    source_url = _required_text(payload, "source_url")
    license_name = _required_text(payload, "license")
    digest = _required_text(payload, "entries_sha256")
    if source.resolve() == DATA_PATH.resolve() and version != DATA_VERSION:
        raise LexiconError("内置 JLPT 数据版本不匹配")
    url = urlparse(source_url)
    if url.scheme not in {"http", "https"} or not url.netloc:
        raise LexiconError("JLPT 数据 source_url 必须为 HTTP(S) 来源地址")
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise LexiconError("JLPT 数据 entries_sha256 格式无效")
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise LexiconError("JLPT 数据 entries 必须为非空数组")
    if digest != entries_sha256(entries):
        raise LexiconError("JLPT 数据词条 SHA-256 不匹配")
    # Preserve conflicting readings and levels so lookup can decline ambiguity
    # instead of silently choosing the last entry in the source dataset.
    exact: dict[tuple[str, str], set[str]] = {}
    lemmas: dict[str, set[tuple[str, str]]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise LexiconError("JLPT 词条必须为对象")
        lemma = _normalize_lemma(_required_text(entry, "lemma"))
        reading = normalize_reading(_required_text(entry, "reading"))
        level = _required_text(entry, "level")
        if level not in LEVELS:
            raise LexiconError(f"无效 JLPT 等级: {level}")
        exact.setdefault((lemma, reading), set()).add(level)
        lemmas.setdefault(lemma, set()).add((reading, level))
    return Lexicon(
        name=name, version=version, source_url=source_url, license=license_name,
        entry_count=len(entries),
        _exact={key: frozenset(values) for key, values in exact.items()},
        _lemmas={key: frozenset(values) for key, values in lemmas.items()},
    )
