## MODIFIED Requirements

### Requirement: 独立烧录字幕映射

`burn` SHALL 先按 config 规格选择有效字幕来源：显式 CLI 来源整体优先于配置来源，均未设置时将每个视频映射到 `<out>/<stem>.bilingual.srt`，其中 out 为最终有效主输出目录。有效字幕目录来自 `--subtitle-dir <dir>` 或 `burn.subtitle_dir` 时 SHALL 读取 `<dir>/<stem>.bilingual.srt`；有效字幕文件来自 `-s/--subtitles <path>` 或 `burn.subtitles` 时 SHALL 允许任意命名的现有 SRT，但仅限最终输入展开并去重后恰有一个视频。CLI 自身的两个来源 SHALL 互斥，未被 CLI 覆盖的配置来源组内两个非空来源 SHALL 互斥。字幕不要求双语内容，全部选定字幕 SHALL 保持处理前整批校验。

#### Scenario: 默认映射

- **WHEN** 执行 `burn first.mp4 second.mov -o out` 且配置也未设置字幕来源
- **THEN** 分别读取 `out/first.bilingual.srt` 和 `out/second.bilingual.srt`

#### Scenario: 独立字幕目录

- **WHEN** 执行 `burn videos/ --subtitle-dir subtitles -o out`
- **THEN** 从 `subtitles` 目录按视频主干名读取双语字幕，成片写入 `out`

#### Scenario: 显式单字幕

- **WHEN** 执行 `burn clip.mp4 -s corrected.srt -o out`
- **THEN** 使用 `corrected.srt`，不要求存在 `out/clip.bilingual.srt`

#### Scenario: 多视频误用单字幕

- **WHEN** 通过 CLI 或配置选定显式字幕文件，且展开去重后仍有多个视频
- **THEN** 退出码为 2，提示使用默认匹配或 `--subtitle-dir`，不烧录任何视频

#### Scenario: 配置字幕目录用于配置批次

- **WHEN** burn.inputs=["first.mp4", "second.mov"]、burn.output_dir="out"、burn.subtitle_dir="subs"，用户执行 burn
- **THEN** 分别读取 subs/first.bilingual.srt 和 subs/second.bilingual.srt，成片写入 out；任一字幕无效时整批拒绝

#### Scenario: CLI 文件切换配置目录来源

- **WHEN** burn.subtitle_dir="saved-subs"，用户执行 `burn clip.mp4 -s corrected.srt -o out`
- **THEN** 仅使用 corrected.srt，忽略配置目录，不要求配置目录存在

#### Scenario: CLI 目录切换配置文件来源

- **WHEN** burn.subtitles="saved.srt"，用户执行 `burn first.mp4 second.mov --subtitle-dir subs -o out`
- **THEN** 从 subs 按主干名映射两个字幕，忽略配置中的单字幕文件

#### Scenario: 默认字幕匹配跟随最终输出目录

- **WHEN** burn.output_dir="saved-out"，CLI 与配置均未选择字幕来源，用户执行 `burn clip.mp4 -o cli-out`
- **THEN** 读取 cli-out/clip.bilingual.srt，成片、日志和报告也写入 cli-out
