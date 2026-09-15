## ADDED Requirements

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
