# Spec: vocabulary

## MODIFIED Requirements

### Requirement: 词汇产物

系统 SHALL 在有效词汇目录原子生成所选格式的词汇产物：`md` 仅生成 `<stem>.vocab.md`，`json` 仅生成 `<stem>.vocab.json`，`both` 生成两者。目录默认是 `-o`，格式默认是 `both`。JSON SHALL 包含 schema version、日文及中文字幕 SHA-256、学习者配置、JLPT 数据版本、形态分析版本和结构化词条；Markdown SHALL 标明数据来源及非官方等级提示。Markdown-only SHALL 在同一文件中保存足以独立验证完整性和新鲜度的元数据，SHALL NOT 为此生成额外 JSON sidecar。默认 N3 时 SHALL 按 N2、N1、未分级分组；其他 learner_level SHALL 按严格更难的等级由易至难分组，再列未分级，组内按首次出现时间排序。系统 SHALL NOT 删除或改写本次未选中的历史词汇文件。

#### Scenario: 正常生成 N3 词表

- **WHEN** N3 用户的视频字幕中含 N2、N1 和未分级目标词，使用默认格式
- **THEN** 两种词汇产物均生成，内容一致且可追溯到字幕时间和原句

#### Scenario: 没有高阶词汇

- **WHEN** 字幕中没有符合筛选条件的词
- **THEN** 按当前格式生成合法空词表；选中 Markdown 时明确说明未发现符合条件的词汇

#### Scenario: 写入中断

- **WHEN** 生成过程中进程被中断
- **THEN** 不留下被误认为有效产物的不完整正式 JSON 或 Markdown

#### Scenario: 仅输出 Markdown

- **WHEN** 有效格式为 md，词汇目标目录最初为空
- **THEN** 仅生成 `<stem>.vocab.md`，其中包含可独立校验的元数据，不生成公开或隐藏 JSON 文件

#### Scenario: 仅输出 JSON

- **WHEN** 有效格式为 json
- **THEN** 生成完整结构化 JSON，不生成或更新 Markdown

#### Scenario: 切换输出目录

- **WHEN** 将词汇输出目录从 `media` 改为 `words`
- **THEN** 本次词汇产物只写入 `words`，不移动、改写或删除 `media` 下的旧词表

### Requirement: 词汇断点续跑

仅当当前所选的词汇产物均合法，且其中的日文及中文字幕哈希、学习者等级、include_unknown、max_examples、JLPT 数据版本、提取器和形态分析版本均与当前运行一致时，系统 SHALL 跳过词汇生成。Markdown-only SHALL 不依赖 JSON 文件；JSON-only SHALL 不依赖 Markdown 文件；both SHALL 验证两种文件内容一致。所选文件缺失、损坏或格式切换时，系统 MAY 利用同目录中的有效 JSON 或嵌入 Markdown 的结构化数据重建所选文件，无需重复调用释义 API。元数据不匹配时 SHALL 重新提取；指定 `--force` 时 SHALL 忽略缓存，重新生成当前所选格式。未选文件 SHALL NOT 作为必需的复用条件，SHALL NOT 被改写或删除。

#### Scenario: 修改学习者等级

- **WHEN** 已有 N3 词表，用户将 learner_level 改为 N2 后重新运行
- **THEN** 旧词表不被复用，系统按 N2 阈值重新生成

#### Scenario: Markdown-only 独立续跑

- **WHEN** 仅存在合法且元数据与当前输入一致的 md-only 词表，当前格式为 md
- **THEN** 复用该词表，不要求或创建 JSON，不调用词汇释义 API

#### Scenario: JSON-only 独立续跑

- **WHEN** 仅存在合法且元数据与当前输入一致的 JSON，当前格式为 json
- **THEN** 复用 JSON，不要求或创建 Markdown

#### Scenario: 内容或元数据损坏

- **WHEN** 所选词汇文件被截断、嵌入元数据损坏，或 Markdown 内容与结构化数据不一致
- **THEN** 不把该文件视为有效缓存；使用其他有效缓存修复，或重新生成

#### Scenario: 切换格式补齐文件

- **WHEN** 只有新鲜有效的 JSON，用户改为 md 或 both
- **THEN** 可从该 JSON 生成所选 Markdown，不重复请求词义；md 模式保留旧 JSON 但不更新或报告它

#### Scenario: 字幕或数据改变

- **WHEN** 日文/中文字幕、学习者设置、JLPT 数据或形态分析版本发生变化
- **THEN** 无论选择何种格式，旧缓存不再用于跳过提取，按当前内容重新生成所选产物
