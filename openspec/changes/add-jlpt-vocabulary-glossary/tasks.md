# Tasks: add-jlpt-vocabulary-glossary

> 本 change 已于 2026-09-06 确认，以下实施任务尚未开始。

## 1. 数据与依赖

- [ ] 1.1 选择并审核 JLPT 词汇数据的准确性、版本固定方式和再分发许可证，记录来源与已知限制
- [ ] 1.2 验证 `SudachiPy` + `SudachiDict-core` 在 Python 3.12 / Apple Silicon 上安装和基本形、读音、词性输出
- [ ] 1.3 更新 `requirements.txt`，加入形态分析依赖和兼容版本范围
- [ ] 1.4 新增 `jlpt_lexicon.py`，实现数据加载、schema 校验、版本标识和 `(lemma, reading)` 查询

## 2. 配置与预检

- [ ] 2.1 扩展 `Config` 和 `config.example.toml`：enabled、learner_level、include_unknown、max_examples
- [ ] 2.2 校验 learner_level 枚举和 max_examples 范围，错误信息给出修复方式
- [ ] 2.3 vocabulary 启用时预检形态分析器、词典和 JLPT 数据；禁用时不做这些检查

## 3. 词汇提取

- [ ] 3.1 新增 `vocabulary.py`：SRT 读取、形态分析、基本形/读音归一化和词性过滤
- [ ] 3.2 实现按学习者等级筛选、未分级与专有名词标记、同形异音保守处理
- [ ] 3.3 实现按 `(lemma, reading)` 去重、surface forms 汇总、出现次数和最多 N 条语境
- [ ] 3.4 实现 DeepSeek 结构化释义请求、ID 校验、重试/拆半和单词级降级

## 4. 产物与断点续跑

- [ ] 4.1 定义并验证 vocabulary JSON schema，写入字幕哈希、配置和数据版本元数据
- [ ] 4.2 从 JSON 确定性生成 Markdown，按 N2、N1、未分级分组及首次时间排序
- [ ] 4.3 使用同目录临时文件和原子替换写产物，中断时不保留不完整正式文件
- [ ] 4.4 实现 vocabulary 产物有效性与 freshness 检查；接入 `--force`

## 5. CLI 与报告

- [ ] 5.1 在 translate 后接入 vocabulary，阶段失败时继续 merge/burn
- [ ] 5.2 扩展 VideoRecord/Reporter，支持 partial 状态、词汇阶段统计和新产物清单
- [ ] 5.3 汇总打印 succeeded/partial/failed/skipped；partial 或 failed 时退出码为 1
- [ ] 5.4 更新 run.log 输出以及英文、中文、日文 README 的流程、配置、产物和隐私说明

## 6. 验证

- [ ] 6.1 添加离线单测：归一化、过滤、等级阈值、未知词、去重、语境、排序
- [ ] 6.2 添加 API stub 单测：成功、格式异常、漏项、重试、拆半和降级
- [ ] 6.3 添加断点续跑测试：字幕哈希/配置/数据版本变化与 `--force`
- [ ] 6.4 添加流水线测试：空词表及 vocabulary 失败仍能生成双语字幕和成片
- [ ] 6.5 用至少一段真实日语视频人工抽查基本形、读音、JLPT 等级、中文释义与时间戳
