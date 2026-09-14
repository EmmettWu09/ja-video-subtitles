# Proposal: add-configurable-vocabulary-output-and-mp3

## Why

当前 `run` 总是把词汇 Markdown、JSON、字幕和成片放在同一目录，无法直接把词表存入笔记或学习资料目录，也无法只保留需要的格式。用户还需要与字幕成片配套的 MP3，便于独立听音复习。让一次运行同时完成这些输出，可以省去移动、删除和手工提取音频的步骤。

## What Changes

- `run` 新增 `--vocab-output-dir PATH`，将所选词汇产物集中输出到该目录；省略时沿用 `[vocabulary] output_dir`，空配置回退到 `-o`。
- `run` 新增 `--vocab-format md|json|both`，只生成 Markdown、只生成 JSON 或同时生成；省略时沿用 `[vocabulary] format`，默认 `both`。
- 命令行参数优先于配置文件；两种来源的相对目录都按命令执行时的工作目录解析。词汇启用时，在视频处理开始前创建并检查词汇目录；禁用时不创建词汇目录或生成词汇文件。
- 词汇复用只检查当前选择的格式，并继续验证源字幕、学习者设置及数据版本；只选 Markdown 时也能独立验证新鲜度，无需额外 JSON 文件。切换格式不会删除已有未选格式文件。
- `run` 自动将源视频的第一条音轨转码为 `<out>/<stem>.mp3`，与 `<out>/<stem>.sub.mp4` 放在同一目录，不受词汇目录设置影响。
- 已有 MP3 和成片在处理前统一确认，`-y` 或 `run --force` 自动覆盖。音频使用临时文件加原子替换；失败保留已有正式文件，记录 `partial` 并继续批次。
- 报告记录实际词汇目录、格式、文件路径及音频阶段耗时和 MP3，不把未选中的历史词汇文件当作本次产物。独立 `burn` 的行为保持不变。

## Capabilities

### New Capabilities

- `audio-export`: 从源视频导出本地 MP3，保证与成片同目录、原子写入、错误隔离及资源清理。

### Modified Capabilities

- `cli`: 增加词汇输出参数、MP3 阶段、目录预检、音频覆盖确认和实际产物报告。
- `config`: 增加词汇输出目录与格式的默认值、校验和命令行覆盖规则。
- `vocabulary`: 支持指定目录与格式的原子输出，并按所选格式独立验证词汇复用。

## Impact

- 影响 `config.py`、`cli.py`、`preflight.py`、`vocabulary.py`、`report.py` 及配置示例；增加本地音频导出模块和相应测试。
- 复用已有 ffmpeg/ffprobe，不增加音视频上传或新的服务依赖。音频转码增加少量本地处理时间和磁盘占用。
- 原有命令仍默认在 `-o` 输出两种词汇文件；新增 MP3 是 `run` 的默认产物。独立 `burn` 不增加音频输出或词汇参数。
- 同步英文、中文、日文 README 中的用法、产物、覆盖与复用说明。
