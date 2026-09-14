"""Config loading: config.toml with defaults."""

import re
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
DEFAULT_MODEL = "deepseek-flash"
DEFAULT_ASR_MODEL = "kotoba-tech/kotoba-whisper-v2.0-faster"
DEFAULT_VIDEO_BITRATE = "8M"


class ConfigError(Exception):
    pass


@dataclass
class BurnConfig:
    force_style: str
    video_bitrate: str


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
    vocabulary_enabled: bool = True
    learner_level: str = "N3"
    include_unknown: bool = True
    max_examples: int = 3
    vocabulary_output_dir: str = ""
    vocabulary_format: str = "both"


def vocabulary_output_dir(cfg: Config, out_dir: Path) -> Path:
    """Vocabulary paths, like CLI paths, are relative to the working directory."""
    if not getattr(cfg, "vocabulary_enabled", True):
        return out_dir
    configured = getattr(cfg, "vocabulary_output_dir", "")
    return Path(configured).expanduser() if configured else out_dir


def load_burn(path: Path | None = None) -> BurnConfig:
    """Load only rendering settings; burning needs no translation config."""
    path = path or (PROJECT_ROOT / "config.toml")
    data = {}
    if path.exists():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as e:
            raise ConfigError(f"cannot read config file {path}: {e}") from e
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"invalid TOML in {path}: {e}") from e

    style = data.get("style", {})
    video = data.get("video", {})
    for name, section in (("style", style), ("video", video)):
        if not isinstance(section, dict):
            raise ConfigError(f"{name} in {path} must be a TOML table")
    force_style = style.get("force_style", DEFAULT_FORCE_STYLE)
    bitrate = video.get("bitrate", DEFAULT_VIDEO_BITRATE)
    if not isinstance(force_style, str):
        raise ConfigError(f"style.force_style in {path} must be a string")
    if (not isinstance(bitrate, str)
            or not re.fullmatch(r"(?:\d+(?:\.\d+)?|\.\d+)[kKmMgG]?", bitrate)
            or float(bitrate.rstrip("kKmMgG")) <= 0):
        raise ConfigError(
            f"video.bitrate in {path} must be a positive bitrate string "
            '(for example "8M", "8000k", or "8000000")')
    return BurnConfig(force_style=force_style, video_bitrate=bitrate)


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
    vocabulary = data.get("vocabulary", {})
    if not isinstance(vocabulary, dict):
        raise ConfigError(f"vocabulary in {path} must be a TOML table")
    enabled = vocabulary.get("enabled", True)
    learner_level = vocabulary.get("learner_level", "N3")
    include_unknown = vocabulary.get("include_unknown", True)
    max_examples = vocabulary.get("max_examples", 3)
    output_dir = vocabulary.get("output_dir", "")
    output_format = vocabulary.get("format", "both")
    for name, value in (("enabled", enabled), ("include_unknown", include_unknown)):
        if not isinstance(value, bool):
            raise ConfigError(f"vocabulary.{name} in {path} must be a boolean")
    if learner_level not in ("N5", "N4", "N3", "N2", "N1"):
        raise ConfigError(
            f"vocabulary.learner_level in {path} must be one of N5/N4/N3/N2/N1")
    if type(max_examples) is not int or not 1 <= max_examples <= 10:
        raise ConfigError(
            f"vocabulary.max_examples in {path} must be an integer from 1 to 10")
    if not isinstance(output_dir, str) or "\x00" in output_dir:
        raise ConfigError(f"vocabulary.output_dir in {path} must be a path string")
    if output_format not in ("md", "json", "both"):
        raise ConfigError(f"vocabulary.format in {path} must be one of md/json/both")
    return Config(
        base_url=ds.get("base_url", DEFAULT_BASE_URL),
        api_key=ds.get("api_key", ""),
        model=ds.get("model", DEFAULT_MODEL),
        asr_model_id=asr.get("model_id", DEFAULT_ASR_MODEL),
        prompt_system=prompt.get("system", DEFAULT_SYSTEM_PROMPT),
        prompt_user_template=prompt.get("user_template", DEFAULT_USER_TEMPLATE),
        force_style=style.get("force_style", DEFAULT_FORCE_STYLE),
        video_bitrate=video.get("bitrate", DEFAULT_VIDEO_BITRATE),
        vocabulary_enabled=enabled,
        learner_level=learner_level,
        include_unknown=include_unknown,
        max_examples=max_examples,
        vocabulary_output_dir=output_dir,
        vocabulary_format=output_format,
    )


def api_key_valid(cfg: Config) -> bool:
    key = cfg.api_key.strip()
    return bool(key) and "在此填入" not in key and "your-api-key" not in key
