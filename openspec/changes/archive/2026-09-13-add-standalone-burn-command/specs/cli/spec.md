# Spec: cli

## MODIFIED Requirements

### Requirement: 命令结构

CLI 命令为 `ja-video-subtitles`，SHALL 提供 `download`（下载 ASR 模型）、`run <视频文件|文件夹> -o <输出目录> [--force] [-y]`（执行日文转写、翻译、双语合成和烧录流水线）以及 `burn <input> [<input> ...] -o <输出目录> [-s <字幕文件> | --subtitle-dir <字幕目录>] [-y]`（将现有 SRT 烧录进视频）。输入支持 mp4/mov 容器，成片统一输出 mp4。`run` 与 `burn` 的 `-o/--output-dir` SHALL 必填，全部新产物仅写入该目录，SHALL NOT 修改源视频。`burn` SHALL NOT 执行转写、翻译或双语合成。

#### Scenario: 单文件处理

- **WHEN** 执行 `ja-video-subtitles run /path/to/xxx.mp4 -o /path/to/out` 且预检通过
- **THEN** 依次执行转写、翻译、双语合成、烧录，产物为输出目录内的 `xxx.ja.srt`、`xxx.zh.srt`、`xxx.bilingual.srt`、`xxx.sub.mp4`，源目录无新增文件

#### Scenario: 文件夹批量

- **WHEN** 执行 `ja-video-subtitles run /path/to/dir -o /path/to/out`
- **THEN** 串行处理目录中的 mp4/mov，单个失败不阻塞其余视频，并打印成功/失败/跳过汇总

#### Scenario: 单文件独立烧录

- **WHEN** 执行 `ja-video-subtitles burn xxx.mp4 -s edited.srt -o out`
- **THEN** 仅将现有 `edited.srt` 烧录到 `out/xxx.sub.mp4`，不生成或修改任何字幕文件

#### Scenario: 参数非法

- **WHEN** 缺少输入或 `-o`，输入不存在/格式不支持，或者同时传入 `-s` 与 `--subtitle-dir`
- **THEN** 打印参数用法或具体检查错误，退出码为 2，不开始烧录

### Requirement: 启动预检

`run` SHALL 保留完整预检：Python 环境与必需包、带 subtitles 滤镜的 ffmpeg、config.toml 存在且 api_key 有效、DeepSeek API 连通、ASR 模型已就绪、磁盘空间充足（≥ 视频总大小 × 2）、输出目录已创建且可写。`burn` SHALL 仅检查 macOS 平台、烧录需要的 Python 环境与包、ffmpeg/libass 与 ffprobe、磁盘空间（≥ 去重后视频总大小 × 2）及输出目录可写性，SHALL NOT 检查或初始化翻译 API 与 ASR 模型。全部字幕映射与预检 SHALL 在任一视频烧录前完成。

#### Scenario: 预检失败

- **WHEN** `run` 任一预检不满足，如 config.toml 缺失
- **THEN** 打印失败项与修复指引，立即以非零退出码结束，不开始处理

#### Scenario: 独立烧录不依赖 API 或模型

- **WHEN** 未配置 DeepSeek key 且 ASR 模型未下载，但烧录依赖和字幕有效
- **THEN** `burn` 可正常执行，无网络访问且不要求模型下载

#### Scenario: 独立烧录预检失败

- **WHEN** `burn` 缺少烧录依赖、磁盘不足或输出目录不可写
- **THEN** 给出修复指引，以退出码 2 结束，不开始任何视频烧录

### Requirement: 同名成片确认

`run` 与 `burn` 在预检通过后、开始处理前 SHALL 统一检查每个视频的 `<stem>.sub.mp4`。已存在且未指定 `-y/--yes` 时逐个提示覆盖或跳过；`run --force` 同样自动覆盖。全部确认 SHALL 在处理开始前完成，烧录过程 SHALL NOT 中断等待输入；未确认的视频 SHALL 跳过。`burn` 不提供 `--force`。

#### Scenario: 同名文件选择覆盖

- **WHEN** 已有成片，用户输入 y 或指定 `-y`
- **THEN** 正常处理并覆盖该成片

