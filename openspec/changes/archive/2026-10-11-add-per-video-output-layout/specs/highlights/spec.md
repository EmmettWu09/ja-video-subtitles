# Spec: highlights

## MODIFIED Requirements

### Requirement: 高光产物布局

`run` 在最终有效高光开关为 true 时 SHALL 执行高光阶段。精华视频 SHALL 输出为 `<out>/<stem>/<stem>.highlights.mp4`，与烧录成片 `<stem>.mp4` 并排放置在按视频产物目录根部，SHALL NOT 放在 highlights 子目录内。其余高光产物 SHALL 写入 `<out>/<stem>/highlights/`：课堂总结 `summary.md`、回看目录 `index.html`、独立切片 `clips/<stem>.clip-NNN.mp4`、配套 SRT（`subtitles/<stem>.highlights.srt`、`subtitles/clips/<stem>.clip-NNN.srt`）、`analysis/transcript.json`、`analysis/candidates.json`、`plans/clips.json`、`plans/highlights.json`、阶段状态 `state.json` 与检查报告 `report.json`。切片与 SRT 文件名 SHALL 包含原始视频主干名，使文件脱离目录上下文仍可归属源视频。`index.html` 中的精华视频链接 SHALL 指向上移后的 `../<stem>.highlights.mp4`。SHALL NOT 在按视频产物目录之外写入高光产物，SHALL NOT 修改源视频。最终有效高光开关为 false 时 SHALL NOT 创建 highlights 目录或生成任何高光产物。`burn` SHALL NOT 生成高光产物。

#### Scenario: 默认生成高光

- **WHEN** 执行 `run lesson.mp4 -o out`，未提供高光开关且配置未设置 `highlights.enabled`，全部阶段成功
- **THEN** `out/lesson/lesson.highlights.mp4` 与 `out/lesson/lesson.mp4` 并排存在，`out/lesson/highlights/` 包含课堂总结、回看目录、切片、配套 SRT、分析与计划 JSON

#### Scenario: 关闭高光

- **WHEN** 执行 `run lesson.mp4 -o out --no-highlights`，或配置 `highlights.enabled=false` 且无 CLI 覆盖
- **THEN** 不创建 `out/lesson/highlights/`、不生成 `lesson.highlights.mp4`，其余字幕、成片与 MP3 产物正常生成

#### Scenario: 批量高光产物隔离

- **WHEN** 执行 `run ./videos -o out`，目录含 `a.mp4` 与 `b.mov` 且高光启用
- **THEN** 高光产物分别写入 `out/a/` 与 `out/b/`，切片文件名分别以 `a.`、`b.` 开头，互不覆盖

#### Scenario: 切片归属可识别

- **WHEN** 用户把某个切片文件单独复制到其他位置
- **THEN** 文件名 `<stem>.clip-NNN.mp4` 仍能表明其来源视频

### Requirement: 高光阶段非阻塞

高光阶段是学习辅助阶段。阶段级异常 SHALL 被记录，但 SHALL NOT 阻止当前视频其余产物生效，也 SHALL NOT 中断批次处理其余视频；此时视频状态 SHALL 为 `partial`，报告 SHALL 包含错误原因。精华版合成失败而独立切片已完成时，切片与分析产物 SHALL 保留并在报告与回看目录中标注精华版未完成。

#### Scenario: 高光失败保留字幕成片

- **WHEN** 字幕成片与 MP3 已生成，但高光阶段因模型持续失败而终止
- **THEN** 视频标记 partial、记录高光错误，`<stem>.mp4` 等主产物保留，批次继续

#### Scenario: 精华失败保留切片

- **WHEN** 独立切片全部导出成功，但精华版配音或合成失败
- **THEN** 切片、SRT 与分析产物保留，回看目录与报告标注精华版未完成及原因
