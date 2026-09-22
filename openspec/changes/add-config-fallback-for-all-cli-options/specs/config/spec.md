## ADDED Requirements

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

### Requirement: 按显式提供状态解析优先级

在当前命令所需配置通过字段校验后，每个普通业务参数 SHALL 按「显式命令行参数 → 对应配置值 → 内置默认值」独立解析。系统 SHALL 区分命令行未提供与显式布尔 `false`，不得以真假判断或命令行解析阶段填入的业务默认值覆盖配置。`run` 的 `force` 和 `yes`、`burn` 的 `yes` SHALL 支持显式开启和显式关闭。一次调用中同一布尔选项的正反开关同时出现 SHALL 报错，而不得按出现顺序取最后一个值。烧录字幕来源 SHALL 遵循单独规定的整组覆盖规则。

#### Scenario: 命令行只覆盖指定字段

- **WHEN** 合法配置为 `run.input="saved.mp4"`、`run.output_dir="saved-out"`、`run.force=true`、`run.yes=true`、`vocabulary.output_dir="words"`、`vocabulary.format="json"`，用户执行 `run cli.mp4 -o cli-out --vocab-format md`
- **THEN** 有效输入为 `cli.mp4`，主输出目录为 `cli-out`，词汇格式为 `md`，其余配置中的强制重跑、自动覆盖和词汇目录继续生效

#### Scenario: 未提供布尔参数保留配置值

- **WHEN** 配置为 `run.force=true` 和 `run.yes=true`，用户未提供任何对应布尔开关
- **THEN** 最终有效的 `force` 和 `yes` 均为 `true`

#### Scenario: 显式关闭配置中的开启值

- **WHEN** 配置为 `run.force=true` 和 `run.yes=true`，用户提供 `--no-force --no-yes`
- **THEN** 最终有效的 `force` 和 `yes` 均为 `false`

#### Scenario: 烧录显式关闭自动覆盖

- **WHEN** 配置为 `burn.yes=true`，用户执行 `burn --no-yes` 且其他必需参数可从配置补齐
- **THEN** 最终有效的 `burn.yes` 为 `false`，覆盖确认遵循现有交互规则

#### Scenario: 显式开启覆盖配置中的关闭值

- **WHEN** 配置为 `run.force=false` 和 `run.yes=false`，用户提供 `--force -y`
- **THEN** 最终有效的 `force` 和 `yes` 均为 `true`

#### Scenario: 正反布尔开关不能同时指定

- **WHEN** 用户同时提供 `--force --no-force`，或同时提供 `--yes --no-yes`，不论顺序及 `-y` 别名
- **THEN** 系统以退出码 2 报告冲突，不开始处理视频

### Requirement: 输入列表与必需参数合并

`run.input`、`run.output_dir`、`burn.inputs` 和 `burn.output_dir` SHALL 在命令行与配置合并后校验是否已提供，不得因命令行省略而提前拒绝可由配置补齐的调用。上述参数 SHALL 没有隐式默认路径；仍缺少必需值时，系统 SHALL 指出对应命令行参数和配置键，以退出码 2 结束。`burn` 的显式命令行输入列表 SHALL 整体替换 `burn.inputs`，不得追加配置中的输入，替换后 SHALL 保留既有输入顺序、目录展开、去重及同名输出冲突检查。

#### Scenario: 混合来源补齐必需参数

- **WHEN** 合法配置仅提供 `run.input="saved.mp4"`，用户执行 `run -o out`
- **THEN** 系统使用配置输入和命令行输出目录，不因缺少位置参数而报错

#### Scenario: 合并后仍缺少主输出目录

- **WHEN** 用户执行 `run video.mp4`，合法配置未提供 `run.output_dir`
- **THEN** 系统以退出码 2 提示通过 `-o/--output-dir` 或 `run.output_dir` 指定主输出目录，不开始处理视频

#### Scenario: 合并后仍缺少烧录输入

- **WHEN** 用户执行 `burn -o out`，合法配置未提供 `burn.inputs`
- **THEN** 系统以退出码 2 提示通过位置参数 `inputs` 或 `burn.inputs` 指定输入，不开始处理视频

#### Scenario: 命令行列表整体替换配置列表

- **WHEN** 合法配置提供 `burn.inputs=["saved-a.mp4", "saved-b.mov"]`，用户执行 `burn cli-a.mov cli-b.mp4 -o out`
- **THEN** 有效原始输入列表只有 `cli-a.mov` 和 `cli-b.mp4`，顺序不变，不解析或处理配置列表中的文件

### Requirement: 烧录字幕来源按组覆盖

