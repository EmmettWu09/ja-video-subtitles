"""ja-video-subtitles: Japanese video -> JA/ZH bilingual hard subtitles, CLI tool."""

__version__ = "0.1.1"

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / ".cache" / "hf"
MODEL_READY_MARKER = CACHE_DIR / ".model-ready"

# Pin the model cache inside the project; must run before importing
# faster_whisper / huggingface_hub anywhere.
os.environ.setdefault("HF_HOME", str(CACHE_DIR))
# huggingface.co is unreachable from some networks; default to the mirror.
# Never overrides a user-provided HF_ENDPOINT.
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
