# burning Specification

## Purpose
将现有或合成的 SRT 字幕硬烧进视频，提供日中双语合成、字幕来源匹配、输出安全检查及硬件编码进度。

## Requirements

### Requirement: 双语字幕合成

SHALL 按 index 对齐 `xxx.ja.srt` 与 `xxx.zh.srt`，在 `-o` 输出目录生成 `xxx.bilingual.srt`：每条字幕两行，上行日文原文、下行中文译文，时间轴沿用转写结果。中文缺失的条目 SHALL 仅保留日文行，不阻塞合成。`run` 仅在已有双语字幕可解析、非空，且每条字幕的 index、时间轴和内容与当前日文/中文字幕的合成结果一致时 SHALL 复用该文件；源字幕改变或缓存不一致时 SHALL 重新合成后再烧录。独立 `burn` SHALL 继续直接读取所选 SRT，不执行合成或修改字幕。

#### Scenario: 正常合成

- **WHEN** ja/zh 两个字幕文件条数一致
- **THEN** 输出目录生成条数相同的 `xxx.bilingual.srt`，每条两行

#### Scenario: 修改中文译文后重跑

- **WHEN** 用户编辑现有 `xxx.zh.srt` 后再次执行 `run` 并确认覆盖成片，旧 `xxx.bilingual.srt` 仍可解析但包含修改前译文
- **THEN** 保留用户编辑的中文字幕，刷新词汇语境（若启用），重新生成双语字幕，再把当前译文烧录进成片

#### Scenario: 修改日文或时间轴后重跑

- **WHEN** 当前日文字幕内容、index 或时间轴已改变，既有双语字幕与当前合成结果不一致
- **THEN** `run` 不复用旧双语字幕，按当前日文时间轴和匹配的中文重新合成

### Requirement: 烧录输出

SHALL 使用带 libass 的 ffmpeg（`subtitles` 滤镜 + `force_style`）将选定 SRT 硬烧进视频，在 `-o` 输出目录生成 `<stem>.sub.mp4`；视频用 `h264_videotoolbox` 硬件编码，音频直通（`-c:a copy`）。`run` 使用合成的 `<stem>.bilingual.srt`；`burn` 使用已有 SRT，SHALL NOT 执行字幕合成或修改字幕。字幕样式 SHALL 有默认值（PingFang SC、白字黑描边、底部居中）并允许 config 覆盖。烧录过程 SHALL 显示进度条。

#### Scenario: 烧录成功

- **WHEN** `run` 已生成双语字幕且成片确认通过
- **THEN** 输出可正常播放、画面含双语硬字幕的 `<stem>.sub.mp4`，进度条走满

#### Scenario: 现有字幕烧录成功

- **WHEN** `burn` 已校验用户提供的 SRT 且成片确认通过
- **THEN** 输出包含该 SRT 硬字幕的 `<stem>.sub.mp4`，原 SRT 保持不变

#### Scenario: ffmpeg 不支持烧录

- **WHEN** 找不到带 subtitles 滤镜的 ffmpeg
- **THEN** 预检失败并提示安装方式，不开始处理任何视频

### Requirement: 同名与安全

成片同名检查与确认 SHALL 在烧录前完成，烧录中 SHALL NOT 等待输入；未获确认的既有成片 SHALL NOT 覆盖。烧录 SHALL NOT 修改源视频或输入字幕。`burn` SHALL 在处理前检查全部成片、日志和报告目标，拒绝任一目标与任一源视频或输入字幕路径相同、指向同一已有文件或与其他输出目标冲突的情况，包括符号链接和硬链接；`-y` SHALL NOT 绕过此检查。

#### Scenario: 未确认不覆盖

- **WHEN** 用户选择跳过已有成片
- **THEN** 既有成片保持原样，不做任何写操作

#### Scenario: 成片目标是另一输入视频

- **WHEN** 输入含 `clip.mp4` 和 `clip.sub.mp4`，输出目录使前者成片目标等于后者源路径
- **THEN** `burn` 在处理前以退出码 2 拒绝整批请求，所有源视频保持不变

#### Scenario: 成片通过链接指向源视频

- **WHEN** 某个成片目标是指向任一源视频的符号链接或硬链接，即使传入 `-y`
- **THEN** `burn` 在处理前以退出码 2 结束，不修改任何源视频

#### Scenario: 日志或报告通过链接指向输入

- **WHEN** `run.log` 或本次报告路径是指向源视频或输入字幕的符号链接或硬链接
- **THEN** 在写日志、报告或烧录视频前以退出码 2 结束，输入文件保持不变

### Requirement: 烧录路径特殊字符

烧录 SHALL 支持视频、SRT 和输出路径中的空格、中日韩字符、单引号、方括号、冒号和反斜杠。在用户按 shell 规则正确引用参数后，SHALL 保留实际文件名含义。嵌入 ffmpeg `subtitles` 滤镜的字幕路径 SHALL 正确进行滤镜选项值及滤镜图两层转义，避免合法路径被误解为滤镜语法。该行为 SHALL 同时适用于 `run` 和 `burn`。

#### Scenario: 特殊字符字幕路径

- **WHEN** 有效 SRT 的路径含空格、中日韩字符、单引号、方括号、冒号或反斜杠，用户正确传入该路径
- **THEN** ffmpeg 读取指定字幕并成功生成硬字幕成片，不因滤镜解析错误而失败

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

### Requirement: 独立烧录整批字幕校验

`burn` SHALL 在任何视频烧录前验证全部映射字幕存在、为可读 UTF-8（可含 BOM）、可解析且非空的 SRT。任一字幕失败 SHALL 打印对应视频与字幕路径，以退出码 2 结束整批请求，不得开始前面的有效任务，也不得生成或修复字幕。

#### Scenario: 后续视频字幕缺失

- **WHEN** 第一个视频字幕有效，但第二个视频缺少字幕
- **THEN** 退出码为 2，两个视频均不烧录，提示缺失的字幕路径

#### Scenario: 字幕损坏

- **WHEN** 任一字幕为空、不可读、非 UTF-8 或 SRT 解析失败
- **THEN** 在全部烧录开始前失败，指出字幕错误，源视频与字幕保持不变
