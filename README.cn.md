# ja-video-subtitles

**任意日文视频 → 一条命令 → 日/中双语硬字幕成片。**

流水线：`视频 → 日文转写(kotoba-whisper) → 日译中(DeepSeek) → 词汇表 → 双语合成 → 烧录(ffmpeg) → 导出 MP3`

## 工作流程

| 阶段 | 做什么 | 产物 |
|---|---|---|
| 转写 | 本地 ASR（kotoba-whisper，CPU，不走网络）：日语音频 → 带时间轴日文字幕，含 VAD、幻觉过滤、按标点分段 | `xxx.ja.srt` |
| 翻译 | 日译中，走 DeepSeek API，分批带上下文、编号校验，异常自动重试降级 | `xxx.zh.srt` |
| 词汇表 | 本地分词、还原基本形及非官方 JLPT 判级；通过配置的 API 生成简体中文词义 | `xxx.vocab.md` 和/或 `xxx.vocab.json` |
| 双语合成 | 日/中逐条对齐（上日下中），纯本地，瞬间完成 | `xxx.bilingual.srt` |
| 烧录 | ffmpeg 把字幕逐帧画进画面，VideoToolbox 硬编出成片 | `xxx.sub.mp4` |
| 音频 | 本地提取源视频第一条音轨并转码为 MP3 | `xxx.mp3` |

转写、分词与 JLPT 查询、合成、烧录和音频导出均在本地执行。翻译会把字幕文本发送到配置的 API；词汇释义会把去重后的词及日文例句发送到同一服务。这些阶段不会上传音视频。默认 API 模型为 `deepseek-flash`。各阶段耗时见报告 `report-*.md`。

支持 mp4/mov，单文件或文件夹批量；`burn` 还可一次传入多个文件和文件夹。字幕、成片、MP3、日志与报告写入 `-o`，词汇文件可单独指定目录；不修改源视频。

> **`run` 的输入必须是日语语音。** 转写固定 `language="ja"`（kotoba-whisper 是日文专用模型），不做语言检测：喂入非日文音频不会报错，只会静默产出垃圾字幕。`burn` 直接使用已有 SRT，不转写音频。

## 平台

**仅支持 macOS（Apple Silicon），不支持 Windows / Linux**——烧录依赖 VideoToolbox 硬编、苹方字体和 Homebrew 的 ffmpeg 路径。其他平台预检直接报错退出。

## 依赖

