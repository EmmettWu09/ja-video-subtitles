# JLPT 词汇参考数据

`jlpt_vocab.json` 是 **yomitan-jlpt-vocab** 的精简格式转换，使用
[stephenmk/yomitan-jlpt-vocab](https://github.com/stephenmk/yomitan-jlpt-vocab/tree/b062d4e38c4bdd0950ae1d4ec55f04b176182e03)
固定提交 `b062d4e38c4bdd0950ae1d4ec55f04b176182e03`，转换版本 `v1`。
运行时完全离线，不需要另外下载词表。

## 归属及许可证

本目录的 `jlpt_vocab.json` 数据依据 **CC BY-SA 4.0** 再分发，许可证全文为
[JLPT-LICENSE.txt](JLPT-LICENSE.txt)，在线条款为
[Creative Commons Attribution-ShareAlike 4.0](https://creativecommons.org/licenses/by-sa/4.0/)。
对这个数据集的改编、再分发应保留归属、许可证和改动说明，并遵守相同方式共享条件。
这份数据许可证不声称改变项目程序代码或用户原始视频的许可证。

归属链及核验来源（2026-09-13 核验）：

- **stephenmk**：词汇拼写整理、读音匹配、JMdict 条目对应及 Yomitan 格式数据。
  [固定版本原仓库 README](https://github.com/stephenmk/yomitan-jlpt-vocab/blob/b062d4e38c4bdd0950ae1d4ec55f04b176182e03/README.md)
  和 [仓库 LICENSE](https://github.com/stephenmk/yomitan-jlpt-vocab/blob/b062d4e38c4bdd0950ae1d4ec55f04b176182e03/LICENSE.txt)
  明确标明归属和 CC BY-SA 4.0；原 README 原样保存为 `JLPT-UPSTREAM-README.md`。
- **Jonathan Waller**：来自 [JLPT Resources](https://www.tanos.co.uk/jlpt/)
  的等级参考。其本人在 [Use my data!](https://www.tanos.co.uk/jlpt/sharing/)
  明确允许非售卖数据依 Creative Commons BY 使用并要求署名；没有擅自给该声明补充版本号。
- **Electronic Dictionary Research and Development Group（EDRDG）/ JMdict**：
  上游用于核对拼写、读音的日语词典资料。JMdict 文件为 EDRDG 的财产，依据
  [EDRDG 许可证](https://www.edrdg.org/edrdg/licence.html) 使用。

## 字段转换和覆盖范围

输入为固定提交下 `yomitan-jlpt-vocab/term_meta_bank_1.json` 到
`term_meta_bank_5.json`，每条为 `[word, "freq", {reading, frequency}]`。
转换只保留 `word -> lemma`、`reading -> reading`、
`frequency.displayValue -> level`。读音先作 Unicode NFKC 再将片假名转平假名，
保留长音符号；不新增释义、词汇、等级、别名或模型推断。
条目顺序和冲突记录原样保留。

| 等级 | 上游条目数 |
| --- | ---: |
| N1 | 3,214 |
| N2 | 1,856 |
| N3 | 1,695 |
| N4 | 643 |
| N5 | 705 |
| 合计 | 8,113 |

这些是数据条目数，不能解释为官方完整词数或互不重复的基本形数量。
JLPT 等级是非官方学习参考；上游指出这些列表来自十多年前的整理，考试内容和分级
可能与之不同。新词、口语、专有名词、行业词、罕见写法可能缺失。未命中表示未分级，
不表示该词一定高于任何等级。

查询优先使用基本形和读音。如果同一对基本形/读音有多个等级，返回未分级。
只有调用方未提供读音，且基本形在该数据中对应唯一读音和唯一等级时，才允许基本形
回退。调用方提供的读音与所有数据词条不匹配时，直接返回未分级，避免把数据中缺失
的同形异音义项分到其他读音的等级；同形异音即便等级相同也不能在缺乏读音匹配时
消除歧义。这种唯一性限于本数据的覆盖范围，不能证明
真实语言里不存在其他义项或读法。

当前提取流程按词典单词处理；数据中登记的部分表达由多个形态分析 token 构成，
不会仅靠其存在就自动合并或赋予等级。已知例子 `泳ぎ方` 可能被拆为 `泳ぐ`、`方`。

## 可复现性与校验

`rebuild_jlpt.py` 固定所有输入文件的提交和 SHA-256，联网仅从该提交获取数据；
不会跟随 `main` 更新。每个上游输入哈希也写在 JSON 的 `upstream_sha256`。

```bash
python ja_video_subtitles/data/rebuild_jlpt.py
```

也可离线重建，将固定版本的七个原文件放入一个目录，保持各自文件名：

```bash
python ja_video_subtitles/data/rebuild_jlpt.py --source-dir /path/to/upstream-files
```

`--output-dir` 可用于在临时目录比较重建结果。JSON 的 `entries_sha256` 是对
词条数组以 UTF-8、`ensure_ascii=False`、`sort_keys=True`、紧凑分隔符序列化的哈希。
加载器还校验 schema version、元信息、等级，并用代码中的独立 SHA-256 校验整个
内置 JSON（包含版本和归属）。更新数据必须显式审阅上游许可、固定提交、输入哈希、
转换版本及完整文件哈希，并重新执行测试。