`burn.subtitles` 与 `burn.subtitle_dir` SHALL 构成互斥的字幕来源组；配置中的空字符串 SHALL 视为未设置来源。用户显式提供 `-s/--subtitles` 或 `--subtitle-dir` 中任意一个时，该命令行来源 SHALL 整体替换配置中的两个来源。未提供命令行来源时，系统 SHALL 使用配置来源；最终仍未设置任何来源时，SHALL 从最终有效主输出目录匹配 `<video-stem>.bilingual.srt`。互斥检查 SHALL 应用于最终有效来源组；最终显式字幕文件 SHALL 继续要求展开和去重后恰好一个视频。

#### Scenario: 字幕文件覆盖配置字幕目录

- **WHEN** 合法配置提供 `burn.subtitle_dir="saved-subs"`，用户为一个视频提供 `--subtitles cli.srt`
- **THEN** 系统只使用 `cli.srt`，不因配置中的字幕目录与命令行字幕文件同时存在而报错

#### Scenario: 字幕目录覆盖配置字幕文件

- **WHEN** 合法配置提供 `burn.subtitles="saved.srt"`，用户提供 `--subtitle-dir cli-subs`
- **THEN** 系统只从 `cli-subs` 匹配字幕，配置中的显式字幕文件不参与来源选择

#### Scenario: 配置来源组冲突且没有命令行覆盖

- **WHEN** 配置中的 `burn.subtitles` 与 `burn.subtitle_dir` 均为合法非空路径字符串，用户未提供命令行字幕来源
- **THEN** 系统以退出码 2 报告两个配置来源互斥，不开始处理视频

#### Scenario: 命令行来源可替换冲突的配置来源组

- **WHEN** 配置中的 `burn.subtitles` 与 `burn.subtitle_dir` 均为合法非空路径字符串，用户显式提供 `--subtitle-dir cli-subs`
- **THEN** 最终来源组只包含 `cli-subs`，不因已被整体替换的配置来源组冲突而失败

#### Scenario: 命令行自身来源互斥

- **WHEN** 用户同时提供 `--subtitles cli.srt` 和 `--subtitle-dir cli-subs`
- **THEN** 系统以退出码 2 报告命令行来源冲突，不开始处理视频

#### Scenario: 空配置来源回退有效输出目录

- **WHEN** 配置中 `burn.subtitles=""`、`burn.subtitle_dir=""`、`burn.output_dir="saved-out"`，用户执行 `burn video.mp4 -o cli-out`
- **THEN** 系统从 `cli-out/video.bilingual.srt` 读取字幕

#### Scenario: 配置字幕文件仍限制视频数量

- **WHEN** 最终有效来源为配置中的 `burn.subtitles="captions.srt"`，最终输入展开和去重后包含两个视频
- **THEN** 系统以退出码 2 提示显式字幕文件要求恰好一个视频，不开始任何烧录

### Requirement: 命令作用域内配置的严格校验

当前命令对应的 `[run]` 或 `[burn]` 配置节如存在 SHALL 为 TOML 表。当前命令读取的已配置字段 SHALL 在应用命令行覆盖前通过类型和取值校验：`run.input`、`run.output_dir`、`burn.output_dir` SHALL 为非空、非纯空白且不含 NUL（U+0000）的路径字符串；`burn.inputs` SHALL 为至少包含一个元素的字符串数组，每个元素 SHALL 为非空、非纯空白且不含 NUL（U+0000）的路径字符串；`run.force`、`run.yes`、`burn.yes` SHALL 为布尔值，不接受字符串或数字替代。`burn.subtitles`、`burn.subtitle_dir` 和 `vocabulary.output_dir` SHALL 为不含 NUL（U+0000）的字符串，仅精确空字符串允许作为缺省值，非空但纯空白的字符串 SHALL 报错。`vocabulary.format` SHALL 继续仅接受 `md`、`json` 或 `both`。配置缺少字段 SHALL 允许后续命令行补齐或使用默认值；已配置非法值 SHALL 不被合法命令行值掩盖。校验失败 SHALL 指出配置字段和允许的类型或取值，以退出码 2 结束。

所有显式 CLI 路径（含位置输入、主输出、词汇目录及字幕文件/目录）SHALL 拒绝空字符串、纯空白和 NUL（U+0000），不得将这些非法值当作未提供。合法路径中的空格和其他字符 SHALL 原样保留，不得自动裁剪。

字段校验 SHALL 不检查路径是否存在或可写，不展开目录输入，也不判断字幕来源组互斥；这些检查 SHALL 仅针对合并后的最终有效值执行。最终有效值仍 SHALL 通过现有视频输入、字幕合法性、输出可写性及输入输出别名冲突检查。

#### Scenario: 配置表类型错误不能被命令行覆盖

- **WHEN** 当前执行 `run`，配置为 `run="invalid"`，命令行已提供合法输入和主输出目录
- **THEN** 系统以退出码 2 提示 `run` 必须为 TOML 表，不开始处理视频

#### Scenario: 布尔配置严格区分字符串与布尔值

