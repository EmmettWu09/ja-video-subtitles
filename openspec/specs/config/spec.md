# config Specification

## Purpose
集中管理翻译服务、ASR、字幕样式、视频码率和词汇学习设置，并按完整流水线或独立烧录验证所需配置。 各配置项具有明确的默认值、合法取值及失败提示，使批量运行可重复，并使独立烧录能够在没有翻译密钥或模型时工作。

## Requirements

### Requirement: 配置文件

配置文件 SHALL 从项目根目录（包所在位置）的 `config.toml` 读取，与命令执行时的当前目录无关。配置项包含 DeepSeek `base_url`（默认 `https://api.deepseek.com`）、`api_key`（无默认值）、`model`（默认 `deepseek-flash`），有内置默认值的翻译 prompt 模板、烧录字幕样式及 `[video] bitrate`（默认 `8M`）。`run` SHALL 要求配置文件存在且 api_key 有效。`burn` SHALL 允许配置文件不存在或缺少/留空 api_key：不存在时使用默认烧录样式和码率，存在时应用烧录相关覆盖项，SHALL NOT 验证或使用翻译 API 配置。无法解析的 TOML 或非法烧录配置 SHALL 在处理前报错。`run` 新增 `[vocabulary]` 配置：`enabled` 默认 true、`learner_level` 默认 `N3`、`include_unknown` 默认 true、`max_examples` 默认 3、`output_dir` 默认空字符串、`format` 默认 `both`。`enabled` 和 `include_unknown` SHALL 仅接受布尔值，`learner_level` SHALL 仅接受 N5/N4/N3/N2/N1，`max_examples` SHALL 仅接受 1 到 10 的整数（布尔值不视为整数）。`output_dir` SHALL 为字符串，空字符串回退到 `-o`；非空路径 SHALL 相对命令执行时的 cwd 解析。`format` SHALL 仅接受 `md`、`json`、`both`。`run --vocab-output-dir` 和 `--vocab-format` 的显式值 SHALL 分别优先于合法配置中的对应值；配置本身 SHALL 先通过类型和枚举校验。`burn` SHALL 忽略词汇配置，不验证其值或要求词汇依赖。

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

#### Scenario: 非法学习者等级

- **WHEN** `run` 的 learner_level 不是 N5/N4/N3/N2/N1，或 max_examples 超出范围
- **THEN** 预检失败并给出合法取值，不开始处理视频

#### Scenario: 非法词汇配置类型

- **WHEN** `run` 的 vocabulary.enabled 或 include_unknown 不是布尔值，或 max_examples 不是整数（包括误用布尔值）
- **THEN** 预检失败并给出字段与合法类型，不开始处理视频

#### Scenario: 禁用词汇功能

- **WHEN** vocabulary.enabled 为 false
- **THEN** 不运行词汇阶段，也不要求形态分析词典和 JLPT 数据就绪

#### Scenario: 独立烧录忽略词汇设置

- **WHEN** `burn` 使用的 TOML 可以解析，但 vocabulary 部分缺失或包含非法词汇配置
- **THEN** 仅验证并应用烧录配置，不因词汇设置或词典缺失而阻止烧录

#### Scenario: 命令行覆盖词汇输出配置

- **WHEN** 配置为 output_dir="saved-words"、format="json"，命令指定 `--vocab-output-dir notes --vocab-format md`
- **THEN** 词汇只生成到 cwd 下 `notes` 的 Markdown，配置值不覆盖显式参数

#### Scenario: 配置中的相对目录

- **WHEN** 用户从项目以外的目录执行命令，配置 output_dir="words" 且没有对应 CLI 覆盖
- **THEN** 词汇目录为命令执行时 cwd 下的 `words`，不是 config.toml 所在目录下的 `words`

#### Scenario: 非法输出配置

- **WHEN** `run` 的 vocabulary.output_dir 不是字符串，或 vocabulary.format 不是 md/json/both
- **THEN** 在处理前给出字段及合法类型/取值错误，退出码为 2

### Requirement: 模板与密钥隔离
仓库 SHALL 提供 `config.example.toml` 模板入库；`config.toml` 真实密钥文件 SHALL 被 `.gitignore` 排除，不得入库。

#### Scenario: 首次配置
- **WHEN** 用户首次使用
- **THEN** 可复制 `config.example.toml` 为 `config.toml`，仅需填入 api_key 即可运行

### Requirement: 词汇输出配置回退

`run` SHALL 分别解析词汇目录和格式，每项按「显式命令行参数 → `config.toml` 的对应配置 → 内置默认值」取值。`--vocab-output-dir` SHALL 仅覆盖 `[vocabulary] output_dir`，`--vocab-format` SHALL 仅覆盖 `[vocabulary] format`。格式默认 `both`，同时输出 Markdown 和 JSON；配置目录为空或缺失时 SHALL 使用 `-o/--output-dir`，即生成的 `<stem>.sub.mp4` 所在目录。示例配置和命令帮助 SHALL 清楚标明该规则。

#### Scenario: 省略两个命令行词汇参数

- **WHEN** 配置为 output_dir="notes"、format="md"，执行 `run video.mp4 -o media`
- **THEN** 词汇输出使用 cwd 下的 notes 目录且仅生成 Markdown；字幕视频仍输出到 media

#### Scenario: 只覆盖格式

- **WHEN** 配置为 output_dir="notes"、format="both"，执行 `run video.mp4 -o media --vocab-format json`
- **THEN** 词汇输出到 notes 且仅生成 JSON，目录配置保留

#### Scenario: 只覆盖目录

- **WHEN** 配置为 output_dir="notes"、format="md"，执行 `run video.mp4 -o media --vocab-output-dir words`
- **THEN** 词汇输出到 words 且仅生成 Markdown，格式配置保留

#### Scenario: 使用内置默认值

- **WHEN** output_dir 和 format 配置均缺失，且未传两个命令行词汇参数
- **THEN** 在 -o 目录同时生成 `<stem>.vocab.md`、`<stem>.vocab.json`，与 `<stem>.sub.mp4` 同目录
