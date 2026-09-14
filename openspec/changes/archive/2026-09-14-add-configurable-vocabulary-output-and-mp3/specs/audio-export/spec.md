# Spec: audio-export

## ADDED Requirements

### Requirement: 源视频 MP3 导出

`run` SHALL 在字幕成片成功生成后，通过本地 ffmpeg 将源视频的第一条音轨导出为可播放的 MP3，路径为 `<output-dir>/<stem>.mp3`，其中 output-dir 是 `-o/--output-dir`。该路径 SHALL 与 `<stem>.sub.mp4` 同目录，不受词汇目录和格式设置影响。系统 SHALL NOT 上传音视频。独立 `burn` SHALL NOT 导出 MP3。

#### Scenario: 完整运行导出音频

- **WHEN** 用户执行 `run lesson.mp4 -o media --vocab-output-dir words --vocab-format md` 且全部阶段成功
- **THEN** `media` 中同时生成 `lesson.sub.mp4` 和 `lesson.mp3`，`words` 中只生成 `lesson.vocab.md`

#### Scenario: 多音轨输入

- **WHEN** 源视频含多条音轨
- **THEN** MP3 包含源视频第一条音轨的音频，不混合其他音轨

#### Scenario: 独立烧录

- **WHEN** 用户执行 `burn lesson.mp4 -s lesson.srt -o media`
- **THEN** 只执行原有烧录流程，不生成或覆盖 `lesson.mp3`

### Requirement: MP3 原子写入和清理

音频导出 SHALL 先写入目标目录中的临时文件，仅当 ffmpeg 成功退出后，才原子替换正式 MP3。导出失败或被中断时 SHALL 终止仍运行的子进程并清理临时文件，SHALL NOT 删除或破坏此前存在的正式 MP3。

#### Scenario: 成功覆盖已有音频

- **WHEN** 已有 MP3 且覆盖已在运行开始前获准，新音频导出成功
- **THEN** 完整新 MP3 原子替换旧文件，目标目录不残留本次临时文件

#### Scenario: 编码失败

- **WHEN** ffmpeg 返回非零退出码
- **THEN** 音频阶段失败，清理临时文件，保留旧 MP3 或保持正式路径不存在

#### Scenario: 导出中断

- **WHEN** 用户在导出 MP3 时按 Ctrl+C
- **THEN** ffmpeg 被终止，临时文件被清理，已有正式 MP3 不变

### Requirement: 音频失败非阻塞

当成片已生成但 MP3 导出失败时，`run` SHALL 保留成片和其他成功产物，记录音频失败原因，将该视频标记为 `partial` 并继续处理批次中的后续视频。批次最终退出码 SHALL 为 1。词汇阶段失败但成片成功时 SHALL 仍尝试导出 MP3。

#### Scenario: 视频没有音轨

- **WHEN** 前置字幕可用且烧录成功，但源视频没有可导出的音轨
- **THEN** MP3 导出报告清晰错误，成片保留，该视频为 partial，后续视频继续

#### Scenario: 词汇阶段失败

- **WHEN** 词汇阶段失败但双语合成和烧录成功
- **THEN** 仍导出 MP3，报告保留词汇错误及 partial 状态，并列出成功的成片和音频
