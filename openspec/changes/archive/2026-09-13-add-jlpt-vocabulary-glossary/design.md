# Design: add-jlpt-vocabulary-glossary

## 目标与术语

配置 `learner_level = "N3"` 表示用户预计已能处理 N3、N4、N5 词汇，因此目标词汇为更难的 N2、N1。JLPT 数字越小难度越高。

`未分级` 表示目标词没有出现在当前版本的 JLPT 映射数据中，不代表它一定比 N3 难。该组主要覆盖口语、网络用语、行业词、外来语和人名地名；输出必须保留这个不确定性。

## 流水线位置

词汇提取依赖日文字幕；词典语境同时使用中文译文，因此安排在翻译之后、双语合成之前：

```text
video.mp4
  -> transcribe  -> video.ja.srt
  -> translate   -> video.zh.srt
  -> vocabulary  -> video.vocab.json + video.vocab.md
  -> merge       -> video.bilingual.srt
  -> burn        -> video.sub.mp4
```

`vocabulary` 是学习辅助产物，不是烧录的前置条件。该阶段发生异常时，CLI 捕获并记录错误，继续执行 `merge` 和 `burn`。

独立 `burn` 子命令保持只烧录已有 SRT 的行为，支持单文件、多文件与目录；其配置和预检不导入分词器、不加载 JLPT 数据，不要求词汇设置合法、ASR 模型就绪或翻译 API 可用。合并规范时先归档 `add-standalone-burn-command`，再应用本变更的完整 CLI/config requirement 块，保留既有独立烧录场景。

## 模块划分

新增 `ja_video_subtitles/vocabulary.py`，职责包括：

- 解析日文、中文字幕并按 SRT index 建立语境；
- 形态分析、基本形归一化和候选词过滤；
- 查询 JLPT 等级映射；
- 按基本形和读音去重、累计出现次数和语境；
- 分批请求中文词典释义并校验结构；
- 写入 JSON，并由 JSON 确定性渲染 Markdown。

新增 `ja_video_subtitles/jlpt_lexicon.py`，仅负责加载、校验和查询版本化 JLPT 数据，避免数据格式与业务流程耦合。

## 候选词提取

### 形态分析

使用固定版本 `SudachiPy==0.6.11` 与 `SudachiDict-core==20260723`，采用词典查询适用的 SplitMode.C。每个 token 至少取得：

- `surface`：字幕中的实际形式；
- `lemma`：词典基本形；
- `reading`：片假名读音，输出时转换为平假名；
- `part_of_speech`：词性。

动词、形容词的活用形式合并到基本形。例如 `考えていた` 计入 `考える`。Sudachi 的表层读音可能仍为活用形式（如 `考え` 的 `カンガエ`），因此规范化读音需从还原的基本形取得，避免同一词以不同活用读音重复入表。

### 过滤规则

默认保留名词、动词、形容词、副词和感叹词，排除：

- 助词、助动词、标点、空白、纯数字和符号；
- 只有一个假名且没有独立实义的 token；
- 项目维护的高频功能词 stoplist。

专有名词不参与 JLPT 等级猜测：在 `include_unknown = true` 时进入 `未分级` 组，并额外标记 `is_proper_noun = true`。

本次只提取单词，不识别多 token 语法结构。SplitMode.C 保留词典中识别的复合词供直接查询；不在跨 token 序列上猜测固定语法结构。

## JLPT 判级

### 数据要求

采用 `stephenmk/yomitan-jlpt-vocab` 的固定提交 `b062d4e38c4bdd0950ae1d4ec55f04b176182e03`，转换版本为该提交号加 `-v1`，共 8,113 条记录。该上游项目声明 CC-BY-SA-4.0，等级来自 Jonathan Waller 的旧社区参考表，上游对照 JMdict 处理读音和常见写法。它不是 JLPT 官方词表，现代口语、专门术语和网络词汇覆盖有限，不能把未收录词当作高阶词。

