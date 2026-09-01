# burning Specification

## Purpose
TBD - created by archiving change add-video-subtitle-pipeline. Update Purpose after archive.
## Requirements
### Requirement: 双语字幕合成
SHALL 按 index 对齐 `xxx.ja.srt` 与 `xxx.zh.srt`，在 `-o` 输出目录生成 `xxx.bilingual.srt`：每条字幕两行，上行日文原文、下行中文译文，时间轴沿用转写结果。中文缺失的条目 SHALL 仅保留日文行，不阻塞合成。

#### Scenario: 正常合成
- **WHEN** ja/zh 两个字幕文件条数一致
- **THEN** 输出目录生成条数相同的 `xxx.bilingual.srt`，每条两行

### Requirement: 烧录输出
SHALL 使用带 libass 的 ffmpeg（`subtitles` 滤镜 + `force_style`）将 `xxx.bilingual.srt` 硬烧进视频，在 `-o` 输出目录生成 `xxx.sub.mp4`；视频用 `h264_videotoolbox` 硬件编码，音频直通（`-c:a copy`）。字幕样式 SHALL 有默认值（PingFang SC、白字黑描边、底部居中）并允许 config 覆盖。烧录过程 SHALL 显示进度条。

#### Scenario: 烧录成功
- **WHEN** `xxx.bilingual.srt` 已生成且成片同名确认已通过
- **THEN** 输出目录生成可正常播放、画面含双语硬字幕的 `xxx.sub.mp4`，进度条走满

#### Scenario: ffmpeg 不支持烧录
- **WHEN** 系统内找不到带 `subtitles` 滤镜的 ffmpeg
- **THEN** 在启动预检阶段即失败退出，并提示安装方式（如 `brew install homebrew-ffmpeg/ffmpeg/ffmpeg-full`），不会在转写/翻译完成后才报错

### Requirement: 同名与安全
烧录目标 `xxx.sub.mp4` 的同名检查与用户确认 SHALL 在烧录开始前完成（见 cli 规格），烧录过程 SHALL NOT 中断等待输入；未获确认的同名成片 SHALL NOT 被覆盖。烧录只新增/覆盖输出目录中的 `xxx.sub.mp4`，SHALL NOT 修改源视频。

#### Scenario: 未确认不覆盖
- **WHEN** 用户对同名成片选择了跳过
- **THEN** 该视频的既有成片保持原样，不做任何写操作

