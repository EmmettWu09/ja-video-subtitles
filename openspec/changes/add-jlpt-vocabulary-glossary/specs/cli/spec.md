# Spec: cli

## MODIFIED Requirements

### Requirement: 命令结构

`run` SHALL 在日文转写和中文翻译之后运行可配置的 vocabulary 阶段，再执行双语合成和烧录。vocabulary 启用时，每个视频除既有字幕和成片外 SHALL 在 `-o` 目录生成 `<stem>.vocab.md` 与 `<stem>.vocab.json`，源视频目录不得被写入。

#### Scenario: 启用词汇功能

- **WHEN** 用户执行 `ja-video-subtitles run video.mp4 -o out` 且 vocabulary.enabled 为 true
- **THEN** 输出目录包含词汇 Markdown、结构化 JSON 以及既有字幕和成片

### Requirement: 词汇阶段非阻塞

词汇阶段是学习辅助阶段。阶段级异常 SHALL 被记录，但不得阻止当前视频继续执行双语合成和烧录。此时视频状态 SHALL 为 `partial`，报告 SHALL 包含错误原因；批量任务 SHALL 继续处理其他视频。

#### Scenario: 形态分析阶段异常

- **WHEN** 日文和中文字幕已生成，但 vocabulary 阶段抛出异常
- **THEN** 系统记录词汇失败，仍生成 bilingual.srt 和 sub.mp4，并把该视频标为 partial

### Requirement: 运行报告

运行报告 SHALL 增加 Vocabulary 阶段、词汇产物以及 N2/N1/未分级/释义降级数量。汇总 SHALL 包含 succeeded、partial、failed、skipped；任何视频为 partial 或 failed 时进程 SHALL 返回退出码 1。报告仍不得包含 api_key。

#### Scenario: 部分成功

- **WHEN** 视频烧录成功但词汇阶段级失败
- **THEN** 报告列出视频成片和已有产物、词汇错误原因及 partial 状态，命令退出码为 1

### Requirement: 启动预检

当 vocabulary.enabled 为 true 时，预检 SHALL 额外验证形态分析依赖、本地形态词典、JLPT 数据及其 schema/版本元数据。任一缺失 SHALL 在处理前失败并给出修复指引；功能禁用时 SHALL 跳过这些检查。

#### Scenario: JLPT 数据缺失

- **WHEN** vocabulary 已启用但 JLPT 数据不存在或校验失败
- **THEN** 预检失败，不开始视频处理，并说明如何安装或恢复数据
