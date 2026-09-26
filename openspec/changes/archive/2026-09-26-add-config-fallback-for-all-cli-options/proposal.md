# Proposal: add-config-fallback-for-all-cli-options

## Why

目前只有词汇输出目录和格式支持命令行覆盖配置，输入、主输出目录、强制重跑、自动覆盖及烧录字幕来源仍必须通过命令行指定。将所有现有业务参数统一支持配置，可以保存常用处理方式，并在每次执行时只传需要临时调整的参数。

## What Changes

- 所有现有业务参数按「显式命令行参数 → `config.toml` 对应配置 → 内置默认值」解析；没有默认值的必需参数在合并后校验。
- 新增 `[run]` 的 `input`、`output_dir`、`force`、`yes`，以及 `[burn]` 的 `inputs`、`output_dir`、`subtitles`、`subtitle_dir`、`yes`；保留既有 `[vocabulary] output_dir/format`，不引入重复配置键。
- `run` 和 `burn` 的位置输入及 `-o/--output-dir` 可以省略，由各自配置补齐；命令行指定的烧录输入列表整体替换配置列表。
- `run` 增加 `--no-force`，`run` 和 `burn` 增加 `--no-yes`，允许显式关闭配置中开启的布尔能力；未传开关时继承配置。
- 将烧录字幕文件与字幕目录作为一组互斥来源：命令行选择来源时覆盖配置中的来源，未选择时使用配置，均未设置时从有效输出目录匹配字幕。
- 明确配置校验、相对路径、缺失参数、覆盖确认和强制重跑的行为，保持独立 `burn` 不依赖翻译、ASR 或词汇配置。
- 更新示例配置、三个语言版本的 README、CLI 帮助与回归测试。子命令选择、帮助和版本信息属于命令控制，不写入配置；`download` 没有业务参数，继续使用既有 ASR 模型配置。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `config`: 补齐全部业务参数的配置映射，规定逐项优先级、严格类型、路径基准与命令配置隔离。
- `cli`: 输入和输出改为合并后必填，支持显式布尔关闭、字幕来源整体覆盖，并让覆盖确认与产物复用使用最终有效值。
- `burning`: 现有字幕映射使用命令行与配置合并后的来源，保留单字幕限制和整批校验。

## Impact

后续实现涉及 `ja_video_subtitles/config.py`、`cli.py`、`preflight.py`、相关测试、`config.example.toml` 和三种语言 README。无需新增依赖，现有完整命令及未新增配置项的旧配置保持兼容；既有词汇配置键、配置文件定位、处理阶段和产物命名保持兼容。

本次交付仅为 OpenSpec 提案、设计、增量规格和实施任务，不实现业务代码、不修改本机含密钥的 `config.toml`，也不归档或同步主规格。