项目内 [数据说明](../../../../ja_video_subtitles/data/README.md)、`JLPT-LICENSE.txt` 与保留的 `JLPT-UPSTREAM-README.md` 记录：

- 数据名称和上游地址；
- 固定版本或内容哈希；
- 许可证及项目内的归属说明；
- 字段映射和已知限制。

每个上游输入文件有 SHA-256 固定值，转换脚本仅映射字段并将读音规范化，不修改上游等级，也不丢弃歧义记录。运行时检验 JSON schema、固定版本、词条校验和及完整文件校验和。`python ja_video_subtitles/data/rebuild_jlpt.py` 可抓取同一提交并验证哈希后重建；上游文件已在本地时支持离线重建。数据的许可与项目代码的 MIT 许可分别保留。

查询优先使用 `(lemma, reading)`。只有调用方没有读音，且基本形在数据集中只有一个读音及等级组合时，才允许回退到 `lemma`。调用方提供的非空读音未匹配时，即使同形词只有一个已知等级也标记 `未分级`，避免把未收录读法误标成另一个读法的等级；例如 `生物/せいぶつ` 为 N3，未匹配的 `生物/なまもの` 保持未分级。同一基本形和读音有多个等级时也标记未分级，不取更难等级来制造确定性。

筛选规则由等级顺序 `N5 < N4 < N3 < N2 < N1` 驱动。例如：

- learner N3 -> N2、N1；
- learner N4 -> N3、N2、N1；
- learner N1 -> 无更高 JLPT 词，仅可能输出未分级词。

## 中文词典释义

判级在本地完成，DeepSeek 不负责决定 JLPT 等级。对筛选、去重后的词汇分批调用现有 OpenAI 兼容 client（默认模型 `deepseek-flash`），输入稳定 ID、基本形、读音、词性和一个原句，要求返回 JSON。提取与判级不访问网络；只有翻译与词义生成把相应文本发送到用户配置的 API，不发送音视频。DeepSeek 官方端点的请求显式关闭 thinking，其他兼容端点保持其原有参数。

预期响应：

```json
{
  "items": [
    {
      "id": "w1",
      "meaning_zh": "预料；估计",
      "note_zh": "常用于表达基于现状作出的推测"
    }
  ]
}
```

响应必须满足 ID 完整、无重复、字段类型正确。失败时沿用现有翻译策略：重试、拆半；单词级最终失败时仍保留本地识别结果，将 `meaning_zh` 留空并写入 warning，不丢弃整个词条。

中文译句不由模型重新生成，直接从同 index 的 `xxx.zh.srt` 取得，确保与视频字幕一致。

## 去重和语境

唯一键为规范化后的 `(lemma, reading)`。每个词条保存：

- 首次出现时间；
- 总出现次数；
- 最多 `max_examples` 个不同字幕语境，默认 3；
- 每个语境的 SRT index、开始时间、日文原句和已有中文译句。

同一字幕内同一词重复出现，出现次数按实际次数累计，但该字幕只保存一次语境。

## 输出格式

### `xxx.vocab.json`

顶层结构包含：

```json
{
  "schema_version": 1,
  "source": {
    "ja_srt": "xxx.ja.srt",
    "ja_srt_sha256": "...",
    "zh_srt": "xxx.zh.srt",
    "zh_srt_sha256": "..."
  },
  "settings": {
    "learner_level": "N3",
    "include_unknown": true,
    "max_examples": 3,
    "jlpt_dataset": "name@version",
    "extractor_version": 1,
    "morphology_versions": {
      "SudachiPy": "0.6.11",
      "SudachiDict-core": "20260723"
    }
  },
  "entries": []
}
```

每个 entry 包含 `lemma`、`reading`、`surface_forms`、`part_of_speech`、`jlpt_level`、`is_proper_noun`、`meaning_zh`、`note_zh`、`occurrence_count` 和 `examples`。

### `xxx.vocab.md`

Markdown 面向直接阅读，示例：

