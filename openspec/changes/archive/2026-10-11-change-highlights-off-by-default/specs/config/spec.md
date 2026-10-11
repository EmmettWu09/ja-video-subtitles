# Spec: config

## MODIFIED Requirements

### Requirement: 配置文件

配置文件 SHALL 从项目根目录（包所在位置）的 `config.toml` 读取，与命令执行时的当前目录无关。配置项包含 DeepSeek `base_url`（默认 `https://api.deepseek.com`）、`api_key`（无默认值）、`model`（默认 `deepseek-flash`），有内置默认值的翻译 prompt 模板、烧录字幕样式及 `[video] bitrate`（默认 `8M`）。`run` SHALL 要求配置文件存在且 api_key 有效。`burn` SHALL 允许配置文件不存在或缺少/留空 api_key：不存在时使用默认烧录样式和码率，存在时应用烧录相关覆盖项，SHALL NOT 验证或使用翻译 API 配置。无法解析的 TOML 或非法烧录配置 SHALL 在处理前报错。`run` 新增 `[vocabulary]` 配置：`enabled` 默认 true、`learner_level` 默认 `N3`、`include_unknown` 默认 true、`max_examples` 默认 3、`output_dir` 默认空字符串、`format` 默认 `both`。`enabled` 和 `include_unknown` SHALL 仅接受布尔值，`learner_level` SHALL 仅接受 N5/N4/N3/N2/N1，`max_examples` SHALL 仅接受 1 到 10 的整数（布尔值不视为整数）。`output_dir` SHALL 为字符串，空字符串回退到 `-o`；非空路径 SHALL 相对命令执行时的 cwd 解析。`format` SHALL 仅接受 `md`、`json`、`both`。`run --vocab-output-dir` 和 `--vocab-format` 的显式值 SHALL 分别优先于合法配置中的对应值；配置本身 SHALL 先通过类型和枚举校验。`run` 新增 `[highlights]` 配置：`enabled` 默认 false、`target_seconds` 默认 240、`intro_start_seconds` 默认 0、`ja_voice` 默认 `Kyoko`、`zh_voice` 默认 `Tingting`。`highlights.enabled` 控制是否输出高光产物，SHALL 仅接受布尔值；`target_seconds` SHALL 仅接受 60 到 900 的整数（布尔值不视为整数）；`intro_start_seconds` SHALL 仅接受不小于 0 的数值（布尔值不视为数值）；`ja_voice` 与 `zh_voice` SHALL 为非空、非纯空白且不含 NUL（U+0000）的字符串。`run --highlights`/`--no-highlights` 的显式值 SHALL 优先于合法配置中的 `highlights.enabled`；配置本身 SHALL 先通过类型和取值校验。`burn` SHALL 忽略词汇与高光配置，不验证其值或要求相关依赖。

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
- **THEN** 使用 enabled=false、target_seconds=240、intro_start_seconds=0、ja_voice=Kyoko、zh_voice=Tingting，即默认不输出高光产物

#### Scenario: 非法学习者等级

- **WHEN** `run` 的 learner_level 不是 N5/N4/N3/N2/N1，或 max_examples 超出范围
- **THEN** 预检失败并给出合法取值，不开始处理视频

#### Scenario: 非法词汇配置类型

- **WHEN** `run` 的 vocabulary.enabled 或 include_unknown 不是布尔值，或 max_examples 不是整数（包括误用布尔值）
- **THEN** 预检失败并给出字段与合法类型，不开始处理视频

#### Scenario: 非法高光配置

- **WHEN** `run` 的 highlights.enabled 不是布尔值、target_seconds 超出 60–900 或非整数、intro_start_seconds 为负数，或 ja_voice/zh_voice 为空或纯空白字符串
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

### Requirement: 全部业务参数的配置映射

系统 SHALL 为 `run` 和 `burn` 的全部现有业务参数提供下表所列的配置键。系统 SHALL 保留既有 `[vocabulary] output_dir` 和 `format`，不得通过新增同义键制造多个配置来源。子命令选择、`--help` 和 `--version` SHALL 保持为命令控制，不写入配置。`download` SHALL 不新增业务参数，并保持既有 ASR 模型配置与回退行为。

| 命令 | 命令行参数 | 配置键 | 无命令行参数且无配置时的行为 |
| --- | --- | --- | --- |
| `run` | 位置参数 `input` | `run.input` | 无默认值，合并后必填 |
| `run` | `-o/--output-dir` | `run.output_dir` | 无默认值，合并后必填 |
| `run` | `--force/--no-force` | `run.force` | `false` |
| `run` | `-y/--yes/--no-yes` | `run.yes` | `false` |
| `run` | `--vocab-output-dir` | `vocabulary.output_dir` | 使用最终有效的 `run` 主输出目录 |
| `run` | `--vocab-format` | `vocabulary.format` | `both` |
| `run` | `--highlights/--no-highlights` | `highlights.enabled` | `false`（默认不输出高光产物） |
| `burn` | 位置参数 `inputs` | `burn.inputs` | 无默认值，合并后必填 |
| `burn` | `-o/--output-dir` | `burn.output_dir` | 无默认值，合并后必填 |
| `burn` | `-s/--subtitles` | `burn.subtitles` | 未指定显式字幕文件 |
| `burn` | `--subtitle-dir` | `burn.subtitle_dir` | 没有任何字幕来源时使用最终有效的 `burn` 主输出目录 |
| `burn` | `-y/--yes/--no-yes` | `burn.yes` | `false` |

#### Scenario: 完全由配置提供运行参数

- **WHEN** 合法配置提供 `run.input="video.mp4"`、`run.output_dir="out"`、`run.force=true` 和 `run.yes=true`，用户执行 `run`
- **THEN** 输入、主输出目录、强制重跑和自动覆盖分别采用这四项配置，并继续执行既有运行前检查

#### Scenario: 完全由配置提供烧录参数

- **WHEN** 合法配置提供 `burn.inputs=["a.mp4", "b.mov"]`、`burn.output_dir="out"`、`burn.subtitle_dir="subs"` 和 `burn.yes=true`，用户执行 `burn`
- **THEN** 两个视频按配置顺序进入烧录输入解析，字幕从 `subs` 匹配，输出到 `out`，自动覆盖采用配置值

#### Scenario: 旧配置与完整命令保持兼容

- **WHEN** 合法配置不含 `[run]` 或 `[burn]`，用户通过命令行提供当前命令的完整输入和主输出目录
- **THEN** 系统使用命令行输入与输出，未指定的布尔选项为 `false`，既有词汇、样式和码率配置继续生效

#### Scenario: 配置开启默认关闭的高光

- **WHEN** 合法配置提供 `highlights.enabled=true`，用户执行 `run video.mp4 -o out` 且未提供高光开关
- **THEN** 本次运行执行高光阶段，行为等同传入 `--highlights`
