# Design: add-video-subtitle-pipeline

## 语言选型：Python（而非 Go）

决定因素是 ASR 生态：kotoba-whisper-v2.0 只在 Python 生态有官方支持的推理路径（faster-whisper 格式的 `kotoba-tech/kotoba-whisper-v2.0-faster`）。Go 只能走 whisper.cpp 的 ggml 绑定，而 kotoba 的 ggml 转换没有官方保证，为核心能力引入无谓风险。Go 的单文件分发优势对本机自用工具无意义。

- 运行时：Python 3.12（ctranslate2 对 cp312 有稳定 wheel；3.14 过新不采用）
- 依赖管理：uv 创建 `.venv`
- 依赖清单：faster-whisper、openai、srt、tqdm

## CLI 结构

`ja-video-subtitles` 仅面向日文视频，两个子命令：

```
ja-video-subtitles download                          # 显式下载 ASR 模型到项目内缓存
ja-video-subtitles run <视频文件|文件夹> -o <输出目录> [--force] [-y]
```

- `-o/--output-dir`：必填。全部产物（含中间字幕与成片）写入该目录，主名与源视频一致；源视频目录不被写入任何文件。目录不存在时自动创建（预检阶段创建并验证可写）。
- `--force`：忽略已存在产物，全部阶段重跑（含覆盖同名成片，不再询问）。
- `-y/--yes`：同名成片自动覆盖，适合批量无人值守。

## 架构

五个阶段串成 pipeline，每阶段一个模块，中间产物全部落盘到输出目录。任一阶段失败只影响当前视频；已存在的中间产物默认跳过（`--force` 重跑），天然支持断点续跑与批量。

```
video.mp4（输入，只读）
  → transcribe   → <out>/video.ja.srt (+ <out>/video.ja.json 置信度日志)
  → translate    → <out>/video.zh.srt
  → merge        → <out>/video.bilingual.srt（每条：日文一行 + 中文一行）
  → burn         → <out>/video.sub.mp4
```

### 代码架构（模块划分）

Python 包 `ja_video_subtitles/`，一个阶段一个模块，README 按此结构说明：

```
ja_video_subtitles/
├── cli.py           # 入口：argparse 子命令 run/download，调度 pipeline、同名确认、Tee 日志、报告
├── config.py        # config.toml 加载、默认值合并（tomllib）
├── preflight.py     # 8 项启动预检
├── model.py         # download 子命令：模型下载、就绪标记 .model-ready
├── transcribe.py    # faster-whisper 转写、VAD、幻觉过滤、按标点分段、模型缓存 → ja.srt/ja.json
├── translate.py     # DeepSeek 分批翻译、编号对齐、降级重试 → zh.srt
├── merge.py         # ja/zh 按位置对齐 → bilingual.srt
├── burn.py          # ffmpeg 烧录、-progress 进度解析、stderr 落盘防死锁、失败清理 → sub.mp4
├── ffmpeg_util.py   # ffmpeg/ffprobe 定位（含 libass 检测）、滤镜路径转义
└── report.py        # report-<时间戳>.md 运行报告（不含密钥）
```

模型缓存目录：项目内 `.cache/hf/`（由 `HF_HOME` 指定），`ja-video-subtitles download` 下载后写 `.cache/hf/.model-ready` 就绪标记；README 需说明该目录用途与体积（约 1.5GB）。

## Mac 平台优化

本工具主要运行环境为 macOS（Apple Silicon），以下设计为 Mac 专属优化：

- **烧录硬件编码**：`h264_videotoolbox`（VideoToolbox 硬编），1 小时视频约 5–15 分钟，远快于 libx264 软编。
- **字幕默认字体**：PingFang SC（苹方），macOS 系统自带，无需额外安装字体。
- **ffmpeg 定位**：优先使用 `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg`（brew 全量构建，含 libass），其次 PATH 中带 `subtitles` 滤镜的 ffmpeg。
- **环境管理**：用 uv（brew 安装）创建 `.venv`，Python 固定 3.12（ctranslate2 有稳定 cp312 arm64 wheel）。
- **转写为 CPU int8 推理（如实说明的取舍）**：faster-whisper 的底层 CTranslate2 在 Mac 上没有 Metal 后端，转写跑在 CPU 上；kotoba 是蒸馏模型，int8 下 M 系芯片足够快（1 小时音频约 10–20 分钟）。GPU 加速路径（whisper.cpp/MLX）未被采用，因为 kotoba 没有官方 ggml/MLX 构建，为日文专用模型引入转换风险不值得。