```markdown
## N1

### 見落とす（みおとす）

- 词性：动词
- 中文：看漏；忽略
- 出现：2 次
- 首次位置：00:03:18

> 書類の間違いを見落としてしまった。
>
> 我不小心漏看了文件中的错误。
```

文件顶部注明学习者等级、JLPT 数据来源版本、生成时间以及“非官方等级参考”提示。默认 N3 配置下按 N2、N1、未分级分组；其他学习者等级依次显示严格更难的级别，再显示未分级，组内按首次出现时间排序。示例中的 `見落とす` 在选定数据中标为 N1。没有目标词汇时仍生成合法文件，并明确写“未发现符合条件的词汇”。

## 配置

在 `config.toml` 增加：

```toml
[vocabulary]
enabled = true
learner_level = "N3"
include_unknown = true
max_examples = 3
```

- `learner_level` 仅允许 `N5`、`N4`、`N3`、`N2`、`N1`；
- `enabled`、`include_unknown` 仅接受布尔值；`max_examples` 仅接受 1 到 10 的整数，不接受布尔值；
- 配置非法时在预检阶段报错；
- `enabled = false` 时不加载分词器、不运行词汇阶段、不要求词表数据就绪。

## 断点续跑

只有同时满足以下条件才跳过 vocabulary 阶段：

- JSON 与 Markdown 都存在且可读；
- JSON schema 合法；
- `ja_srt_sha256`、`zh_srt_sha256` 与当前日文、中文字幕一致；
- learner level、include_unknown、max_examples、JLPT 数据版本、提取器和形态分析版本一致。

配置或源字幕变化时自动重建词表。`--force` 无条件重建。

`run` 的双语字幕也校验内容新鲜度：只有缓存的 SRT 与当前日文、中文按 index 合成的时间轴和文本一致才跳过合成。修改日文或中文后重新运行时，词汇语境与烧录用双语字幕同时更新，避免词表和成片显示不同译文。独立 `burn` 保持直接读取用户选定 SRT 的行为，不合成、不修改字幕。

先原子写入临时文件，再替换正式 JSON/Markdown，避免中断留下“看似存在但内容不完整”的产物。

## 报告和错误语义

报告增加 `Vocabulary` 阶段，记录目标词数量、N2/N1/未分级数量、释义降级数量和耗时；产物清单包含 `.vocab.md`、`.vocab.json`。

错误分三类：

- 单词释义失败：保留词条并留空释义，阶段完成但带 warning，报告计入释义降级；其他阶段成功时视频仍为 succeeded；
- 无目标词：正常完成，输出空词表；
- 阶段级失败（分词器、数据文件、写文件异常）：视频标记为 `partial`，继续合成和烧录。

批量结束汇总增加 partial 数量；存在 `partial` 或 `failed` 时进程退出码为 1，方便无人值守任务发现词表缺失。

## 测试策略

- 单元测试：活用归一化、词性过滤、N3 阈值、同形异音、去重、出现次数和排序；
- API stub 测试：完整响应、乱序 ID、漏项、重复项、重试与单词级降级；
- 产物测试：JSON schema、Markdown 内容、空词表、原子写入；
- 断点测试：源字幕、配置或数据版本变化时重跑，不变时跳过；
- 流水线测试：词汇阶段失败仍生成 `.bilingual.srt` 和 `.sub.mp4`，报告为 partial；
- 真实日语样本人工抽查：N2/N1 判级、基本形、读音、释义和上下文准确性。

## 备选方案及取舍

### 完全交给大模型提取和判级

实现更少，但同一词的 JLPT 等级可能随 prompt 和模型版本变化，漏词和误判难以自动验证，因此不采用。

### 只用本地词典

判级稳定且无新增 API 成本，但难以得到自然的简体中文释义，尤其是口语和行业词。因此采用本地判级、API 释义的混合方案。

### 仅输出 Markdown

短期简单，但无法可靠判断旧产物是否与当前字幕、等级配置和数据版本匹配，也不利于未来导出 Anki。因此同时保留 JSON。
