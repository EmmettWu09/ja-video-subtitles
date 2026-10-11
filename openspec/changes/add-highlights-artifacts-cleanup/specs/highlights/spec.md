# Spec: highlights

## ADDED Requirements

### Requirement: 高光产物回收

`[highlights] keep_artifacts`（仅接受布尔值，默认 false，无对应 CLI 参数）控制高光全部成功后的产物保留策略。`keep_artifacts` 为 false 时，高光流水线全部成功（精华视频 `<out>/<stem>/<stem>.highlights.mp4` 渲染完成）后 SHALL 删除整个 `<out>/<stem>/highlights/` 目录（含课堂总结、回看目录、独立切片、配套 SRT、分析 JSON、计划 JSON、`state.json` 与 `report.json`），只保留与烧录成片并排的 `<stem>.highlights.mp4`。精华未完成（essence_incomplete，如配音或渲染失败但独立切片已成功）或高光流水线任一阶段失败时 SHALL NOT 回收，SHALL 保留 `highlights/` 目录全部内容用于断点续跑与排查。`keep_artifacts` 为 true 时 SHALL 保持完整保留行为，不删除任何高光产物。回收 SHALL NOT 删除或修改按视频产物目录中的其他产物（字幕、成片、MP3）。回收后 `state.json` 不复存在，重跑该视频时高光阶段 SHALL 按既有缓存规则视为无可用缓存，从头重新分析。

#### Scenario: 默认成功后回收

- **WHEN** 配置未设置 `highlights.keep_artifacts`（默认 false），高光启用且全部阶段成功，精华视频渲染完成
- **THEN** `<out>/<stem>/highlights/` 目录被整体删除，仅保留 `<out>/<stem>/<stem>.highlights.mp4`，其余字幕、成片与 MP3 产物不受影响

#### Scenario: 精华未完成时保留目录

- **WHEN** `keep_artifacts` 为 false，独立切片已导出但精华版配音或合成失败（essence_incomplete）
- **THEN** `<out>/<stem>/highlights/` 目录完整保留，可用于断点续跑与排查，不发生任何回收

#### Scenario: keep_artifacts 开启时完整保留

- **WHEN** 配置 `highlights.keep_artifacts=true`，高光启用且全部阶段成功
- **THEN** `<out>/<stem>/highlights/` 中的课堂总结、回看目录、切片、配套 SRT、分析 JSON、`state.json` 等全部产物完整保留，与回收前行为一致
