# Spec: cli

## MODIFIED Requirements

### Requirement: 命令结构

CLI 命令为 `ja-video-subtitles`，SHALL 提供 `download`（下载 ASR 模型）、`run <视频文件|文件夹> -o <输出目录> [--vocab-output-dir <词汇目录>] [--vocab-format md|json|both] [--force] [-y]`（执行日文转写、翻译、可配置词汇阶段、双语合成、烧录和 MP3 导出流水线）以及 `burn <input> [<input> ...] -o <输出目录> [-s <字幕文件> | --subtitle-dir <字幕目录>] [-y]`（将现有 SRT 烧录进视频）。输入支持 mp4/mov 容器，成片统一输出 mp4。`run` 与 `burn` 的 `-o/--output-dir` SHALL 必填，字幕、成片、MP3、日志和报告 SHALL 写入该目录，词汇产物 SHALL 写入有效词汇目录，SHALL NOT 修改源视频。`run` 的 vocabulary 阶段 SHALL 在翻译后、双语合成前执行；启用时 SHALL 按 `md`、`json`、`both` 在有效词汇目录生成对应的 `<stem>.vocab.md` 和/或 `<stem>.vocab.json`，默认两种格式均输出到 `-o`。`run` SHALL 在烧录成功后导出 `<output-dir>/<stem>.mp3`。`burn` SHALL NOT 执行转写、翻译、词汇提取、双语合成或 MP3 导出。

#### Scenario: 单文件处理

- **WHEN** 执行 `ja-video-subtitles run /path/to/xxx.mp4 -o /path/to/out` 且预检通过
- **THEN** 依次执行转写、翻译、启用的词汇阶段、双语合成、烧录和 MP3 导出，产物为输出目录内的 `xxx.ja.srt`、`xxx.zh.srt`、`xxx.bilingual.srt`、`xxx.sub.mp4`、`xxx.mp3`，词汇启用时增加 `xxx.vocab.md` 和 `xxx.vocab.json`，源目录无新增文件

#### Scenario: 文件夹批量

- **WHEN** 执行 `ja-video-subtitles run /path/to/dir -o /path/to/out`
- **THEN** 串行处理目录中的 mp4/mov，单个失败不阻塞其余视频，并打印 succeeded/partial/failed/skipped 汇总

#### Scenario: 单文件独立烧录

- **WHEN** 执行 `ja-video-subtitles burn xxx.mp4 -s edited.srt -o out`
- **THEN** 仅将现有 `edited.srt` 烧录到 `out/xxx.sub.mp4`，不生成或修改任何字幕文件

#### Scenario: 参数非法

- **WHEN** 缺少输入或 `-o`，输入不存在/格式不支持，或者同时传入 `-s` 与 `--subtitle-dir`
- **THEN** 打印参数用法或具体检查错误，退出码为 2，不开始烧录

#### Scenario: 启用词汇功能

- **WHEN** 用户执行 `ja-video-subtitles run video.mp4 -o out` 且 vocabulary.enabled 为 true
- **THEN** 翻译后提取词汇，默认输出目录包含词汇 Markdown、结构化 JSON、字幕、成片和 MP3

#### Scenario: 自定义词汇目录和单格式

- **WHEN** 执行 `run video.mp4 -o media --vocab-output-dir words --vocab-format json` 且词汇已启用
- **THEN** 词汇仅写入 `words/video.vocab.json`，不新建 Markdown，字幕、MP3、成片、日志与报告仍写入 `media`

#### Scenario: 词汇格式参数非法

- **WHEN** `--vocab-format` 不为 `md`、`json`、`both`
- **THEN** 参数解析失败并给出合法值，退出码为 2，不开始处理

#### Scenario: 词汇禁用

- **WHEN** vocabulary.enabled 为 false，但命令包含合法词汇目录和格式参数
- **THEN** 不创建词汇目录、不生成词汇文件，正常生成字幕、成片和 MP3

#### Scenario: 完整流水线输出冲突

- **WHEN** 不同输入视频主干名经规范化后相同，或计划输出路径之间冲突、可能覆盖源视频
- **THEN** 在处理前拒绝整批请求并给出冲突路径，退出码为 2


### Requirement: 启动预检

