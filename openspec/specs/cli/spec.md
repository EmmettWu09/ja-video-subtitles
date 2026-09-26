# cli Specification

## Purpose
提供 macOS 日语视频处理命令，支持完整字幕与词汇流水线、独立字幕烧录、批量执行、启动校验、进度与结果报告。

## Requirements

### Requirement: 平台约束
工具仅支持 macOS（Apple Silicon），明确不支持 Windows / Linux。预检 SHALL 检查运行平台，非 macOS 时立即报错退出，不开始任何处理。

#### Scenario: 非 macOS 平台
- **WHEN** 在 Windows 或 Linux 上执行 `ja-video-subtitles run ...`
- **THEN** 预检失败，提示仅支持 macOS，退出码非零

### Requirement: 命令结构

CLI 命令为 `ja-video-subtitles`，SHALL 提供 `download`（下载 ASR 模型）、`run [<视频文件|文件夹>] [-o <输出目录>] [--vocab-output-dir <词汇目录>] [--vocab-format md|json|both] [--force | --no-force] [-y | --no-yes]`（执行日文转写、翻译、可配置词汇阶段、双语合成、烧录和 MP3 导出流水线）以及 `burn [<input> ...] [-o <输出目录>] [-s <字幕文件> | --subtitle-dir <字幕目录>] [-y | --no-yes]`（将现有 SRT 烧录进视频）。输入支持 mp4/mov 容器，成片统一输出 mp4。`run` 与 `burn` 的输入及 `-o/--output-dir` SHALL 允许从各自配置补齐；合并后输入和主输出目录 SHALL 必须存在有效值，无默认路径。显式 CLI 优先于配置，配置缺失时才使用既有内置默认值；完整映射及例外见 config 规格。后续规格中的 `-o`、`<out>` 和 `<output-dir>` 均 SHALL 指代本次合并后的有效主输出目录。字幕、成片、MP3、日志和报告 SHALL 写入该目录，词汇产物 SHALL 写入有效词汇目录，SHALL NOT 修改源视频。`run` 的 vocabulary 阶段 SHALL 在翻译后、双语合成前执行；启用时 SHALL 按 `md`、`json`、`both` 在有效词汇目录生成对应的 `<stem>.vocab.md` 和/或 `<stem>.vocab.json`，默认两种格式均输出到 `-o`。`run` SHALL 在烧录成功后导出 `<output-dir>/<stem>.mp3`。`burn` SHALL NOT 执行转写、翻译、词汇提取、双语合成或 MP3 导出。

#### Scenario: 单文件处理

- **WHEN** 执行 `ja-video-subtitles run /path/to/xxx.mp4 -o /path/to/out`、词汇目录与格式使用内置默认值且预检通过
- **THEN** 依次执行转写、翻译、启用的词汇阶段、双语合成、烧录和 MP3 导出，产物为输出目录内的 `xxx.ja.srt`、`xxx.zh.srt`、`xxx.bilingual.srt`、`xxx.sub.mp4`、`xxx.mp3`，词汇启用时增加 `xxx.vocab.md` 和 `xxx.vocab.json`，源目录无新增文件

#### Scenario: 文件夹批量

- **WHEN** 执行 `ja-video-subtitles run /path/to/dir -o /path/to/out`
- **THEN** 串行处理目录中的 mp4/mov，单个失败不阻塞其余视频，并打印 succeeded/partial/failed/skipped 汇总

#### Scenario: 单文件独立烧录

- **WHEN** 执行 `ja-video-subtitles burn xxx.mp4 -s edited.srt -o out`
- **THEN** 仅将现有 `edited.srt` 烧录到 `out/xxx.sub.mp4`，不生成或修改任何字幕文件

#### Scenario: 参数非法

- **WHEN** CLI 与配置合并后仍缺少输入或主输出目录，最终输入不存在/格式不支持，或者同时传入 `-s` 与 `--subtitle-dir`
- **THEN** 打印参数用法或具体检查错误，退出码为 2，不开始烧录

#### Scenario: 启用词汇功能

- **WHEN** 用户执行 `ja-video-subtitles run video.mp4 -o out` 且 vocabulary.enabled 为 true，词汇目录与格式使用内置默认值
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

#### Scenario: 只用配置启动完整流水线

- **WHEN** 合法配置给出 `run.input="video.mp4"` 和 `run.output_dir="media"`，词汇使用内置默认值，用户执行 `ja-video-subtitles run` 且预检通过
- **THEN** 对 video.mp4 执行完整流水线，字幕、成片、MP3、词汇、日志和报告均写入 media，行为等同显式传入这两个路径

#### Scenario: 只用配置启动独立烧录

- **WHEN** 合法配置给出 `burn.inputs=["video.mp4"]`、`burn.output_dir="out"`、`burn.subtitles="edited.srt"`，用户执行 `ja-video-subtitles burn` 且预检通过
- **THEN** 仅将 edited.srt 烧录为 out/video.sub.mp4，日志及报告写入 out，不执行其他流水线阶段

