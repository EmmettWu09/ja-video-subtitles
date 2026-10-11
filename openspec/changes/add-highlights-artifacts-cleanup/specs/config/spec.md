# Spec: config

## MODIFIED Requirements

### Requirement: 配置文件

配置文件 SHALL 从项目根目录（包所在位置）的 `config.toml` 读取，与命令执行时的当前目录无关。配置项包含 DeepSeek `base_url`（默认 `https://api.deepseek.com`）、`api_key`（无默认值）、`model`（默认 `deepseek-flash`），有内置默认值的翻译 prompt 模板、烧录字幕样式及 `[video] bitrate`（默认 `8M`）。`run` SHALL 要求配置文件存在且 api_key 有效。`burn` SHALL 允许配置文件不存在或缺少/留空 api_key：不存在时使用默认烧录样式和码率，存在时应用烧录相关覆盖项，SHALL NOT 验证或使用翻译 API 配置。无法解析的 TOML 或非法烧录配置 SHALL 在处理前报错。`run` 新增 `[vocabulary]` 配置：`enabled` 默认 true、`learner_level` 默认 `N3`、`include_unknown` 默认 true、`max_examples` 默认 3、`output_dir` 默认空字符串、`format` 默认 `both`。`enabled` 和 `include_unknown` SHALL 仅接受布尔值，`learner_level` SHALL 仅接受 N5/N4/N3/N2/N1，`max_examples` SHALL 仅接受 1 到 10 的整数（布尔值不视为整数）。`output_dir` SHALL 为字符串，空字符串回退到 `-o`；非空路径 SHALL 相对命令执行时的 cwd 解析。`format` SHALL 仅接受 `md`、`json`、`both`。`run --vocab-output-dir` 和 `--vocab-format` 的显式值 SHALL 分别优先于合法配置中的对应值；配置本身 SHALL 先通过类型和枚举校验。`run` 新增 `[highlights]` 配置：`enabled` 默认 false、`target_seconds` 默认 240、`intro_start_seconds` 默认 0、`ja_voice` 默认 `Kyoko`、`zh_voice` 默认 `Tingting`、`keep_artifacts` 默认 false。`highlights.enabled` 控制是否输出高光产物，SHALL 仅接受布尔值；`target_seconds` SHALL 仅接受 60 到 900 的整数（布尔值不视为整数）；`intro_start_seconds` SHALL 仅接受不小于 0 的数值（布尔值不视为数值）；`ja_voice` 与 `zh_voice` SHALL 为非空、非纯空白且不含 NUL（U+0000）的字符串。`highlights.keep_artifacts` 控制高光全部成功后是否保留 `<out>/<stem>/highlights/` 产物目录，SHALL 仅接受布尔值，SHALL NOT 提供对应 CLI 参数（config-only）。`run --highlights`/`--no-highlights` 的显式值 SHALL 优先于合法配置中的 `highlights.enabled`；配置本身 SHALL 先通过类型和取值校验。`burn` SHALL 忽略词汇与高光配置，不验证其值或要求相关依赖。

#### Scenario: 正常加载

- **WHEN** config.toml 存在且字段合法
- **THEN** 使用配置值，未配置字段回退到内置默认值

#### Scenario: 配置缺失

- **WHEN** 执行 `run`，config.toml 不存在或 api_key 为空/仍为占位符
- **THEN** 预检失败，提示参照 config.example.toml 创建配置，退出码非零

#### Scenario: 独立烧录无配置

- **WHEN** 执行 `burn` 且 config.toml 不存在
- **THEN** 使用默认字幕样式和 `8M` 码率，无需创建配置文件

#### Scenario: 独立烧录只配置样式和码率

- **WHEN** 执行 `burn`，配置只有字幕样式与 `[video] bitrate`，没有有效 DeepSeek key
- **THEN** 应用样式和码率覆盖，不检查 API key 或 API 连通性

#### Scenario: 独立烧录配置损坏

- **WHEN** `burn` 读取的 config.toml 无法解析或包含非法烧录配置
- **THEN** 打印配置错误，以退出码 2 结束，不开始任何视频烧录