`run` SHALL 保留完整预检：Python 环境与必需包、带 subtitles 滤镜及 MP3 编码器的 ffmpeg 和 ffprobe、config.toml 存在且 api_key 有效、DeepSeek API 连通、ASR 模型已就绪、磁盘空间充足（≥ 视频总大小 × 2）、输出目录已创建且可写。`burn` SHALL 仅检查 macOS 平台、烧录需要的 Python 环境与包、ffmpeg/libass 与 ffprobe、磁盘空间（≥ 去重后视频总大小 × 2）及输出目录可写性，SHALL NOT 检查或初始化翻译 API、ASR 模型、词汇分词器及其词典或 JLPT 数据。`run` 在 vocabulary.enabled 为 true 时 SHALL 额外创建并检查有效词汇目录可写，验证形态分析依赖、本地形态词典及 JLPT 数据的 schema、版本和校验和；任一缺失或损坏 SHALL 在处理前失败并给出修复指引。功能禁用时 SHALL 跳过词汇相关目录创建与检查。全部字幕映射与预检 SHALL 在任一视频烧录前完成。

#### Scenario: 预检失败

- **WHEN** `run` 任一预检不满足，如 config.toml 缺失
- **THEN** 打印失败项与修复指引，立即以非零退出码结束，不开始处理

#### Scenario: 独立烧录不依赖 API 或模型

- **WHEN** 未配置 DeepSeek key 且 ASR 模型未下载，但烧录依赖和字幕有效
- **THEN** `burn` 可正常执行，无网络访问且不要求模型下载

#### Scenario: 独立烧录预检失败

- **WHEN** `burn` 缺少烧录依赖、磁盘不足或输出目录不可写
- **THEN** 给出修复指引，以退出码 2 结束，不开始任何视频烧录

#### Scenario: JLPT 数据缺失

- **WHEN** vocabulary 已启用但 JLPT 数据不存在或校验失败
- **THEN** 预检失败，不开始视频处理，并说明如何安装或恢复数据

#### Scenario: 禁用词汇依赖检查

- **WHEN** `run` 的 vocabulary.enabled 为 false，或执行独立 `burn`
- **THEN** 不加载词汇分词器及其词典、不要求 JLPT 数据就绪，继续各自其余预检

#### Scenario: 词汇目录不可用

- **WHEN** 词汇启用，但有效词汇目录是普通文件、不能创建或不可写
- **THEN** 在视频处理前失败，指出词汇目录问题，退出码为 2

#### Scenario: 音频编码依赖缺失

- **WHEN** `run` 所用 ffmpeg 缺少 MP3 编码器
- **THEN** 预检失败并提示修复，以退出码 2 结束；独立 `burn` 不检查 MP3 编码器


### Requirement: 同名成片确认

`run` 与 `burn` 在预检通过后、开始处理前 SHALL 统一检查每个视频的 `<stem>.sub.mp4`；`run` SHALL 同时检查 `<stem>.mp3`。任一目标存在都 SHALL 纳入该视频的覆盖确认。已存在且未指定 `-y/--yes` 时逐个提示覆盖或跳过；`run --force` 同样自动覆盖。全部确认 SHALL 在处理开始前完成，烧录过程 SHALL NOT 中断等待输入；未确认的视频 SHALL 整体跳过，保留该视频已有成片和 MP3。`burn` 不提供 `--force`。

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

#### Scenario: 只有同名音频

- **WHEN** `run` 目标目录仅存在 `<stem>.mp3`，未指定 `-y` 或 `--force`
- **THEN** 同样在处理前提示覆盖或跳过；拒绝或 EOF 时跳过该视频且保留旧 MP3

#### Scenario: 自动覆盖成片与音频

- **WHEN** `run` 指定 `-y` 或 `--force`，已有成片和/或 MP3
- **THEN** 不再询问，处理该视频并在对应阶段成功后覆盖目标


### Requirement: 运行报告

