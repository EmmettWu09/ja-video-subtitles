# Proposal: add-lesson-highlights

## Why

当前流水线把日语课堂录屏整理为双语字幕成片，但一节课约 50 分钟，学习者和不懂日语的观众都难以快速回顾课堂中的关键表现。需要基于流水线已生成的日中双语字幕，自动发现值得记录的初学者高光（连贯交流、完整表达、主动提问、老师认可、学以致用、自我纠正、提示后突破、有趣互动），并直接交付课堂总结、独立高光切片集和 3–5 分钟精华视频。

## What Changes

- `run` 新增高光阶段：在烧录成功后，基于 `<stem>.ja.srt`/`<stem>.zh.srt` 与源视频执行字幕整理、课堂分析、高光筛选和边界裁定，输出课堂总结、独立切片集、精华视频及配套 SRT、剪辑清单、分析数据和回看目录。
- 高光产物 SHALL 写入本次运行目标目录下的 `<out>/<stem>.highlights/` 子目录，与 `<stem>.sub.mp4` 同级；不引入独立输出根目录，批量运行时每个视频一个子目录。
- `run` 新增 `--highlights` / `--no-highlights` 正反开关，并新增 `[highlights] enabled` 配置，默认 true（默认生成高光）；显式 CLI 优先于配置，配置优先于内置默认值；`burn` 不接受高光参数、不执行高光阶段。
- 新增 `[highlights]` 配置节：`enabled`（默认 true）、`target_seconds`（默认 240）、`intro_start_seconds`（默认 0）、`ja_voice`（默认 `Kyoko`）、`zh_voice`（默认 `Tingting`）。
- 精华版片头使用原片开头的连续画面，原音轨完全不进入片头，仅播放本地 `say` 合成的日文摘要配音（含句间停顿 15–25 秒），并烧录摘要日文与中文译文；课堂高光保留原声与对应日中双语对白字幕。
- 高光阶段与词汇、音频阶段一样非阻塞：阶段级失败标记 `partial`、记录原因并继续批次；精华版合成失败时保留已完成的独立切片与分析产物。
- 启用高光时预检额外检查 `say` 命令及所配置音色可用；课堂分析仅上传字幕文字、编号和时间信息，不上传视频、音频或截图。
- 高光阶段支持阶段级断点恢复与缓存，缓存关联源字幕内容、模型、音色与目标时长等配置；`--force` 重跑高光阶段。
- 已有 `<stem>.highlights/highlights.mp4` 纳入处理前的覆盖确认与输出冲突检查；运行报告记录高光阶段耗时、切片数量、精华实际时长与失败原因。
- 更新 CLI 帮助、`config.example.toml` 及英文、中文、日文 README。

## Capabilities

### New Capabilities

- `highlights`: 课堂字幕整理与高光分析、独立高光切片、精华视频合成、字幕导出、课堂总结与回看目录、本地配音、断点恢复与数据边界。

### Modified Capabilities

- `cli`: `run` 新增高光开关与高光阶段，预检、覆盖确认、输出冲突检查、运行报告与产物复用规则相应扩展；`burn` 行为不变。
- `config`: 新增 `[highlights]` 配置节的默认值、校验、与 CLI 的优先级映射及子命令隔离规则。

## Impact

- 影响 `cli.py`、`config.py`、`preflight.py`、`report.py`、`config.example.toml` 与三语 README；新增高光模块（字幕整理、课堂分析、选段、时间轴、TTS、渲染、回看页）及相应测试。
- 复用既有 DeepSeek 文本接口、ffmpeg/ffprobe 与字幕烧录能力；新增 macOS `say` 本地配音依赖；音视频与截图不上云。
- 默认开启高光会改变既有 `run` 的默认产物与处理耗时；用户可通过 `--no-highlights` 或 `highlights.enabled=false` 完全关闭，关闭时不创建高光目录、不增加预检项。
- 第一版仅支持以流水线自生成字幕为输入（对应设计文档 `source_subtitles=none` 路径）；已烧录双语原片输入、字幕区域遮盖与计划编辑后重渲染（`render --plan`）留待后续。