#### Scenario: CLI 只覆盖输出目录

- **WHEN** 合法配置给出 `run.input="video.mp4"`、`run.output_dir="saved"`、`vocabulary.output_dir=""`，用户执行 `run -o temporary`
- **THEN** 输入仍使用 video.mp4，主输出、默认词汇目录、覆盖检查、日志及报告均使用 temporary，不创建或写入 saved

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

`run` 与 `burn` 在预检通过后、开始处理前 SHALL 统一检查每个视频的 `<stem>.sub.mp4`；`run` SHALL 同时检查 `<stem>.mp3`。任一目标存在都 SHALL 纳入该视频的覆盖确认。自动覆盖 SHALL 使用合并后的有效值：`run` 为 `yes OR force`，`burn` 为 `yes`。已存在且未启用自动覆盖时 SHALL 逐个提示覆盖或跳过；配置或 CLI 开启的 force 均具有自动覆盖语义。全部确认 SHALL 在处理开始前完成，烧录过程 SHALL NOT 中断等待输入；未确认的视频 SHALL 整体跳过，保留该视频已有成片和 MP3。`burn` 不提供 `--force` 或 `--no-force`。显式 `--no-yes` SHALL 只关闭 yes，不能抵消仍为 true 的 force；`--no-force` SHALL 只关闭 force，不能抵消仍为 true 的 yes。任何自动覆盖选项 SHALL NOT 绕过输入、字幕或输出路径冲突校验。

#### Scenario: 同名文件选择覆盖

- **WHEN** 已有成片，用户输入 y 或有效自动覆盖值为 true
- **THEN** 正常处理并覆盖该成片

#### Scenario: 同名文件选择跳过

- **WHEN** 已有成片，用户输入 N
- **THEN** 标记跳过，保留既有成片，继续其他视频并在汇总中体现

#### Scenario: 非交互环境

- **WHEN** 存在同名成片且 stdin EOF，且有效自动覆盖值为 false
- **THEN** 不抛异常，跳过该视频并打印提示

#### Scenario: 烧录不中断

- **WHEN** 任一视频进入烧录阶段
- **THEN** 后续不再弹出本批次的覆盖提示

#### Scenario: 只有同名音频

- **WHEN** `run` 目标目录仅存在 `<stem>.mp3`，有效 yes 和 force 均为 false
- **THEN** 同样在处理前提示覆盖或跳过；拒绝或 EOF 时跳过该视频且保留旧 MP3

#### Scenario: 自动覆盖成片与音频

- **WHEN** `run` 的有效 yes 或 force 为 true，已有成片和/或 MP3
- **THEN** 不再询问，处理该视频并在对应阶段成功后覆盖目标

#### Scenario: 从配置开启烧录自动覆盖

- **WHEN** burn.yes=true 且未传 --no-yes，已有同名成片，全部校验通过
- **THEN** burn 不询问，直接处理并覆盖对应成片

#### Scenario: 关闭所有自动覆盖来源

- **WHEN** run.force=true、run.yes=true，用户传入 --no-force --no-yes，已有成片或 MP3
- **THEN** 使用正常产物复用策略，在处理前询问覆盖；拒绝或 EOF 时跳过并保留已有文件

#### Scenario: 只关闭 yes 不关闭强制重跑

- **WHEN** run.force=true，用户只传 --no-yes
- **THEN** force 仍生效，全部阶段重跑且无需覆盖询问

#### Scenario: 只关闭 force 保留自动覆盖

- **WHEN** run.force=true、run.yes=true，用户只传 --no-force
- **THEN** 允许复用合法中间产物，仍无需覆盖询问

### Requirement: 运行日志

`run` 与 `burn` SHALL 将终端输出同时追加到输出目录的 `run.log`，包含视频处理、错误与最终汇总。

#### Scenario: 日志落盘

- **WHEN** `run` 或 `burn` 全部处理完成或其中一个视频失败
- **THEN** `run.log` 包含各视频的烧录记录、错误及汇总

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

在最终有效 force 为 false 时，输出目录中中间产物（`xxx.ja.srt`、`xxx.zh.srt`、`xxx.bilingual.srt`）已存在时，对应阶段 SHALL 默认复用合法且满足新鲜度要求的产物（不询问）；产物无法解析或为空时 SHALL 视为损坏并重跑该阶段。日文、中文字幕有效时 SHALL 保留，双语字幕仅在其 index、时间轴和内容与当前日文/中文字幕的合成结果一致时 SHALL 复用，否则重新合成。启用的词汇阶段 SHALL 仅在当前选择的词汇产物合法且源字幕、学习者设置和数据版本等元数据一致时跳过；所选文件需补齐时 MAY 使用有效结构化缓存生成对应格式，无需重新调用释义 API，未选文件不作必需条件，详见 vocabulary 规格。最终有效 force 为 true 时（由 `--force` 或 `run.force=true` 提供）SHALL 强制全部阶段重跑并覆盖当前运行所选的同名产物（不再询问），SHALL NOT 删除或改写未选中的词汇格式。已确认处理的视频 SHALL 重新从源视频导出 MP3，不因旧 MP3 存在而无条件复用。独立 `burn` 只读取现有字幕，不适用此流水线复用或重生成逻辑。

