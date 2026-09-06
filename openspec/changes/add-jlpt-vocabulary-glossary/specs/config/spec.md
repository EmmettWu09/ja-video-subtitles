# Spec: config

## MODIFIED Requirements

### Requirement: 配置文件

配置文件 SHALL 从项目根目录（包所在位置）的 `config.toml` 读取，与用户执行命令时的当前目录无关。除既有 DeepSeek、ASR、prompt、字幕样式和视频码率配置外，新增 `[vocabulary]`：`enabled` 默认 true、`learner_level` 默认 `N3`、`include_unknown` 默认 true、`max_examples` 默认 3。`learner_level` SHALL 仅接受 N5/N4/N3/N2/N1，`max_examples` SHALL 在 1 到 10 之间。

#### Scenario: 未配置 vocabulary

- **WHEN** config.toml 没有 `[vocabulary]`
- **THEN** 使用 enabled=true、learner_level=N3、include_unknown=true、max_examples=3

#### Scenario: 非法学习者等级

- **WHEN** learner_level 不是 N5/N4/N3/N2/N1，或 max_examples 超出范围
- **THEN** 预检失败并给出合法取值，不开始处理视频

#### Scenario: 禁用词汇功能

- **WHEN** vocabulary.enabled 为 false
- **THEN** 不运行词汇阶段，也不要求形态分析词典和 JLPT 数据就绪
