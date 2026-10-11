# Spec: cli

## MODIFIED Requirements

### Requirement: 命令结构

CLI 命令为 `ja-video-subtitles`，SHALL 提供 `download`（下载 ASR 模型）、`run [<视频文件|文件夹>] [-o <输出目录>] [--vocab-output-dir <词汇目录>] [--vocab-format md|json|both] [--force | --no-force] [-y | --no-yes] [--highlights | --no-highlights]`（执行日文转写、翻译、可配置词汇阶段、双语合成、烧录、MP3 导出和可配置高光阶段流水线）以及 `burn [<input> ...] [-o <输出目录>] [-s <字幕文件> | --subtitle-dir <字幕目录>] [-y | --no-yes]`（将现有 SRT 烧录进视频）。输入支持 mp4/mov 容器，成片统一输出 mp4。`run` 与 `burn` 的输入及 `-o/--output-dir` SHALL 允许从各自配置补齐；合并后输入和主输出目录 SHALL 必须存在有效值，无默认路径。显式 CLI 优先于配置，配置缺失时才使用既有内置默认值；完整映射及例外见 config 规格。后续规格中的 `-o`、`<out>` 和 `<output-dir>` 均 SHALL 指代本次合并后的有效主输出目录。`run` 的按视频产物 SHALL 写入按视频产物目录 `<out>/<stem>/`（一个视频一个文件夹，文件夹名为原始视频主干名）：字幕 `<stem>.ja.srt`、`.ja.json`、`.zh.srt`、`.bilingual.srt`，烧录成片 `<stem>.mp4`（使用原始文件名），MP3 `<stem>.mp3`，精华视频 `<stem>.highlights.mp4`；日志 `run.log` 与报告 `report-<时间戳>.md` SHALL 写入主输出目录根，SHALL NOT 移入视频文件夹。词汇产物 SHALL 写入有效词汇目录，SHALL NOT 修改源视频。`run` 的 vocabulary 阶段 SHALL 在翻译后、双语合成前执行；启用时 SHALL 按 `md`、`json`、`both` 在有效词汇目录生成对应的 `<stem>.vocab.md` 和/或 `<stem>.vocab.json`，默认两种格式均输出到 `-o`。`run` SHALL 在烧录成功后导出 `<out>/<stem>/<stem>.mp3`。`run` 在最终有效高光开关为 true 时 SHALL 在烧录成功后执行高光阶段，精华视频 SHALL 输出为 `<out>/<stem>/<stem>.highlights.mp4`（与烧录成片并排，SHALL NOT 放在 highlights 子目录内），其余高光产物 SHALL 写入 `<out>/<stem>/highlights/`，布局与内容见 highlights 规格；最终有效高光开关默认为 false（未配置 `highlights.enabled` 且未传 CLI 开关），此时 SHALL NOT 创建 highlights 目录、生成 `<stem>.highlights.mp4` 或执行高光阶段。`--highlights` 与 `--no-highlights` SHALL 构成正反互斥开关，同时出现 SHALL 报错。`burn` SHALL NOT 执行转写、翻译、词汇提取、双语合成、MP3 导出或高光阶段，SHALL NOT 接受高光参数；`burn` 的产物布局保持 `<out>/<stem>.sub.mp4` 不变。重跑时 SHALL 直接覆盖已存在的同名产物（经既有覆盖确认或自动覆盖机制），SHALL NOT 为避免重名而改用派生文件名；旧版平铺布局的遗留产物 SHALL NOT 参与复用，也 SHALL NOT 被自动删除或迁移。

#### Scenario: 单文件处理

- **WHEN** 执行 `ja-video-subtitles run /path/to/xxx.mp4 -o /path/to/out`、词汇目录与格式使用内置默认值、未配置也未传入高光开关且预检通过
- **THEN** 依次执行转写、翻译、启用的词汇阶段、双语合成、烧录和 MP3 导出，产物为 `out/xxx/` 内的 `xxx.ja.srt`、`xxx.zh.srt`、`xxx.bilingual.srt`、`xxx.mp4`、`xxx.mp3`，词汇启用时在有效词汇目录增加 `xxx.vocab.md` 和 `xxx.vocab.json`，`run.log` 与报告位于 `out` 根；不执行高光阶段、不创建 `out/xxx/highlights/`、不生成 `xxx.highlights.mp4`，源目录无新增文件

#### Scenario: 文件夹批量

- **WHEN** 执行 `ja-video-subtitles run /path/to/dir -o /path/to/out`
- **THEN** 串行处理目录中的 mp4/mov，每个视频的产物分别写入 `out/<stem>/`，单个失败不阻塞其余视频，并打印 succeeded/partial/failed/skipped 汇总

#### Scenario: 单文件独立烧录

- **WHEN** 执行 `ja-video-subtitles burn xxx.mp4 -s edited.srt -o out`
- **THEN** 仅将现有 `edited.srt` 烧录到 `out/xxx.sub.mp4`，不生成或修改任何字幕文件，不创建按视频文件夹

#### Scenario: 参数非法

- **WHEN** CLI 与配置合并后仍缺少输入或主输出目录，最终输入不存在/格式不支持，同时传入 `-s` 与 `--subtitle-dir`，或同时传入 `--highlights` 与 `--no-highlights`
- **THEN** 打印参数用法或具体检查错误，退出码为 2，不开始处理

#### Scenario: 启用词汇功能

- **WHEN** 用户执行 `ja-video-subtitles run video.mp4 -o out` 且 vocabulary.enabled 为 true，词汇目录与格式使用内置默认值
- **THEN** 翻译后提取词汇，主输出目录包含词汇 Markdown、结构化 JSON，视频文件夹包含字幕、成片和 MP3