#### Scenario: 断点续跑

- **WHEN** 上次运行在翻译阶段失败，输出目录已有 `xxx.ja.srt`，用户修复后再次执行同一命令且有效 force=false
- **THEN** 跳过转写，从翻译继续

#### Scenario: 强制重跑

- **WHEN** 用户执行 `ja-video-subtitles run xxx.mp4 -o out --force`
- **THEN** 忽略全部已有产物（含成片），完整重跑所有阶段

#### Scenario: 合法但过期的双语字幕

- **WHEN** `xxx.bilingual.srt` 可以解析但与当前日文/中文字幕的合成结果不同
- **THEN** 重新合成并烧录更新后的双语字幕，不仅因缓存可解析就跳过合成

#### Scenario: 配置强制重跑与 CLI 等效

- **WHEN** run.force=true，用户未提供 force 正反开关，全部预检通过
- **THEN** 忽略中间缓存，重跑全部阶段并覆盖本次所选产物，保留未选词汇格式

#### Scenario: 临时关闭配置中的强制重跑

- **WHEN** run.force=true，用户提供 --no-force，输出目录已有合法且新鲜的中间产物，并已确认处理视频
- **THEN** 复用适用中间产物，按既有规则处理成片和 MP3

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

### Requirement: 词汇阶段非阻塞

词汇阶段是学习辅助阶段。阶段级异常 SHALL 被记录，但不得阻止当前视频继续执行双语合成和烧录。此时视频状态 SHALL 为 `partial`，报告 SHALL 包含错误原因；批量任务 SHALL 继续处理其他视频。

#### Scenario: 形态分析阶段异常

- **WHEN** 日文和中文字幕已生成，但 vocabulary 阶段抛出异常
- **THEN** 系统记录词汇失败，仍生成 bilingual.srt 和 sub.mp4，并把该视频标为 partial

### Requirement: 参数合并先于路径访问和处理副作用

`run` 与 `burn` SHALL 在访问输入路径、展开视频、创建输出目录或开始运行预检前完成参数来源解析、当前作用域配置字段校验以及最终必需项和字幕来源互斥校验。显式单字幕只允许一个视频的数量约束 SHALL 在输入展开并去重后、运行预检或处理副作用前校验。参数或配置错误 SHALL 返回退出码 2 并指出选项或配置字段；不得触发模型下载、翻译 API 请求、目录创建或媒体写入。显式 CLI 值非法或最终路径不可用时 SHALL 报错，SHALL NOT 静默改用配置中的其他路径。配置有效但被 CLI 覆盖的路径 SHALL 不被创建或检查可用性。

#### Scenario: 缺少有效路径不触发副作用

- **WHEN** run 或 burn 合并后缺少输入或主输出目录
- **THEN** 返回退出码 2 并提示对应 CLI 参数和配置键，不创建目录、不访问 API、不启动视频处理

#### Scenario: 显式空路径不是未提供

- **WHEN** 配置含合法输出目录，用户传入 `-o ""` 或只含空白的输出路径
- **THEN** 报告非法显式路径并返回退出码 2，不使用配置输出目录继续处理

#### Scenario: 显式路径不存在不能回退

- **WHEN** 配置输入存在，用户显式传入不存在的输入路径
- **THEN** 报告该 CLI 输入不存在并返回退出码 2，不处理配置中的输入

### Requirement: 参数帮助与配置示例

CLI 帮助、`config.example.toml` 和三个语言版本的 README SHALL 列出业务参数与配置键映射，说明 CLI、配置、默认值的顺序、合并后必需项、相对路径基准、字幕来源按组覆盖及布尔否定开关。示例配置的输入、输出及字幕路径 SHALL 使用注释示例，force 和 yes SHALL 默认为 false。文档 SHALL 说明配置开启 force/yes 与对应 CLI 开关具有相同重跑及覆盖行为。帮助和版本请求 SHALL 不读取配置，也不依赖有效输入、输出、API 密钥或模型。

#### Scenario: 无配置查看帮助和版本

- **WHEN** config.toml 缺失或损坏，用户执行 `--help`、`run --help`、`burn --help`、`download --help` 或 `--version`
- **THEN** 正常显示所请求信息并以退出码 0 结束，不执行配置或媒体预检

#### Scenario: 用户查阅纯配置使用示例

- **WHEN** 用户查看模板和 README
- **THEN** 能找到配置输入与输出后直接执行 run/burn、只用 CLI 覆盖单项、关闭配置开关以及切换字幕来源的示例
