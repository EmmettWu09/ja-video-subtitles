# Proposal: add-standalone-burn-command

## Why

现有 `run` 命令执行转写、翻译、合成与烧录整条流水线。用户已有字幕、仅调整字幕内容或样式时，需要能够直接重新烧录一个视频，也需要一次处理多个视频或文件夹，而不依赖翻译 API、ASR 模型及完整流水线预检。

## What Changes

- 新增 `burn <input> [<input> ...] -o <out> [-s <srt> | --subtitle-dir <dir>] [-y]`，输入可混合多个 mp4/mov 文件与文件夹。
- 默认按视频文件名读取 `<out>/<stem>.bilingual.srt`；`--subtitle-dir` 可指定统一字幕目录；仅处理一个去重后的视频时，可用 `-s/--subtitles` 指定任意有效 SRT 文件。
- 文件夹仅展开当前层 mp4/mov，排序后处理；重复源文件去重，同名主干冲突与成片覆盖源文件的风险在处理前报错。
- 全批次字幕映射、格式与烧录预检通过后，统一确认已有成片，再串行烧录为 `<out>/<stem>.sub.mp4`。单个烧录失败继续后续视频。
- `burn` 无需 API key、ASR 模型或 `config.toml`；配置存在时沿用字幕样式与视频码率。复用进度显示、日志、报告和已有成片确认行为。
- 更新三种语言 README，说明单文件、多文件及文件夹的烧录命令。

## Out of Scope

- 不修改 `run` 的参数、完整流水线或断点续跑行为。
- 不新增转写、翻译、字幕合成、词汇处理、递归扫描或跨平台编码支持。
- 不新增视频输出命名模板、字幕自动猜测、单字幕批量复用或 `burn --force`。

## Impact

- Modified capabilities: `cli`, `burning`, `config`。
- 复用现有 ffmpeg 烧录与报告模块，按命令选择配置加载及预检范围；不新增第三方依赖。
- 与尚未实现的 `add-jlpt-vocabulary-glossary` 独立：`burn` 始终只消费现成字幕，不运行词汇阶段。
