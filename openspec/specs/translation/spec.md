# translation Specification

## Purpose
使用 OpenAI 兼容翻译服务将日文字幕翻译为简体中文，保持编号对应，通过批次校验、重试及降级保障流水线持续运行。

## Requirements
### Requirement: 日译中
SHALL 通过 config 中的 OpenAI 兼容接口（默认 DeepSeek）将 `xxx.ja.srt` 翻译为简体中文，在 `-o` 输出目录生成与视频同主名的 `xxx.zh.srt`，时间轴与索引 SHALL 与原文逐条一致。

#### Scenario: 翻译成功
- **WHEN** `xxx.ja.srt` 存在且 API 可用
- **THEN** 输出目录生成条数相同、时间轴相同的 `xxx.zh.srt`，终端按批次显示进度条

### Requirement: 分批与上下文
翻译 SHALL 分批进行（每批 ≤20 条且原文合计 ≤800 字符），并在每批中附上前一批末尾 2 条原文作为仅供理解的上下文（不翻译、不输出）。

#### Scenario: 省略主语的上下文还原
- **WHEN** 某条字幕省略了主语，其指代出现在前几条
- **THEN** 模型能看到上下文，译文主语一致

### Requirement: 编号对齐与降级重试
每批输入 SHALL 带 `1..N` 编号并要求模型严格按 `编号. 译文` 输出；解析后校验编号完整。校验失败 SHALL 整批重试（最多 2 次），仍失败则拆半递归翻译；单条最终失败时保留日文原文并打印警告，不中断整体流程。

#### Scenario: 模型输出格式异常
- **WHEN** 某批响应缺少编号或条数不符
- **THEN** 自动重试/拆半，最终在日志中可见降级过程，流程不中断

### Requirement: 可配置 prompt
翻译的 system prompt 与 user prompt 模板 SHALL 有内置默认值（英文撰写，明确要求输出简体中文：口语化、每条译文 ≤24 个汉字、专有名词一致），并允许在 `config.toml` 中整体覆盖。上下文按字幕在列表中的位置取前 2 条，SHALL NOT 依赖 srt 文件的 index 编号连续。

#### Scenario: 自定义风格
- **WHEN** 用户在 config 中覆盖 system prompt
- **THEN** 翻译使用用户 prompt，默认值不再生效

