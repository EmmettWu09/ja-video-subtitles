#!/usr/bin/env python3
"""Rebuild the pinned JLPT reference; this script never updates the source pin.

Usage: python ja_video_subtitles/data/rebuild_jlpt.py [--source-dir DIRECTORY]
Offline mode reads the upstream filenames from DIRECTORY. Normal mode fetches
the same immutable GitHub commit archive over HTTPS. No third-party dependencies.
"""

from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ja_video_subtitles.jlpt_lexicon import (  # noqa: E402
    DATA_VERSION, entries_sha256, normalize_reading,
)

COMMIT = "b062d4e38c4bdd0950ae1d4ec55f04b176182e03"
REPOSITORY = "https://github.com/stephenmk/yomitan-jlpt-vocab"
FILES = {
    "yomitan-jlpt-vocab/term_meta_bank_1.json": "80698c74b0d4efe476db35626b60324007f66d5ca32c0178bf3f9456a0290abf",
    "yomitan-jlpt-vocab/term_meta_bank_2.json": "c58e20a6fc2dececf6a5e42bd1163212615ef79deec85e77c6f7c7deb4d4cc7e",
    "yomitan-jlpt-vocab/term_meta_bank_3.json": "baeee2da06c41ea973cb54a6118834682b33857128f7d97577f21cbaaae7c51b",
    "yomitan-jlpt-vocab/term_meta_bank_4.json": "844590546217e084f8244f3cf9e6eb6054f5f7a370857bf5917fe19d4d83d7a8",
    "yomitan-jlpt-vocab/term_meta_bank_5.json": "a169779f5b8e4dbf4aaa86c367e2b0e24721b5d247c8e0c5b37b18189bc1be83",
    "LICENSE.txt": "7abe19ec9bb73b36141b999b861d24ad855e808bafe0f81e84cce28556f6c297",
    "README.md": "4efd40eecf18c01a61ca54d4c1731daa0756a384b0f4ade551b43914a087869a",
}


def fetch(source_dir: Path | None) -> dict[str, bytes]:
    """Read pinned upstream files and verify vocabulary and attribution hashes.

    Offline inputs use each upstream basename in one directory; both modes must
    provide identical bytes before conversion is allowed.
    """
    if source_dir is None:
        url = f"https://codeload.github.com/stephenmk/yomitan-jlpt-vocab/zip/{COMMIT}"
        request = Request(url, headers={"User-Agent": "ja-video-subtitles-jlpt-rebuild"})
        with urlopen(request, timeout=30) as response:
            archive = response.read()
        # Read only known members; never extract untrusted archive paths.
        with ZipFile(BytesIO(archive)) as source:
            upstream = {path: source.read(f"yomitan-jlpt-vocab-{COMMIT}/{path}")
                        for path in FILES}
    else:
        upstream = {path: (source_dir / Path(path).name).read_bytes() for path in FILES}
    for path, raw in upstream.items():
        if hashlib.sha256(raw).hexdigest() != FILES[path]:
            raise ValueError(f"Upstream SHA-256 mismatch: {path}")
    return upstream


def main() -> None:
    """Write the reproducible reference and its original license and provenance."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    upstream = fetch(args.source_dir)
    entries = []
    for path, raw in upstream.items():
        if not path.endswith(".json"):
            continue
        for lemma, kind, details in json.loads(raw):
            if kind != "freq":
                raise ValueError(f"Unsupported upstream entry type: {kind}")
            entries.append({"lemma": lemma, "reading": normalize_reading(details["reading"]),
                            "level": details["frequency"]["displayValue"]})
    # Keep duplicates/conflicts: resolving competing levels would invent certainty.
    payload = {
        "schema_version": 1,
        "name": "yomitan-jlpt-vocab",
        "version": DATA_VERSION,
        "source_url": f"{REPOSITORY}/tree/{COMMIT}",
        "license": "CC-BY-SA-4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "attribution": "stephenmk; Jonathan Waller; EDRDG / JMdict",
        "upstream_commit": COMMIT,
        "upstream_sha256": FILES,
        "entries_sha256": entries_sha256(entries),
        "entries": entries,
    }
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (output / "jlpt_vocab.json").write_bytes(raw)
    (output / "JLPT-LICENSE.txt").write_bytes(upstream["LICENSE.txt"])
    (output / "JLPT-UPSTREAM-README.md").write_bytes(upstream["README.md"])
    print(f"{len(entries)} entries; jlpt_vocab.json SHA-256: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
