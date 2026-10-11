# Proposal: change-highlights-off-by-default

## Why

高光分析、配音与渲染显著增加 `run` 的处理耗时与 API 调用，且并非每次字幕处理都需要课堂高光。用户反馈默认产物里不应包含高光产物，需要显式开启才生成。现有 `[highlights] enabled` 与 `--highlights/--no-highlights` 已完整承载「是否输出高光产物」语义，无需新增同义配置键（config 规格禁止多配置来源），本次仅把默认值从 true 翻转为 false。

## What Changes

- `[highlights] enabled` 内置默认值由 true 改为 false：未配置且未传 CLI 开关时，`run` SHALL NOT 执行高光阶段、创建 highlights 目录或生成 `<stem>.highlights.mp4`，也 SHALL 跳过 `say`/音色预检。
- 显式 `highlights.enabled=true` 或 `--highlights` 仍开启高光；`--no-highlights` 行为不变。配置校验、CLI 合并顺序、覆盖确认、报告与复用规则不变。
- CLI 帮助、`config.example.toml` 与三语 README 的默认说明同步为「默认关闭，需显式开启」。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `config`: `highlights.enabled` 默认值翻转为 false，映射表与场景同步。
- `cli`: 命令结构与文档场景中「默认生成高光」改为「默认不输出高光产物」。

## Impact

- 影响 `config.py` 默认常量、`cli.py` 帮助文本、`config.example.toml`、三语 README 及相应测试。
- 行为变化：既有未显式配置的用户下次 `run` 不再生成高光产物；需要高光时设置 `highlights.enabled=true` 或传 `--highlights`。高光功能本身的实现与产物布局不变。
