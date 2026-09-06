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

建议使用 `SudachiPy` 与 `SudachiDict-core`，采用适合词典查询的拆分模式。每个 token 至少取得：

- `surface`：字幕中的实际形式；
- `lemma`：词典基本形；
- `reading`：片假名读音，输出时转换为平假名；
- `part_of_speech`：词性。

动词、形容词的活用形式合并到基本形。例如 `考えていた` 计入 `考える`。

### 过滤规则

默认保留名词、动词、形容词、副词和感叹词，排除：

- 助词、助动词、标点、空白、纯数字和符号；
- 只有一个假名且没有独立实义的 token；
- 项目维护的高频功能词 stoplist。

专有名词不参与 JLPT 等级猜测：在 `include_unknown = true` 时进入 `未分级` 组，并额外标记 `is_proper_noun = true`。

本次只提取单词，不识别多 token 语法结构。词表数据中明确登记的固定复合词，可以在规范化 token 序列上做最长匹配；实现前需用选定数据集验证可行性。

## JLPT 判级

### 数据要求

实现前必须选择一份允许再分发或允许安装时获取的 JLPT 词汇数据，并记录：

- 数据名称和上游地址；
- 固定版本或内容哈希；
- 许可证及项目内的归属说明；
- 字段映射和已知限制。

不得在来源和许可证未确认前直接把第三方词表提交进仓库。

查询优先使用 `(lemma, reading)`，只在结果唯一时回退到 `lemma`。同形异音或同形多等级无法唯一确定时标记 `未分级`，不取更难等级来制造确定性。

筛选规则由等级顺序 `N5 < N4 < N3 < N2 < N1` 驱动。例如：

- learner N3 -> N2、N1；
- learner N4 -> N3、N2、N1；
- learner N1 -> 无更高 JLPT 词，仅可能输出未分级词。

## 中文词典释义

判级在本地完成，DeepSeek 不负责决定 JLPT 等级。对筛选、去重后的词汇分批调用现有 OpenAI 兼容 client，输入稳定 ID、基本形、读音、词性和一个原句，要求返回 JSON：

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
    "ja_srt_sha256": "..."
  },
  "settings": {
    "learner_level": "N3",
    "include_unknown": true,
    "max_examples": 3,
    "jlpt_dataset": "name@version"
  },
  "entries": []
}
```

每个 entry 包含 `lemma`、`reading`、`surface_forms`、`part_of_speech`、`jlpt_level`、`is_proper_noun`、`meaning_zh`、`note_zh`、`occurrence_count` 和 `examples`。

### `xxx.vocab.md`

Markdown 面向直接阅读，示例：

```markdown
## N2

### 見落とす（みおとす）

- 词性：动词
- 中文：看漏；忽略
- 出现：2 次
- 首次位置：00:03:18

> 書類の間違いを見落としてしまった。
>
> 我不小心漏看了文件中的错误。
```

文件顶部注明学习者等级、JLPT 数据来源版本、生成时间以及“非官方等级参考”提示。分组顺序固定为 N2、N1、未分级；组内按首次出现时间排序。没有目标词汇时仍生成合法文件，并明确写“未发现符合条件的词汇”。

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
- `max_examples` 允许 1 到 10；
- 配置非法时在预检阶段报错；
- `enabled = false` 时不加载分词器、不运行词汇阶段、不要求词表数据就绪。

## 断点续跑

只有同时满足以下条件才跳过 vocabulary 阶段：

- JSON 与 Markdown 都存在且可读；
- JSON schema 合法；
- `ja_srt_sha256` 与当前日文字幕一致；
- learner level、include_unknown、max_examples 和 JLPT 数据版本一致。

配置或源字幕变化时自动重建词表。`--force` 无条件重建。

先原子写入临时文件，再替换正式 JSON/Markdown，避免中断留下“看似存在但内容不完整”的产物。

## 报告和错误语义

报告增加 `Vocabulary` 阶段，记录目标词数量、N2/N1/未分级数量、释义降级数量和耗时；产物清单包含 `.vocab.md`、`.vocab.json`。

错误分三类：

- 单词释义失败：保留词条并留空释义，阶段完成但带 warning；
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
