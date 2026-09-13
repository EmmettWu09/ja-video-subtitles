# Spec: vocabulary

## ADDED Requirements

### Requirement: 按学习者等级提取词汇

系统 SHALL 对日文 SRT 做本地形态分析，将活用形式归一为基本形，并基于版本化 JLPT 词汇数据筛选严格高于 `learner_level` 的词汇。默认 `learner_level` 为 N3，因此 SHALL 收录 N2、N1，排除 N3、N4、N5。查询 SHALL 优先精确匹配基本形和读音，只有读音缺失且数据中该基本形对应唯一读音及等级时才允许基本形回退；非空读音未命中或存在等级歧义时 SHALL 标记未分级。判级结果 SHALL 标注数据来源与版本，不得宣称为 JLPT 官方词表结论。

#### Scenario: N3 用户遇到不同等级词汇

- **WHEN** 字幕同时包含可判定为 N4、N3、N2、N1 的词汇且 learner_level 为 N3
- **THEN** 词表只包含 N2、N1 词汇

#### Scenario: 活用形式

- **WHEN** 字幕中出现同一动词的多个活用形式
- **THEN** 它们合并为一个基本形词条，出现次数正确累计

#### Scenario: 等级映射存在歧义

- **WHEN** 仅凭基本形和读音不能唯一确定 JLPT 等级
- **THEN** 系统将该词标为未分级，不猜测为 N1 或 N2

#### Scenario: 同形词的读音未收录

- **WHEN** 数据含 `生物/せいぶつ` 的 N3 记录，但调用方给出的读音是未收录的 `なまもの`
- **THEN** 标记为未分级，不复用另一读法的 N3 等级

### Requirement: 未分级实义词

当 `include_unknown = true` 时，系统 SHALL 收录不在 JLPT 数据中的实义词并标记为 `未分级`，包括符合过滤规则的专有名词；专有名词 SHALL 额外标记。系统 SHALL 排除助词、助动词、标点、纯数字、符号和无独立实义的单假名 token。当 `include_unknown = false` 时，未分级词 SHALL 不输出。

#### Scenario: 字幕含人名和助词

- **WHEN** 字幕含一个未分级人名及多个助词，且 include_unknown 为 true
- **THEN** 人名进入未分级组并标记为专有名词，助词不进入词表

### Requirement: 去重和语境

系统 SHALL 按规范化 `(基本形, 读音)` 去重，记录所有表层形式、总出现次数、首次出现时间，并保存最多 `max_examples` 个不同字幕语境。每个语境 SHALL 包含 SRT index、开始时间、日文原句和同 index 的现有中文译句。

#### Scenario: 同一词多次出现

- **WHEN** 同一基本形在视频中以不同活用形式出现 5 次，分布在 4 条字幕中，max_examples 为 3
- **THEN** 输出一个词条，occurrence_count 为 5，保存 3 条不同字幕语境

### Requirement: 中文词典释义

系统 SHALL 使用 config 中的 OpenAI 兼容接口为去重后的目标词生成简体中文词典义和简短用法说明。JLPT 等级 SHALL 来自本地数据，不得由该接口覆盖。接口响应 SHALL 通过稳定 ID 做完整性、唯一性和字段类型校验；失败时 SHALL 重试并拆分批次，单词级最终失败 SHALL 保留词条、留空释义并记录 warning。

#### Scenario: 单个词释义失败

- **WHEN** 某词在重试和拆分后仍无法取得合法释义
- **THEN** 该词仍出现在词表中，等级、读音和语境保留，释义为空且报告记录一次降级

### Requirement: 词汇产物

系统 SHALL 在输出目录原子生成 `<stem>.vocab.json` 和 `<stem>.vocab.md`。JSON SHALL 包含 schema version、日文及中文字幕 SHA-256、学习者配置、JLPT 数据版本、形态分析版本和结构化词条；Markdown SHALL 标明数据来源及非官方等级提示。默认 N3 时 SHALL 按 N2、N1、未分级分组；其他 learner_level SHALL 按严格更难的等级由易至难分组，再列未分级，组内按首次出现时间排序。

#### Scenario: 正常生成 N3 词表

- **WHEN** N3 用户的视频字幕中含 N2、N1 和未分级目标词
- **THEN** 两种词汇产物均生成，内容一致且可追溯到字幕时间和原句

#### Scenario: 没有高阶词汇

- **WHEN** 字幕中没有符合筛选条件的词
- **THEN** 系统仍生成合法的空 JSON 和 Markdown，Markdown 明确说明未发现符合条件的词汇

#### Scenario: 写入中断

- **WHEN** 生成过程中进程被中断
- **THEN** 不留下被误认为有效产物的不完整正式 JSON 或 Markdown

### Requirement: 词汇断点续跑

仅当 JSON/Markdown 均合法，且 JSON 中的日文及中文字幕哈希、学习者等级、include_unknown、max_examples、JLPT 数据版本、提取器和形态分析版本均与当前运行一致时，系统 SHALL 跳过词汇阶段。任一项变化或指定 `--force` 时 SHALL 重新生成。

#### Scenario: 修改学习者等级

- **WHEN** 已有 N3 词表，用户将 learner_level 改为 N2 后重新运行
- **THEN** 旧词表不被复用，系统按 N2 阈值重新生成
