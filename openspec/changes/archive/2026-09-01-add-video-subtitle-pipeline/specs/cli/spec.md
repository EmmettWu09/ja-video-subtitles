# Spec: cli

## ADDED Requirements

### Requirement: 平台约束
工具仅支持 macOS（Apple Silicon），明确不支持 Windows / Linux。预检 SHALL 检查运行平台，非 macOS 时立即报错退出，不开始任何处理。

#### Scenario: 非 macOS 平台
- **WHEN** 在 Windows 或 Linux 上执行 `ja-video-subtitles run ...`
- **THEN** 预检失败，提示仅支持 macOS，退出码非零

### Requirement: 命令结构
CLI 命令为 `ja-video-subtitles`，仅处理日文视频，提供两个子命令：`download`（下载 ASR 模型）和 `run <视频文件|文件夹> -o <输出目录> [--force] [-y]`（执行处理流水线）。输入支持 mp4 与 mov 容器（成片统一输出为 mp4）。`run` 的 `-o/--output-dir` SHALL 为必填参数，且全部产物只写入该目录，源视频目录 SHALL NOT 被写入任何文件。

#### Scenario: 单文件处理
- **WHEN** 用户执行 `ja-video-subtitles run /path/to/xxx.mp4 -o /path/to/out` 且预检通过
- **THEN** 依次执行转写、翻译、双语合成、烧录，产物全部生成在 `/path/to/out`：`xxx.ja.srt`、`xxx.zh.srt`、`xxx.bilingual.srt`、`xxx.sub.mp4`，源目录无新增文件

#### Scenario: 文件夹批量
- **WHEN** 用户执行 `ja-video-subtitles run /path/to/dir -o /path/to/out`，输入目录下含多个 mp4
- **THEN** 串行处理每个 mp4；单个视频失败 SHALL 记录错误并继续处理其余视频，全部结束后打印成功/失败/跳过汇总

#### Scenario: 参数非法
- **WHEN** 缺少位置参数、缺少 `-o`、或输入路径不存在/非 mp4/mov
- **THEN** 打印用法说明，退出码非零，不执行任何处理

### Requirement: 模型下载子命令
`ja-video-subtitles download` SHALL 将 ASR 模型下载到项目内缓存目录并显示下载进度，成功后写入就绪标记。`run` SHALL NOT 自动下载模型；预检发现模型未就绪时，报错提示用户先运行 `ja-video-subtitles download`，并以非零退出码退出。

#### Scenario: 模型未下载
- **WHEN** 首次使用，用户直接执行 `ja-video-subtitles run xxx.mp4 -o out` 而未执行过 `download`
- **THEN** 预检失败，提示「请先运行 ja-video-subtitles download」，退出码非零，不开始任何处理

#### Scenario: 下载成功
- **WHEN** 用户执行 `ja-video-subtitles download`
- **THEN** 模型下载到项目内缓存目录，终端显示进度，完成后写入就绪标记

### Requirement: 进度显示
每个处理阶段 SHALL 在终端打印实时进度条：转写按已处理音频时长、翻译按批次、烧录按已编码时长。批量处理时进度条按文件分别显示。

#### Scenario: 转写进度
- **WHEN** 正在转写 1 小时的视频
- **THEN** 进度条随转写推进实时更新，百分比可估算剩余时间

### Requirement: 启动预检
在 `run` 处理任何视频之前，SHALL 依次完成全部预检：Python 环境与必需包、带 subtitles 滤镜的 ffmpeg、config.toml 存在且 api_key 有效、DeepSeek API 连通、ASR 模型已就绪、磁盘空间充足（≥ 视频总大小 × 2）、输出目录已创建且可写。

#### Scenario: 预检失败
- **WHEN** 任一预检项不满足（如 config.toml 缺失）
- **THEN** 逐条打印失败项及修复指引，立即以非零退出码结束，不开始任何转写或烧录

### Requirement: 同名成片确认
预检通过后、开始处理前，SHALL 统一检查每个待处理视频在输出目录的同名成片 `xxx.sub.mp4`：已存在且未指定 `--force`/`-y` 时，逐个提示用户选择覆盖或跳过；选跳过的视频不处理。全部确认 SHALL 在处理开始前完成；烧录过程 SHALL NOT 中断等待用户输入。`-y` 表示全部自动覆盖。

#### Scenario: 同名文件选择覆盖
- **WHEN** 输出目录已存在 `xxx.sub.mp4`，用户在提示中输入 y
- **THEN** 该视频正常处理并覆盖成片

#### Scenario: 同名文件选择跳过
- **WHEN** 输出目录已存在 `xxx.sub.mp4`，用户在提示中输入 N
- **THEN** 该视频标记为跳过，继续处理其余视频，汇总中体现

#### Scenario: 非交互环境
- **WHEN** 在 nohup/管道等无 stdin 的环境中运行，且存在同名成片
- **THEN** 不抛异常，按「不覆盖」跳过该视频并打印提示

#### Scenario: 烧录不中断
- **WHEN** 烧录阶段正在进行
- **THEN** 全程无任何交互式询问，直至该视频烧录完成

### Requirement: 运行日志
`run`  SHALL 将全部终端输出同时写入输出目录的 `run.log`（追加模式），批量长任务中断后可根据日志定位失败位置。

#### Scenario: 日志落盘
- **WHEN** 批量处理完成或中途失败
- **THEN** 输出目录的 `run.log` 包含各阶段记录与最终汇总

### Requirement: 运行报告
`run` 结束时 SHALL 在输出目录生成 `report-<时间戳>.md`：包含开始/结束时间与总耗时、工具版本、配置摘要（ASR 模型、翻译模型与 base_url、烧录码率；SHALL NOT 包含 api_key）、成功/失败/跳过汇总，以及每个视频的阶段耗时表（跳过阶段标注）、失败原因、产物清单（文件名、大小、字幕条数）。

#### Scenario: 生成报告
- **WHEN** 一次 `run` 处理完所有视频
- **THEN** 输出目录生成报告文件，内容覆盖上述字段，且不包含任何密钥信息

### Requirement: 产物复用与强制重跑
输出目录中中间产物（`xxx.ja.srt`、`xxx.zh.srt`、`xxx.bilingual.srt`）已存在时，对应阶段 SHALL 默认跳过（不询问）；产物无法解析或为空时 SHALL 视为损坏并重跑该阶段；`--force` 强制全部阶段重跑并覆盖所有同名产物（不再询问）。

#### Scenario: 断点续跑
- **WHEN** 上次运行在翻译阶段失败，输出目录已有 `xxx.ja.srt`，用户修复后再次执行同一命令
- **THEN** 跳过转写，从翻译继续

#### Scenario: 强制重跑
- **WHEN** 用户执行 `ja-video-subtitles run xxx.mp4 -o out --force`
- **THEN** 忽略全部已有产物（含成片），完整重跑所有阶段
