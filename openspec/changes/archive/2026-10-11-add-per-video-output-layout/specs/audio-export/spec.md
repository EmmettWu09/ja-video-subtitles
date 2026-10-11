# Spec: audio-export

## MODIFIED Requirements

### Requirement: 源视频 MP3 导出

`run` SHALL 在字幕成片成功生成后，通过本地 ffmpeg 将源视频的第一条音轨导出为可播放的 MP3，路径为 `<output-dir>/<stem>/<stem>.mp3`，即与烧录成片 `<stem>.mp4` 相同的按视频产物目录，不受词汇目录和格式设置影响。系统 SHALL NOT 上传音视频。独立 `burn` SHALL NOT 导出 MP3。

#### Scenario: 完整运行导出音频

- **WHEN** 用户执行 `run lesson.mp4 -o media --vocab-output-dir words --vocab-format md` 且全部阶段成功
- **THEN** `media/lesson/` 中同时生成 `lesson.mp4` 和 `lesson.mp3`，`words` 中只生成 `lesson.vocab.md`

#### Scenario: 多音轨输入

- **WHEN** 源视频含多条音轨
- **THEN** MP3 包含源视频第一条音轨的音频，不混合其他音轨

#### Scenario: 独立烧录

- **WHEN** 用户执行 `burn lesson.mp4 -s lesson.srt -o media`
- **THEN** 只执行原有烧录流程，不生成或覆盖 `lesson.mp3`
