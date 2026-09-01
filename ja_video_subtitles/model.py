"""ASR model download and readiness check (ja-video-subtitles download)."""

import sys
from pathlib import Path

from . import CACHE_DIR, MODEL_READY_MARKER


def _model_dir(model_id: str) -> Path:
    # HF_HOME layout: hub/models--<org>--<name>/
    return CACHE_DIR / "hub" / ("models--" + model_id.replace("/", "--"))


def model_ready(model_id: str) -> bool:
    if not MODEL_READY_MARKER.exists():
        return False
    model_dir = _model_dir(model_id)
    return model_dir.exists() and any(model_dir.rglob("model.bin"))


def download(model_id: str) -> None:
    from huggingface_hub import snapshot_download

    print(f"[download] downloading ASR model {model_id} -> {CACHE_DIR} "
          f"(~1.5GB)")
    snapshot_download(repo_id=model_id)  # tqdm progress built in
    if not any(_model_dir(model_id).rglob("model.bin")):
        print("[download] model.bin not found after download; please retry",
              file=sys.stderr)
        sys.exit(1)
    MODEL_READY_MARKER.parent.mkdir(parents=True, exist_ok=True)
    MODEL_READY_MARKER.write_text(model_id + "\n", encoding="utf-8")
    print("[download] model ready")