- **WHEN** 当前命令对应的 `force` 或 `yes` 配置为字符串 `"true"`、整数 `1` 或整数 `0`，即使命令行提供了对应正反开关
- **THEN** 系统报告该配置字段必须为布尔值，以退出码 2 结束

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

### Requirement: 配置文件定位与业务路径基准

配置文件 SHALL 继续从项目根目录的 `config.toml` 加载。命令行及配置中的所有最终有效业务路径 SHALL 统一展开 `~`，相对路径 SHALL 以命令执行时的 cwd 为基准，不以配置文件目录为基准；此规则适用于视频输入、主输出目录、字幕文件、字幕目录及词汇输出目录。目录回退 SHALL 在主输出目录完成优先级解析后计算。`vocabulary.output_dir` 缺失或为空且没有显式词汇目录覆盖时，SHALL 使用最终有效 `run` 主输出目录。词汇功能禁用时 SHALL 保持不解析、不检查自定义词汇输出目录的既有行为。

#### Scenario: 从项目外目录使用相对路径

- **WHEN** 项目根目录的配置提供 `run.input="videos/a.mp4"` 和 `run.output_dir="out"`，用户从另一个目录执行 `run`
- **THEN** 配置仍来自项目根目录，输入与输出分别位于命令 cwd 下的 `videos/a.mp4` 和 `out`

#### Scenario: 命令行与配置均支持用户主目录

- **WHEN** 最终有效输入、输出或字幕路径由命令行或配置提供，且以 `~/` 开头
- **THEN** 系统将其展开为当前用户主目录下的路径后执行既有路径检查

#### Scenario: 词汇缺省目录跟随配置主输出目录

- **WHEN** `run.output_dir="media"`，`vocabulary.output_dir=""`，用户未提供 `-o` 或 `--vocab-output-dir`
- **THEN** 词汇输出与字幕视频均位于 cwd 下的 `media`

#### Scenario: 词汇缺省目录跟随命令行主输出覆盖

- **WHEN** `run.output_dir="saved-media"`，`vocabulary.output_dir=""`，用户提供 `-o cli-media` 而未提供 `--vocab-output-dir`
- **THEN** 词汇输出与字幕视频均位于 cwd 下的 `cli-media`

#### Scenario: 禁用词汇后不解析其目录

- **WHEN** `vocabulary.enabled=false`，`vocabulary.output_dir` 是类型合法但无法解析或不可写的自定义路径
- **THEN** 系统不解析、不检查或创建该词汇目录，其他必要预检继续执行

### Requirement: 子命令配置隔离与缺失文件兼容

`run` SHALL 读取并验证 `[run]` 及既有完整流水线所需配置，忽略 `[burn]` 的形状和值。`burn` SHALL 只读取并验证 `[burn]`、`[style]` 和 `[video]`，忽略 `[run]`、`[deepseek]`、`[asr]`、`[prompt]` 和 `[vocabulary]` 的形状和值，不要求翻译 API、ASR 模型或词汇依赖。配置文件语法无法解析 SHALL 不受命令作用域隔离保护：`run` 和 `burn` 均 SHALL 以退出码 2 报错。缺少配置文件时，`run` SHALL 继续报错；`burn` 在命令行提供完整必需参数时 SHALL 使用内置布尔值、字幕来源和烧录设置继续运行。

#### Scenario: 运行忽略烧录命令专属配置

- **WHEN** `[run]` 与流水线配置合法，但 `burn` 被配置为错误类型或包含非法字段值，用户执行 `run`
- **THEN** `run` 不因 `burn` 配置而失败

#### Scenario: 烧录忽略流水线专属配置

- **WHEN** `[burn]`、`[style]` 和 `[video]` 合法，其他配置节形状或字段值非法但整个 TOML 可解析，用户执行 `burn`
- **THEN** `burn` 不校验这些无关配置，不初始化翻译、ASR 或词汇依赖，继续本地烧录预检

#### Scenario: 烧录不能忽略 TOML 语法损坏

- **WHEN** `config.toml` 包含 TOML 语法错误，即使命令行提供了 `burn` 的完整参数
- **THEN** 系统以退出码 2 提示配置解析错误，不开始任何视频烧录

#### Scenario: 无配置烧录使用命令行与默认值

- **WHEN** `config.toml` 不存在，用户执行 `burn video.mp4 -o out`
- **THEN** 输入与输出来自命令行，`yes=false`，字幕从 `out/video.bilingual.srt` 匹配，使用内置字幕样式与 `8M` 码率并继续本地预检

#### Scenario: 完整命令行不取消运行对配置文件的要求

- **WHEN** `config.toml` 不存在，用户提供 `run` 的完整业务参数
- **THEN** 系统继续提示创建配置文件及填写有效翻译密钥，以退出码 2 结束
