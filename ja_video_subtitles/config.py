"""Config loading: config.toml with defaults."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import PROJECT_ROOT

# The default prompts are in English but explicitly demand concise,
# natural Simplified Chinese output.
DEFAULT_SYSTEM_PROMPT = """You are a professional subtitle translator. Translate Japanese subtitles into natural, fluent Simplified Chinese.
Rules:
1. Colloquial and idiomatic Chinese;
2. Keep each line within 24 Chinese characters when possible;
3. Keep names and proper nouns consistent;
4. Output only the translation, no explanations."""

DEFAULT_USER_TEMPLATE = """Below are {n} consecutive Japanese subtitle lines. Translate each into Simplified Chinese.
Reply strictly in the format "N. translation", one line each, numbered 1 to {n}. Do not merge, split, or skip any line.

Context (for understanding only, do NOT translate):
{context}

Subtitles to translate:
{lines}"""

DEFAULT_FORCE_STYLE = (
    "FontName=PingFang SC,FontSize=20,PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,MarginV=28,Alignment=2"
)
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_ASR_MODEL = "kotoba-tech/kotoba-whisper-v2.0-faster"
DEFAULT_VIDEO_BITRATE = "8M"


class ConfigError(Exception):
    pass


@dataclass
class Config:
    base_url: str
    api_key: str
    model: str
    asr_model_id: str
    prompt_system: str
    prompt_user_template: str
    force_style: str
    video_bitrate: str


def load(path: Path | None = None) -> Config:
    path = path or (PROJECT_ROOT / "config.toml")
    if not path.exists():
        raise ConfigError(
            f"config file {path} not found; create it from the template: "
            "cp config.example.toml config.toml")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"invalid TOML in {path}: {e}") from e

    ds = data.get("deepseek", {})
    prompt = data.get("prompt", {})
    style = data.get("style", {})
    asr = data.get("asr", {})
    video = data.get("video", {})
    return Config(
        base_url=ds.get("base_url", DEFAULT_BASE_URL),
        api_key=ds.get("api_key", ""),
        model=ds.get("model", DEFAULT_MODEL),
        asr_model_id=asr.get("model_id", DEFAULT_ASR_MODEL),
        prompt_system=prompt.get("system", DEFAULT_SYSTEM_PROMPT),
        prompt_user_template=prompt.get("user_template", DEFAULT_USER_TEMPLATE),
        force_style=style.get("force_style", DEFAULT_FORCE_STYLE),
        video_bitrate=video.get("bitrate", DEFAULT_VIDEO_BITRATE),
    )


def api_key_valid(cfg: Config) -> bool:
    key = cfg.api_key.strip()
    return bool(key) and "在此填入" not in key and "your-api-key" not in key