#### Scenario: 自定义词汇目录和单格式

- **WHEN** 执行 `run video.mp4 -o media --vocab-output-dir words --vocab-format json` 且词汇已启用
- **THEN** 词汇仅写入 `words/video.vocab.json`，不新建 Markdown，字幕、MP3、成片、日志与报告仍写入 `media`（按视频产物在 `media/video/`）

#### Scenario: 词汇格式参数非法

- **WHEN** `--vocab-format` 不为 `md`、`json`、`both`
- **THEN** 参数解析失败并给出合法值，退出码为 2，不开始处理

#### Scenario: 词汇禁用

- **WHEN** vocabulary.enabled 为 false，但命令包含合法词汇目录和格式参数
- **THEN** 不创建词汇目录、不生成词汇文件，正常生成字幕、成片和 MP3

#### Scenario: 默认不输出高光产物

- **WHEN** 执行 `run video.mp4 -o out`，未提供高光开关且配置未设置 highlights.enabled
- **THEN** 不执行高光阶段、不创建 `out/video/highlights/`、不生成 `video.highlights.mp4`，其余产物正常写入 `out/video/`

#### Scenario: 命令行开启默认关闭的高光

- **WHEN** 配置未设置 highlights.enabled，用户执行 `run video.mp4 -o out --highlights`
- **THEN** 烧录成功后执行高光阶段，精华视频输出为 `out/video/video.highlights.mp4`，其余高光产物写入 `out/video/highlights/`

#### Scenario: 命令行关闭配置开启的高光

- **WHEN** 配置 highlights.enabled=true，用户执行 `run video.mp4 -o out --no-highlights`
- **THEN** 不执行高光阶段、不创建 highlights 目录，其余产物正常写入 `out/video/`

#### Scenario: 命令行开启配置关闭的高光

- **WHEN** 配置 highlights.enabled=false，用户执行 `run video.mp4 -o out --highlights`
- **THEN** 执行高光阶段，显式 CLI 值优先于配置

#### Scenario: 重跑覆盖同名产物

- **WHEN** `out/video/` 中已存在上次运行的 `video.mp4`、`video.highlights.mp4` 等产物，覆盖已获准（确认、`-y` 或 `--force`）
- **THEN** 新产物直接覆盖同名旧文件，不生成派生文件名

#### Scenario: 旧平铺布局产物不复用

- **WHEN** 主输出目录根存在旧版布局的 `video.ja.srt`、`video.sub.mp4` 等平铺产物
- **THEN** 各阶段按新布局重新生成到 `out/video/`，旧文件保留原处不被删除或移动

#### Scenario: 独立烧录拒绝高光参数

- **WHEN** 用户向 `burn` 传入 `--highlights` 或 `--no-highlights`
- **THEN** 参数解析失败，退出码为 2，不开始烧录

#### Scenario: 完整流水线输出冲突

- **WHEN** 不同输入视频主干名经规范化后相同，或计划输出路径（含按视频产物目录与高光产物路径）之间冲突、可能覆盖源视频
- **THEN** 在处理前拒绝整批请求并给出冲突路径，退出码为 2

#### Scenario: 只用配置启动完整流水线

- **WHEN** 合法配置给出 `run.input="video.mp4"` 和 `run.output_dir="media"`，词汇与高光使用内置默认值，用户执行 `ja-video-subtitles run` 且预检通过
- **THEN** 对 video.mp4 执行除高光外的完整流水线，按视频产物写入 `media/video/`，词汇写入有效词汇目录，日志和报告写入 `media` 根，行为等同显式传入这两个路径

#### Scenario: 只用配置启动独立烧录

- **WHEN** 合法配置给出 `burn.inputs=["video.mp4"]`、`burn.output_dir="out"`、`burn.subtitles="edited.srt"`，用户执行 `ja-video-subtitles burn` 且预检通过
- **THEN** 仅将 edited.srt 烧录为 out/video.sub.mp4，日志及报告写入 out，不执行其他流水线阶段

#### Scenario: CLI 只覆盖输出目录

- **WHEN** 合法配置给出 `run.input="video.mp4"`、`run.output_dir="saved"`、`vocabulary.output_dir=""`，用户执行 `run -o temporary`
- **THEN** 输入仍使用 video.mp4，主输出、默认词汇目录、覆盖检查、日志及报告均使用 temporary，不创建或写入 saved

### Requirement: 参数帮助与配置示例

CLI 帮助、`config.example.toml` 和三个语言版本的 README SHALL 列出业务参数与配置键映射（含 `--highlights`/`--no-highlights` 与 `[highlights]` 配置键），说明 CLI、配置、默认值的顺序、合并后必需项、相对路径基准、字幕来源按组覆盖及布尔否定开关，并明确高光默认关闭及其开启方式（`--highlights` 或 `highlights.enabled=true`）。示例配置的输入、输出及字幕路径 SHALL 使用注释示例，force 和 yes SHALL 默认为 false。文档 SHALL 说明配置开启 force/yes 与对应 CLI 开关具有相同重跑及覆盖行为。帮助和版本请求 SHALL 不读取配置，也不依赖有效输入、输出、API 密钥或模型。

#### Scenario: 无配置查看帮助和版本

- **WHEN** config.toml 缺失或损坏，用户执行 `--help`、`run --help`、`burn --help`、`download --help` 或 `--version`
- **THEN** 正常显示所请求信息并以退出码 0 结束，不执行配置或媒体预检

#### Scenario: 用户查阅纯配置使用示例

- **WHEN** 用户查看模板和 README
- **THEN** 能找到配置输入与输出后直接执行 run/burn、只用 CLI 覆盖单项、开启或关闭配置开关（含开启高光）以及切换字幕来源的示例