#### Scenario: 同名文件选择跳过

- **WHEN** 已有成片，用户输入 N
- **THEN** 标记跳过，保留既有成片，继续其他视频并在汇总中体现

#### Scenario: 非交互环境

- **WHEN** 存在同名成片且 stdin EOF，又未指定自动覆盖
- **THEN** 不抛异常，跳过该视频并打印提示

#### Scenario: 烧录不中断

- **WHEN** 任一视频进入烧录阶段
- **THEN** 后续不再弹出本批次的覆盖提示

### Requirement: 运行日志

`run` 与 `burn` SHALL 将终端输出同时追加到输出目录的 `run.log`，包含视频处理、错误与最终汇总。

#### Scenario: 日志落盘

- **WHEN** `run` 或 `burn` 全部处理完成或其中一个视频失败
- **THEN** `run.log` 包含各视频的烧录记录、错误及汇总

### Requirement: 运行报告

`run` 与 `burn` 结束时 SHALL 在输出目录生成 `report-<时间戳>.md`，包含开始/结束时间与总耗时、工具版本、配置摘要、成功/失败/跳过汇总，以及每个视频的实际阶段耗时、失败原因和产物清单。`run` 配置摘要包含 ASR 模型、翻译模型与 base_url、烧录码率。`burn` SHALL 明确标记 burn-only，并将模型及翻译服务标记为 N/A，列出实际字幕输入与成片，不得将未执行的转写/翻译/合成阶段显示为成功。报告 SHALL NOT 包含 api_key。

#### Scenario: 生成报告

- **WHEN** `run` 处理完所有视频
- **THEN** 输出目录生成包含配置摘要、阶段耗时、产物和汇总且不含密钥的报告

#### Scenario: 独立烧录报告

- **WHEN** `burn` 处理完所有视频
- **THEN** 报告记录 burn-only、模型/翻译 N/A、烧录耗时、字幕来源及每个视频的最终结果

## ADDED Requirements

### Requirement: 独立烧录多输入展开

`burn` SHALL 接受一个或多个文件或目录路径，按参数顺序展开。目录 SHALL 仅枚举当前层 mp4/mov 文件，按文件名排序，忽略子目录和其他格式。SHALL 按解析后路径去重并保留首次出现顺序。任一显式指定的目录在当前层没有 mp4/mov，或最终没有有效视频时，SHALL 以退出码 2 拒绝整批请求。不同源视频的主干名不区分大小写冲突时 SHALL 拒绝整批请求。

#### Scenario: 多个文件与目录混合

- **WHEN** 执行 `burn a.mp4 videos/ b.mov -o out`，目录内包含 `c.mp4`、`d.mov` 和子目录
- **THEN** 按输入位置及目录排序串行处理四个视频，不递归进入子目录

#### Scenario: 重复源路径

- **WHEN** 同一视频通过直接路径、目录或符号链接重复出现
- **THEN** 解析路径去重后仅烧录一次，位置采用首次出现的顺序

#### Scenario: 无匹配视频

- **WHEN** 任一显式输入目录没有当前层 mp4/mov，即使其他输入包含有效视频
- **THEN** 退出码为 2，指出无匹配视频的目录，不烧录任一视频

#### Scenario: 主干名冲突

- **WHEN** 输入包含不同视频 `a/clip.mp4` 与 `b/CLIP.mov`
- **THEN** 在处理前报告同名冲突，以退出码 2 结束，不烧录任一视频

### Requirement: 独立烧录批次结果

`burn` SHALL 串行处理所有已确认任务。单视频烧录失败 SHALL 记录原因并继续其余视频。所有视频成功或跳过时退出码 SHALL 为 0，至少一个烧录失败时 SHALL 为 1，输入、字幕、配置或预检错误时 SHALL 为 2 且无视频开始烧录。

#### Scenario: 部分视频失败

- **WHEN** 第一个视频烧录失败，后面还有待处理视频
- **THEN** 继续烧录后续视频，汇总包含失败数，最终退出码为 1

#### Scenario: 全部跳过

- **WHEN** 用户跳过全部已有成片
- **THEN** 不启动 ffmpeg，汇总记录全部跳过，退出码为 0