## 关键决策

### 模型分发
- ASR 模型（约 1.5GB）不随 `run` 自动下载，由 `ja-video-subtitles download` 显式完成，下载成功后写入就绪标记 `.cache/hf/.model-ready`。
- `run` 的预检校验标记与模型文件存在；缺失则报错「请先运行 ja-video-subtitles download」并退出。
- 模型缓存放项目内 `.cache/hf`（`HF_HOME`），不污染用户全局目录。

### 转写
- 模型 `kotoba-tech/kotoba-whisper-v2.0-faster`，`language="ja"`，`compute_type="int8"`。
- 幻觉防护三件套（长视频必需）：VAD 过滤（`vad_filter=True`）、`condition_on_previous_text=False`、后处理规则（高 no_speech_prob + 低 avg_logprob 丢弃；与上一条完全重复丢弃）。
- 进度条：faster-whisper 逐 segment 返回，用 segment 结束时间 / 音频总时长驱动 tqdm。

### 翻译
- OpenAI 兼容 client，`base_url`/`api_key`/`model` 全部走 `config.toml`。
- 分批：每批 ≤20 条且原文合计 ≤800 字符；附上一批末尾 2 条作为「仅供上下文、不翻译」。
- 对齐协议：批内编号 `1..N` 输入，要求模型严格输出 `编号. 译文`；解析后校验编号完整，缺失则整批重试（最多 2 次），再失败则拆半递归，单条仍失败则保留原文并打印警告，不中断流程。
- 默认 prompt 约束：口语化、每条译文 ≤24 个汉字、专有名词保持一致。prompt 在 config 中可覆盖。

### 双语合成
- 按 index 逐条对齐 `ja.srt` 与 `zh.srt`（时间轴沿用转写结果），每条输出两行：上行日文、下行中文。
- 翻译缺条（极端降级情况）时该条仅保留日文，不阻塞。

### 同名成片处理（烧录前确认）
- 预检通过后、开始处理前，统一检查所有待处理视频在输出目录的同名成片 `<out>/xxx.sub.mp4`。
- 已存在且未给 `--force`/`-y`：逐个交互询问「覆盖？[y/N]」；选否则该视频标记为跳过，其余视频照常处理。
- 所有确认动作在处理开始前完成；**烧录一旦开始，任何情况下不中断等待用户输入**。
- 中间产物（srt/json）存在时按断点续跑语义跳过对应阶段，不询问。

### 烧录
- 预检时定位带 `subtitles` 滤镜的 ffmpeg：优先 `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg`，其次 PATH 中支持该滤镜的 `ffmpeg`；都没有则预检失败。
- `force_style` 默认：苹方（PingFang SC）、白字黑描边、底部居中、MarginV=28；可在 config 覆盖。
- 编码：`h264_videotoolbox` 硬件编码（1 小时视频约 5–15 分钟），音频 `-c:a copy` 直通。
- 烧录进度条：解析 `ffmpeg -progress pipe:1` 的 `out_time` 与视频总时长换算。

### 启动预检（全部通过才开始处理）
0. 运行平台为 macOS（不支持 Windows / Linux）；
1. Python ≥ 3.12 及必需包可导入；
2. 存在带 `subtitles` 滤镜的 ffmpeg；
3. `config.toml` 存在、api_key 非空且非占位符；
4. DeepSeek API 连通性（一次最小 chat 请求，max_tokens=1）；
5. ASR 模型已下载（就绪标记存在），否则提示 `ja-video-subtitles download`；
6. 磁盘剩余空间 ≥ 待处理视频总大小 × 2；
7. 输入路径存在、输出目录已创建且可写。
任一失败：打印缺失项与修复指引，退出码非零。

## 配置

`config.toml`（不入库，`.gitignore` 排除）+ `config.example.toml`（入库模板）。使用 stdlib `tomllib` 解析，零额外依赖。

## 风险

- DeepSeek 长批次偶发不遵守编号格式：靠对齐校验 + 拆半重试兜底，已覆盖。
- 无风扇机型长时间烧录降频：仅影响速度，不影响正确性；README 中给出预期耗时。
- 批量时交互询问打断：同名确认全部前置到处理开始前，另提供 `-y` 跳过交互。
