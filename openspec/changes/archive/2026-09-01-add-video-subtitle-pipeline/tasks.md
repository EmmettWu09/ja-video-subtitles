# Tasks: add-video-subtitle-pipeline

## 1. 脚手架
- [x] 1.1 `uv venv --python 3.12 .venv`，`requirements.txt`：faster-whisper、openai、srt、tqdm
- [x] 1.2 `config.example.toml` 模板 + `.gitignore`（排除 config.toml、.cache/、.venv/）
- [x] 1.3 README.md，须包含：
  - 依赖安装清单及命令（uv、Python 3.12、ffmpeg-full 的 brew 安装命令）
  - **venv 设置步骤**：`uv venv --python 3.12 .venv` → `uv pip install -r requirements.txt` → 激活方式
  - **代码架构说明**：`ja_video_subtitles/` 各模块职责（对照 design.md 的模块划分）
  - **ASR 模型目录说明**：`ja-video-subtitles download` 下载到项目内 `.cache/hf/`（约 1.5GB），`.model-ready` 就绪标记
  - 配置方法（cp config.example.toml config.toml，填 api_key）、用法、产物说明、预期耗时

## 2. 配置模块
- [x] 2.1 加载 `config.toml`（tomllib），缺失字段回退默认值，api_key 无默认值
- [x] 2.2 默认翻译 prompt 内置为常量，config 中可覆盖

## 3. 预检
- [x] 3.1 实现全部 8 项预检（平台为 macOS、Python 依赖、ffmpeg+libass、config/api_key、DeepSeek 连通、ASR 模型就绪标记、磁盘空间、输出目录可写），失败项逐条打印 + 修复指引 + 非零退出

## 4. 模型下载子命令
- [x] 4.1 `ja-video-subtitles download`：下载 kotoba-whisper-v2.0-faster 到项目内 `.cache/hf`，显示下载进度，成功后写 `.model-ready` 就绪标记

## 5. 转写
- [x] 5.1 faster-whisper + kotoba-whisper-v2.0-faster，VAD + 幻觉过滤
- [x] 5.2 输出 `<out>/xxx.ja.srt` 与 `<out>/xxx.ja.json`（置信度日志），tqdm 进度条
- [x] 5.3 按句末标点拆分长段字幕，时间戳按字符占比线性分配
- [x] 5.4 模型实例按 ID 缓存，批量只加载一次

## 6. 翻译
- [x] 6.1 分批 + 上下文 + 编号对齐校验 + 重试/拆半降级
- [x] 6.2 输出 `<out>/xxx.zh.srt`，按批数显示进度条

## 7. 双语合成
- [x] 7.1 按 index 对齐生成 `<out>/xxx.bilingual.srt`（上行日文、下行中文）

## 8. 烧录
- [x] 8.1 subtitles 滤镜 + force_style，h264_videotoolbox + 音频直通，输出 `<out>/xxx.sub.mp4`
- [x] 8.2 解析 `ffmpeg -progress` 显示烧录进度条

## 9. CLI 入口
- [x] 9.1 子命令结构：`ja-video-subtitles download` / `ja-video-subtitles run <路径> -o <目录> [--force] [-y]`；文件夹处理其中全部 mp4
- [x] 9.2 处理开始前统一做同名成片检查并交互确认（覆盖/跳过），烧录过程不中断；`-y` 跳过交互
- [x] 9.3 批量时逐文件串行处理，单文件失败不中断其余文件，结束打印成功/失败/跳过汇总

## 10. 验证
- [x] 10.1 用 macOS `say -v Kyoko` 合成日文音频 + lavfi 生成测试视频，端到端跑通 run 全流程
- [x] 10.2 校验：产物全部落在 -o 目录、命名正确、双语字幕内容、烧录成品可播放、同名确认交互符合预期、未下载模型时 run 正确报错退出；真实视频 + 真实 DeepSeek 翻译已验证

## 11. 健壮性加固（review 后修复）
- [x] 11.1 burn：修复错误路径 TypeError；stderr 落临时文件防 PIPE 死锁；Ctrl+C/失败时杀子进程并清理半成品
- [x] 11.2 入口脚本不再 cd，相对路径以调用者 cwd 为准；config 按包位置解析
- [x] 11.3 断点续跑校验中间产物（非空 + 可解析），损坏自动重跑
- [x] 11.4 非交互环境同名确认 EOFError 按不覆盖处理；预检磁盘检查向上找已存在父目录
- [x] 11.5 滤镜路径转义补逗号；ffmpeg_util 独立成模块

## 12. 可观测性与发布
- [x] 12.1 run.log：终端输出 tee 到输出目录
- [x] 12.2 report-<时间戳>.md 运行报告（配置摘要不含 api_key、阶段耗时、产物清单、失败原因）
- [x] 12.3 `tests/test_smoke.py` 14 个离线单测；`--version`
- [x] 12.4 MIT LICENSE（无个人署名）；用户可见输出与注释全部英文化；README 英/中/日三语
