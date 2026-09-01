# Proposal: add-video-subtitle-pipeline

## Why

目标：**任意日文视频进来，一条命令烧录出「日文+中文」双语硬字幕成片。** 需要把约 1 小时时长的日文视频自动处理成烧录双语字幕的成片。现有 GUI 开源工具（SmartSub 等）不含日文专用 ASR 模型、无法纯命令行批量跑；通用 Whisper 模型在日文中准确率与速度都不是最优。因此自建一条可配置、可断点续跑的命令行流水线。

**平台约束：仅支持 macOS（Apple Silicon），明确不支持 Windows / Linux**（烧录依赖 VideoToolbox 硬件编码与苹方字体，ffmpeg 按 Homebrew 路径定位）。

## What Changes

- 新增命令行工具 `ja-video-subtitles`（仅处理日文视频），子命令：
  - `ja-video-subtitles run <视频文件|文件夹> -o <输出目录> [--force] [-y]`：依次完成 **日文转写 → 日译中 → 双语合成 → 烧录**；文件夹入参处理其中全部 mp4 / mov。
  - `ja-video-subtitles download`：单独下载 ASR 模型（约 1.5GB）。未下载模型时 `run` 在预检阶段直接报错退出。
- 全部产物输出到 `-o` 指定的目录，**不在源视频目录生成任何文件**：`<out>/xxx.ja.srt`、`<out>/xxx.zh.srt`、`<out>/xxx.bilingual.srt`、`<out>/xxx.sub.mp4`。
- 烧录前检查输出目录同名成片：存在则逐个提示用户选择覆盖或跳过；确认动作全部发生在烧录开始之前，烧录过程不中断等待输入。
- 转写引擎：faster-whisper + kotoba-whisper-v2.0（日文专用蒸馏模型），VAD + 幻觉过滤。
- 翻译引擎：DeepSeek（OpenAI 兼容接口），分批带上下文翻译，编号对齐校验与自动降级重试。
- 烧录：带 libass 的 ffmpeg（`subtitles` 滤镜 + `force_style`），硬字幕。
- 新增 `config.toml` 配置：DeepSeek 的 base_url / api_key / model，以及翻译 prompt（提供默认值，可覆盖）。
- 每个阶段打印进度条；程序启动先做依赖与环境预检，任何一项不满足立即退出，不允许跑到烧录中途才报错。

## Impact

- Affected specs（新增 capability）：`cli`、`config`、`transcription`、`translation`、`burning`
- 技术栈：**Python 3.12** + faster-whisper + openai + srt + tqdm；外部依赖 ffmpeg-full（libass）
- ASR 模型约 1.5GB，由 `ja-video-subtitles download` 显式下载，缓存于项目内 `.cache/hf`