| 依赖 | 用途 | 安装 |
|---|---|---|
| Homebrew | 包管理 | `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"` |
| uv | Python 环境管理 | `brew install uv` |
| Python 3.12 | 运行时 | `uv venv` 自动安装 |
| ffmpeg-full | 字幕烧录（libass） | `brew install homebrew-ffmpeg/ffmpeg/ffmpeg-full` |
| DeepSeek API Key | 日译中和词汇释义 | [DeepSeek 平台](https://platform.deepseek.com) |
| SudachiPy / SudachiDict-core | 本地词汇形态分析 | 随 `requirements.txt` 安装；词典下载约 70 MB |

字幕字体为 macOS 自带苹方，无需安装。

## 安装

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp config.example.toml config.toml   # 填入 deepseek.api_key
./ja-video-subtitles download                 # 一次性下载 ASR 模型（约 1.5GB）
```

模型存放在项目内 `.cache/hf/`（`HF_HOME` 已固定），下载成功写 `.model-ready` 标记。默认走 `hf-mirror.com` 镜像，可用 `HF_ENDPOINT=https://huggingface.co` 覆盖。

如果只用 `burn`，安装 Python、`srt`、`tqdm` 和 ffmpeg 即可，配置文件、API key、ASR 模型及词汇词典均可跳过。项目中存在 `config.toml` 时只读取字幕样式和视频码率，否则使用默认值。`burn` 忽略词汇配置，不导入分词器或加载 JLPT 数据。

## 用法

```bash
./ja-video-subtitles run /path/to/xxx.mp4 -o /path/to/output   # 单文件
./ja-video-subtitles run /path/to/dir   -o /path/to/output     # 文件夹批量
./ja-video-subtitles run /path/to/dir   -o out -y              # 同名自动覆盖
./ja-video-subtitles run xxx.mp4 -o out --force                # 全部重跑
```

### 指定词汇目录与格式

```bash
# 词汇单独存放在 words，仅生成 Markdown
./ja-video-subtitles run xxx.mp4 -o media --vocab-output-dir words --vocab-format md
# 仅生成 JSON
./ja-video-subtitles run xxx.mp4 -o media --vocab-output-dir words --vocab-format json
# 两种格式都生成
./ja-video-subtitles run xxx.mp4 -o media --vocab-output-dir words --vocab-format both
```

以上命令把所选 `xxx.vocab.md` 和/或 `xxx.vocab.json` 写入 `words`，字幕、`xxx.sub.mp4` 和 `xxx.mp3` 仍在 `media` 中。不指定时，默认在 `-o` 生成两种词汇格式。命令行选项优先于对应配置，所有相对路径均以执行命令时的目录为准。切换格式会保留旧的未选格式文件，但不将它们列入本次报告。词汇配置 `enabled = false` 时，这些选项不会启用词汇功能。

### 只烧录已有字幕

```bash
./ja-video-subtitles burn xxx.mp4 -o out                         # 读取 out/xxx.bilingual.srt
./ja-video-subtitles burn xxx.mp4 -s edited.srt -o out           # 指定单个 SRT
./ja-video-subtitles burn first.mp4 second.mov -o out            # 多文件
./ja-video-subtitles burn first.mp4 second.mov --subtitle-dir subtitles -o out -y
./ja-video-subtitles burn /path/to/videos --subtitle-dir subtitles -o out
```

`burn` 仅把已有字幕烧进视频，输出 `<out>/<stem>.sub.mp4`、`run.log` 和 `report-*.md`，不生成或修改字幕。默认读取 `<out>/<stem>.bilingual.srt`；指定 `--subtitle-dir` 则读取该目录下的同名字幕。处理一个去重后的视频时，可用 `-s/--subtitles` 指定任意命名的 SRT；它与 `--subtitle-dir` 不能同时使用。

可混合传入文件和文件夹。文件夹按文件名排序，仅扫描当前层 mp4/mov，重复的实际视频路径只处理一次。任一传入文件夹在当前层没有 mp4/mov 时，整批退出。不同视频主干名相同（不区分大小写），或任一成片路径会覆盖源视频时，整批拒绝。全部字幕须为可读、非空的 UTF-8 SRT；任一字幕缺失或损坏，整批在烧录前退出。

已有成片在开始前统一确认，`-y/--yes` 自动覆盖，无标准输入时跳过；`burn` 不使用 `--force`。预检通过后，单个视频编码失败会继续其他视频。退出码：`0` 成功或跳过，`1` 存在烧录失败，`2` 参数、字幕、配置或预检错误。全程不检查或加载 API 与 ASR 模型。

### 完整流水线的产物与行为

`run` 产物（默认都在 `-o`，词汇文件可另设目录且按所选格式生成）：`xxx.ja.srt`（日文）、`xxx.ja.json`（转写置信度）、`xxx.zh.srt`（中文）、`xxx.vocab.md`（词汇表）、`xxx.vocab.json`（结构化词条及复用元数据）、`xxx.bilingual.srt`（双语，上日下中）、`xxx.sub.mp4`（成片）、`xxx.mp3`（源视频第一条音轨，192 kb/s，与成片同目录）、`report-<时间戳>.md`（运行报告）、`run.log`（日志）。词汇功能禁用时不生成词汇产物。

行为要点：

- 相对路径以执行命令时的目录为准；config 与模型缓存始终从项目目录读取。
- 断点续跑：已有合法产物自动跳过；损坏产物自动重跑。`run` 仅复用与当前日文/中文字幕重新合成结果一致的双语字幕；修改任一源字幕后会先更新双语文件再烧录。手工编辑后的独立 SRT 可用 `burn` 原样烧录。
- 同名成片或 MP3 在处理开始前统一询问；处理过程不中断。拒绝任一已有输出或标准输入为 EOF 时，跳过该视频。`-y` 或 `--force` 自动覆盖；确认处理后会重新从源视频导出 MP3，导出失败保留此前的正式 MP3。
- 预检平台、Python 依赖、ffmpeg+libass+MP3 编码器、config/api_key、DeepSeek 连通、模型就绪、磁盘空间和输出目录可写。词汇启用时还会创建并检查词汇目录可写，再检查分词器、本地形态词典及 JLPT 数据的 schema、版本与哈希；任一失败会在处理前退出并给出修复指引。
- 词汇阶段整体失败仍继续合成与烧录，该视频记为 `partial`（部分成功），整批退出码为 `1`；音频导出失败同样记为 `partial`，保留成功成片并继续后续视频；其他处理失败为 `failed`，确认跳过为 `skipped`。单个词释义重试后失败时，保留词条、留空释义并附 warning，只计为释义降级。报告包含 succeeded/partial/failed/skipped 数量、词汇等级分布、释义降级数量、错误、实际所选词汇路径和成功导出的音频，不含 API key。音频导出失败时保留的旧 MP3 不会被报告为本次成功产物。
- 烧录或音频导出中 Ctrl+C 会杀掉 ffmpeg 并清理临时/半成品文件；此前正式 MP3 保留。

### 词汇配置

项目根目录 `config.toml` 中的可选配置，默认值如下：

```toml
[vocabulary]
enabled = true
learner_level = "N3"
include_unknown = true
max_examples = 3
output_dir = ""  # 空字符串使用 -o；也可填写相对 cwd 或绝对目录
format = "both"  # md、json 或 both
```

`output_dir` 必须是字符串，`format` 只接受 `md`、`json`、`both`；单次运行可用 `--vocab-output-dir`、`--vocab-format` 覆盖。

两个选项分别按「命令行显式参数 → `config.toml` 对应配置 → 默认值」取值。未传词汇参数时，直接执行 `./ja-video-subtitles run video.mp4 -o out` 就会使用配置文件。默认 `format = "both"` 且 `output_dir = ""`，会把 `video.vocab.md` 和 `video.vocab.json` 放到 `out`，与生成的 `video.sub.mp4` 同目录。只传 `--vocab-format md` 时，目录仍使用配置中的 `output_dir`；只传目录参数时，格式仍使用配置中的 `format`。

`learner_level` 仅接受 N5/N4/N3/N2/N1，只收录严格更难的等级，因此 N3 用户得到 N2、N1。`include_unknown` 决定是否收录未分级实义词；专有名词会额外标记，未分级不代表一定较难。`enabled`、`include_unknown` 必须是布尔值，`max_examples` 必须是 1–10 的整数。词条包含基本形、读音、表层形式、出现次数、首次时间，以及最多指定条数的不同日文字幕语境和已有中文译句。没有符合条件的词时仍生成合法空词表。

等级来自固定版本的本地非官方参考数据，不由 API 决定；[数据说明](ja_video_subtitles/data/README.md) 记录来源、许可证及限制。JSON 记录字幕哈希、配置、数据和形态分析版本；仅输出 Markdown 时，复用数据嵌在文件的 HTML 注释中，不生成额外 JSON。仅检查当前所选格式是否有效、新鲜，日文/中文字幕、学习者配置或数据变化会重新生成。切换格式时可利用有效结构化缓存补齐所选文件，不重复请求词义 API。`--force` 强制重跑全部阶段，词汇只重写所选格式；已有成片或 MP3 时，继续处理需 `-y`、`--force` 或在提示中选择覆盖。

设 `enabled = false` 可跳过词汇阶段、词汇目录创建及其依赖检查。若启用后预检发现依赖或数据损坏，可重装固定依赖并恢复同一版本词表：

```bash
uv pip install --python .venv/bin/python --reinstall-package SudachiPy --reinstall-package SudachiDict-core -r requirements.txt
.venv/bin/python ja_video_subtitles/data/rebuild_jlpt.py
```

## 测试

```bash
.venv/bin/python -m unittest discover -s tests
```

离线单测，不依赖模型与 API。

本机安装 ffmpeg 后，可额外运行真实烧录与 MP3 导出测试（自动生成短视频，无需模型或配置）：

```bash
RUN_FFMPEG_TESTS=1 .venv/bin/python -m unittest discover -s tests
```

## 代码结构

见英文版 [README.md](README.md) 的 Code layout 一节（模块职责一一对应）。

独立烧录的 OpenSpec 变更见 [add-standalone-burn-command](openspec/changes/archive/2026-09-13-add-standalone-burn-command/proposal.md)。
词汇表的 OpenSpec 变更见 [add-jlpt-vocabulary-glossary](openspec/changes/archive/2026-09-13-add-jlpt-vocabulary-glossary/proposal.md)。

词汇输出与 MP3 的 OpenSpec 归档变更见 [add-configurable-vocabulary-output-and-mp3](openspec/changes/archive/2026-09-14-add-configurable-vocabulary-output-and-mp3/proposal.md)。

配置回退、各参数独立覆盖及对应测试和注释核查见 [document-vocabulary-config-fallback](openspec/changes/archive/2026-09-15-document-vocabulary-config-fallback/proposal.md)。

## 预期耗时（1 小时视频，M 系芯片）

转写约 10–20 分钟，翻译约 2–5 分钟，烧录约 5–15 分钟（VideoToolbox 硬编）。词汇阶段取决于去重后的目标词数和 API 延迟，实际耗时见报告。

## License

代码使用 MIT，见 `LICENSE`。内置 JLPT 数据另有归属及许可证，见[数据说明](ja_video_subtitles/data/README.md)。
