# ja-video-subtitles

**任意日文视频 → 一条命令 → 日/中双语硬字幕成片。**

流水线：`视频 → 日文转写(kotoba-whisper) → 日译中(DeepSeek) → 双语合成 → 烧录(ffmpeg)`

## 工作流程

| 阶段 | 做什么 | 产物 |
|---|---|---|
| 转写 | 本地 ASR（kotoba-whisper，CPU，不走网络）：日语音频 → 带时间轴日文字幕，含 VAD、幻觉过滤、按标点分段 | `xxx.ja.srt` |
| 翻译 | 日译中，走 DeepSeek API，分批带上下文、编号校验，异常自动重试降级 | `xxx.zh.srt` |
| 双语合成 | 日/中逐条对齐（上日下中），纯本地，瞬间完成 | `xxx.bilingual.srt` |
| 烧录 | ffmpeg 把字幕逐帧画进画面，VideoToolbox 硬编出成片 | `xxx.sub.mp4` |

转写和烧录吃本机算力，翻译走网络，合成是文件拼接。各阶段耗时见报告 `report-*.md`。

支持 mp4/mov，单文件或文件夹批量。产物全部写入 `-o` 目录，源目录零写入。

> **输入必须是日语语音。** 转写固定 `language="ja"`（kotoba-whisper 是日文专用模型），不做语言检测：喂入非日文音频不会报错，只会静默产出垃圾字幕。

## 平台

**仅支持 macOS（Apple Silicon），不支持 Windows / Linux**——烧录依赖 VideoToolbox 硬编、苹方字体和 Homebrew 的 ffmpeg 路径。其他平台预检直接报错退出。

## 依赖

| 依赖 | 用途 | 安装 |
|---|---|---|
| Homebrew | 包管理 | `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"` |
| uv | Python 环境管理 | `brew install uv` |
| Python 3.12 | 运行时 | `uv venv` 自动安装 |
| ffmpeg-full | 字幕烧录（libass） | `brew install homebrew-ffmpeg/ffmpeg/ffmpeg-full` |
| DeepSeek API Key | 日译中 | <https://platform.deepseek.com>（1 小时视频 < 1 元） |

字幕字体为 macOS 自带苹方，无需安装。

## 安装

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp config.example.toml config.toml   # 填入 deepseek.api_key
./ja-video-subtitles download                 # 一次性下载 ASR 模型（约 1.5GB）
```

模型存放在项目内 `.cache/hf/`（`HF_HOME` 已固定），下载成功写 `.model-ready` 标记。默认走 `hf-mirror.com` 镜像，可用 `HF_ENDPOINT=https://huggingface.co` 覆盖。

## 用法

```bash
./ja-video-subtitles run /path/to/xxx.mp4 -o /path/to/output   # 单文件
./ja-video-subtitles run /path/to/dir   -o /path/to/output     # 文件夹批量
./ja-video-subtitles run /path/to/dir   -o out -y              # 同名自动覆盖
./ja-video-subtitles run xxx.mp4 -o out --force                # 全部重跑
```

产物（都在 `-o` 目录）：`xxx.ja.srt`（日文）、`xxx.zh.srt`（中文）、`xxx.bilingual.srt`（双语，上日下中）、`xxx.sub.mp4`（成片）、`report-<时间戳>.md`（运行报告）、`run.log`（日志）。

行为要点：

- 相对路径以执行命令时的目录为准；config 与模型缓存始终从项目目录读取。
- 断点续跑：已有合法产物自动跳过；损坏产物自动重跑。
- 同名成片在处理开始前统一询问；烧录过程不中断。非交互环境默认不覆盖。
- 预检 8 项（平台、Python 依赖、ffmpeg+libass、config/api_key、DeepSeek 连通、模型就绪、磁盘空间、输出目录可写），任一失败立即退出并给出修复指引。
- 烧录中 Ctrl+C 会杀掉 ffmpeg 并清理半成品。

## 测试

```bash
.venv/bin/python -m unittest discover -s tests
```

离线单测，不依赖模型与 API。

## 代码结构

见英文版 [README.md](README.md) 的 Code layout 一节（模块职责一一对应）。

## 预期耗时（1 小时视频，M 系芯片）

转写约 10–20 分钟，翻译约 2–5 分钟，烧录约 5–15 分钟（VideoToolbox 硬编）。

## License

MIT，见 `LICENSE`。
