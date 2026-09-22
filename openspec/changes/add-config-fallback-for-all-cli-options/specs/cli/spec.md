## MODIFIED Requirements

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

## ADDED Requirements

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
