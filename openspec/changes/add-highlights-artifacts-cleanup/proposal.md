# Proposal: add-highlights-artifacts-cleanup

## Why

高光阶段默认成功后会在 `<out>/<stem>/highlights/` 留下课堂总结、回看目录、独立切片、配套 SRT、分析 JSON、计划 JSON、`state.json` 等大量中间产物。对学习者的日常交付而言，真正需要的只是与成片并排的 `<stem>.highlights.mp4`；其余产物占用磁盘（切片视频尤其大）且干扰查看。但调试高光质量、断点续跑时又需要完整产物。需要一个配置开关在「默认清爽交付」与「保留全部产物」之间切换。

## What Changes

- 新增 `[highlights] keep_artifacts` 配置，仅接受布尔值，默认 false；无对应 CLI 参数（config-only，类似翻译 prompt 模板）。
- 默认（false）：高光流水线全部成功（精华视频渲染完成）后，SHALL 删除整个 `<out>/<stem>/highlights/` 目录，只保留与成片并排的 `<stem>.highlights.mp4`。
- 精华未完成（essence_incomplete，如 TTS/渲染失败但切片成功）或流水线阶段失败时，SHALL 保留 `highlights/` 目录用于断点续跑与排查。
- `keep_artifacts = true`：保持现有行为，完整保留总结、回看目录、切片、分析 JSON、`state.json` 等全部产物。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `config`: `[highlights]` 新增 `keep_artifacts` 键的默认值、布尔校验与默认场景。
- `highlights`: 新增高光产物回收 Requirement，定义默认回收、失败保留与 keep_artifacts=true 完整保留三种行为。

## Impact

- 影响 `config.py`（默认值与校验）、高光包（成功后清理逻辑）及相应测试；无新外部依赖，无 CLI 参数变化。
- 取舍：回收后 `state.json` 一并删除，重跑该视频时高光阶段无法断点续跑，将从头重新分析并产生新的 API 调用；需要保留现场或反复调试高光时应显式设置 `keep_artifacts = true`。
- 仅在精华视频渲染完成的全部成功路径触发回收；失败与精华未完成路径行为不变（保留目录）。