`run` 与 `burn` 结束时 SHALL 在输出目录生成 `report-<时间戳>.md`，包含开始/结束时间与总耗时、工具版本、配置摘要、成功/失败/跳过汇总；`run` 另包含 partial 数量，以及每个视频的实际阶段耗时、失败原因和产物清单。`run` 配置摘要包含 ASR 模型、翻译模型与 base_url、烧录码率、有效词汇输出目录和格式。`burn` SHALL 明确标记 burn-only，并将模型及翻译服务标记为 N/A，列出实际字幕输入与成片，不得将未执行的转写/翻译/合成阶段显示为成功。`run` 报告 SHALL 记录 Vocabulary 阶段耗时、词汇产物、目标词总数、N2/N1/未分级及释义降级数量；词汇阶段级失败 SHALL 记录错误和 partial 状态。词汇产物 SHALL 按本次启用状态、所选格式和实际目录列举，SHALL NOT 将未选中的历史词汇文件列为本次产物。`run` SHALL 记录音频阶段耗时、成功导出的 MP3 路径及音频错误；音频失败 SHALL 标记 partial，不得将遗留旧 MP3 报为成功导出。词汇和音频同时失败时 SHALL 保留两者原因。`burn` 报告 SHALL NOT 显示未执行的音频阶段。`run` 中任何视频为 partial 或 failed 时，退出码 SHALL 为 1；其余成功或跳过时 SHALL 为 0。单词级释义降级不改变视频成功状态，SHALL 保留 warning 和降级计数。报告 SHALL NOT 包含 api_key。

#### Scenario: 生成报告

- **WHEN** `run` 处理完所有视频
- **THEN** 输出目录生成包含配置摘要、阶段耗时、产物和汇总且不含密钥的报告

#### Scenario: 独立烧录报告

- **WHEN** `burn` 处理完所有视频
- **THEN** 报告记录 burn-only、模型/翻译 N/A、烧录耗时、字幕来源及每个视频的最终结果

#### Scenario: 部分成功

- **WHEN** 视频烧录成功但词汇阶段级失败
- **THEN** 报告列出视频成片和已有产物、词汇错误原因及 partial 状态，命令退出码为 1

#### Scenario: 释义降级

- **WHEN** 词汇文件生成成功，但一个词在重试和拆分后仍无法取得合法释义，其余阶段成功
- **THEN** 视频保持成功，报告增加一次释义降级计数，词条保留 warning 和空释义

#### Scenario: 独立目录与历史格式

- **WHEN** 本次只选 `md` 并输出到词汇目录，主输出目录或词汇目录存在旧 JSON
- **THEN** 报告列出真实 Markdown 路径及 md 格式，不列旧 JSON；字幕、视频和成功导出的 MP3 路径仍来自 `-o`

#### Scenario: 音频阶段失败

- **WHEN** 成片生成成功，但音频导出失败且旧 MP3 仍存在
- **THEN** 报告保留成片，列音频错误及 partial 状态，不把旧 MP3 当作本次成功产物，退出码为 1


### Requirement: 产物复用与强制重跑

输出目录中中间产物（`xxx.ja.srt`、`xxx.zh.srt`、`xxx.bilingual.srt`）已存在时，对应阶段 SHALL 默认复用合法且满足新鲜度要求的产物（不询问）；产物无法解析或为空时 SHALL 视为损坏并重跑该阶段。日文、中文字幕有效时 SHALL 保留，双语字幕仅在其 index、时间轴和内容与当前日文/中文字幕的合成结果一致时 SHALL 复用，否则重新合成。启用的词汇阶段 SHALL 仅在当前选择的词汇产物合法且源字幕、学习者设置和数据版本等元数据一致时跳过；所选文件需补齐时 MAY 使用有效结构化缓存生成对应格式，无需重新调用释义 API，未选文件不作必需条件，详见 vocabulary 规格。`--force` SHALL 强制全部阶段重跑并覆盖当前运行所选的同名产物（不再询问），SHALL NOT 删除或改写未选中的词汇格式。已确认处理的视频 SHALL 重新从源视频导出 MP3，不因旧 MP3 存在而无条件复用。独立 `burn` 只读取现有字幕，不适用此流水线复用或重生成逻辑。

#### Scenario: 断点续跑

- **WHEN** 上次运行在翻译阶段失败，输出目录已有 `xxx.ja.srt`，用户修复后再次执行同一命令
- **THEN** 跳过转写，从翻译继续

#### Scenario: 强制重跑

- **WHEN** 用户执行 `ja-video-subtitles run xxx.mp4 -o out --force`
- **THEN** 忽略全部已有产物（含成片），完整重跑所有阶段

#### Scenario: 合法但过期的双语字幕

- **WHEN** `xxx.bilingual.srt` 可以解析但与当前日文/中文字幕的合成结果不同
- **THEN** 重新合成并烧录更新后的双语字幕，不仅因缓存可解析就跳过合成