#### Scenario: 未配置 vocabulary

- **WHEN** config.toml 没有 `[vocabulary]`
- **THEN** 使用 enabled=true、learner_level=N3、include_unknown=true、max_examples=3、output_dir=""、format=both

#### Scenario: 未配置 highlights

- **WHEN** config.toml 没有 `[highlights]`
- **THEN** 使用 enabled=false、target_seconds=240、intro_start_seconds=0、ja_voice=Kyoko、zh_voice=Tingting、keep_artifacts=false，即默认不输出高光产物

#### Scenario: 非法学习者等级

- **WHEN** `run` 的 learner_level 不是 N5/N4/N3/N2/N1，或 max_examples 超出范围
- **THEN** 预检失败并给出合法取值，不开始处理视频

#### Scenario: 非法词汇配置类型

- **WHEN** `run` 的 vocabulary.enabled 或 include_unknown 不是布尔值，或 max_examples 不是整数（包括误用布尔值）
- **THEN** 预检失败并给出字段与合法类型，不开始处理视频

#### Scenario: 非法高光配置

- **WHEN** `run` 的 highlights.enabled 或 keep_artifacts 不是布尔值、target_seconds 超出 60–900 或非整数、intro_start_seconds 为负数，或 ja_voice/zh_voice 为空或纯空白字符串
- **THEN** 预检失败并给出字段与合法类型/取值，不开始处理视频

#### Scenario: 禁用词汇功能

- **WHEN** vocabulary.enabled 为 false
- **THEN** 不运行词汇阶段，也不要求形态分析词典和 JLPT 数据就绪

#### Scenario: 禁用高光功能

- **WHEN** highlights.enabled 为 false（含未配置时的默认值）且无 CLI 覆盖
- **THEN** 不运行高光阶段，也不要求 `say` 命令与音色可用

#### Scenario: 独立烧录忽略词汇设置

- **WHEN** `burn` 使用的 TOML 可以解析，但 vocabulary 部分缺失或包含非法词汇配置
- **THEN** 仅验证并应用烧录配置，不因词汇设置或词典缺失而阻止烧录

#### Scenario: 独立烧录忽略高光设置

- **WHEN** `burn` 使用的 TOML 可以解析，但 highlights 部分缺失或包含非法高光配置
- **THEN** 仅验证并应用烧录配置，不因高光设置而阻止烧录

#### Scenario: 命令行覆盖词汇输出配置

- **WHEN** 配置为 output_dir="saved-words"、format="json"，命令指定 `--vocab-output-dir notes --vocab-format md`
- **THEN** 词汇只生成到 cwd 下 `notes` 的 Markdown，配置值不覆盖显式参数

#### Scenario: 命令行覆盖高光开关

- **WHEN** 配置为 highlights.enabled=false，命令指定 `--highlights`
- **THEN** 本次运行执行高光阶段，配置值不覆盖显式参数

#### Scenario: 配置中的相对目录

- **WHEN** 用户从项目以外的目录执行命令，配置 output_dir="words" 且没有对应 CLI 覆盖
- **THEN** 词汇目录为命令执行时 cwd 下的 `words`，不是 config.toml 所在目录下的 `words`

#### Scenario: 非法输出配置

- **WHEN** `run` 的 vocabulary.output_dir 不是字符串，或 vocabulary.format 不是 md/json/both
- **THEN** 在处理前给出字段及合法类型/取值错误，退出码为 2

### Requirement: 命令作用域内配置的严格校验

当前命令对应的 `[run]` 或 `[burn]` 配置节如存在 SHALL 为 TOML 表。`run` 读取的 `[highlights]` 配置节如存在 SHALL 为 TOML 表。当前命令读取的已配置字段 SHALL 在应用命令行覆盖前通过类型和取值校验：`run.input`、`run.output_dir`、`burn.output_dir` SHALL 为非空、非纯空白且不含 NUL（U+0000）的路径字符串；`burn.inputs` SHALL 为至少包含一个元素的字符串数组，每个元素 SHALL 为非空、非纯空白且不含 NUL（U+0000）的路径字符串；`run.force`、`run.yes`、`burn.yes`、`highlights.enabled`、`highlights.keep_artifacts` SHALL 为布尔值，不接受字符串或数字替代。`burn.subtitles`、`burn.subtitle_dir` 和 `vocabulary.output_dir` SHALL 为不含 NUL（U+0000）的字符串，仅精确空字符串允许作为缺省值，非空但纯空白的字符串 SHALL 报错。`vocabulary.format` SHALL 继续仅接受 `md`、`json` 或 `both`。`highlights.target_seconds` SHALL 为 60 到 900 的整数（布尔值不视为整数）；`highlights.intro_start_seconds` SHALL 为不小于 0 的数值（布尔值不视为数值）；`highlights.ja_voice` 与 `highlights.zh_voice` SHALL 为非空、非纯空白且不含 NUL（U+0000）的字符串。配置缺少字段 SHALL 允许后续命令行补齐或使用默认值；已配置非法值 SHALL 不被合法命令行值掩盖。校验失败 SHALL 指出配置字段和允许的类型或取值，以退出码 2 结束。

所有显式 CLI 路径（含位置输入、主输出、词汇目录及字幕文件/目录）SHALL 拒绝空字符串、纯空白和 NUL（U+0000），不得将这些非法值当作未提供。合法路径中的空格和其他字符 SHALL 原样保留，不得自动裁剪。

字段校验 SHALL 不检查路径是否存在或可写，不展开目录输入，也不判断字幕来源组互斥；这些检查 SHALL 仅针对合并后的最终有效值执行。最终有效值仍 SHALL 通过现有视频输入、字幕合法性、输出可写性及输入输出别名冲突检查。

#### Scenario: 配置表类型错误不能被命令行覆盖

- **WHEN** 当前执行 `run`，配置为 `run="invalid"`，命令行已提供合法输入和主输出目录
- **THEN** 系统以退出码 2 提示 `run` 必须为 TOML 表，不开始处理视频

#### Scenario: 高光配置表类型错误

- **WHEN** 当前执行 `run`，配置为 `highlights="invalid"`
- **THEN** 系统以退出码 2 提示 `highlights` 必须为 TOML 表，不开始处理视频

#### Scenario: 布尔配置严格区分字符串与布尔值

- **WHEN** 当前命令对应的 `force`、`yes` 或 `highlights.enabled` 配置为字符串 `"true"`、整数 `1` 或整数 `0`，即使命令行提供了对应正反开关
- **THEN** 系统报告该配置字段必须为布尔值，以退出码 2 结束

#### Scenario: 非法高光配置不能被命令行掩盖

- **WHEN** `highlights.target_seconds="240"` 或 `highlights.ja_voice=""`，用户执行 `run video.mp4 -o out --highlights`
- **THEN** 系统报告对应配置字段的合法类型或取值，以退出码 2 结束

#### Scenario: 烧录列表类型与元素严格校验

- **WHEN** `burn.inputs` 为单个字符串、空数组、包含非字符串的数组或包含空字符串的数组，即使命令行提供了合法烧录输入
- **THEN** 系统报告 `burn.inputs` 必须为包含至少一个非空路径字符串的数组，以退出码 2 结束

#### Scenario: 主路径不能配置为空

- **WHEN** 当前命令所需的输入或主输出目录被配置为空字符串或纯空白字符串，且命令行提供了该字段的合法路径
- **THEN** 系统仍报告对应配置路径必须非空，以退出码 2 结束

#### Scenario: 非法词汇格式不能被命令行掩盖

- **WHEN** `vocabulary.format="csv"`，用户执行 `run video.mp4 -o out --vocab-format md`
- **THEN** 系统报告 `vocabulary.format` 的合法取值为 `md/json/both`，以退出码 2 结束

#### Scenario: 只检查最终有效路径的存在性与可写性

- **WHEN** 当前命令的配置路径字符串类型合法，但指向不存在的输入、字幕或不可写的输出位置，且这些路径均被合法命令行路径替换
- **THEN** 系统只对命令行所选最终有效路径进行文件系统检查，不因被替换的配置路径不可用而失败，也不创建被替换的输出目录
