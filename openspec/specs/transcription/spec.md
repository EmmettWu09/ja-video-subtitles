# transcription Specification

## Purpose
TBD - created by archiving change add-video-subtitle-pipeline. Update Purpose after archive.
## Requirements
### Requirement: 日文转写
SHALL 使用 faster-whisper 加载日文专用模型 `kotoba-tech/kotoba-whisper-v2.0-faster`（允许 config 覆盖模型 ID），以 `language="ja"` 转写输入视频，在 `-o` 输出目录生成与视频同主名的 `xxx.ja.srt`，并同时输出含每条置信度（avg_logprob、no_speech_prob）的 `xxx.ja.json` 供排查。

#### Scenario: 转写成功
- **WHEN** 输入 1 小时日文视频
- **THEN** 输出目录生成带准确时间轴的 `xxx.ja.srt` 与 `xxx.ja.json`，终端显示转写进度条

### Requirement: 幻觉过滤
SHALL 启用 VAD 过滤与 `condition_on_previous_text=False`，并对转写结果应用规则过滤：高 no_speech_prob 且低 avg_logprob 的片段丢弃；与上一条文本完全重复的片段丢弃。被过滤的条数 SHALL 打印到终端。

#### Scenario: BGM 片段
- **WHEN** 视频含长时间无人声的 BGM 片段
- **THEN** 该片段不产生虚构字幕，终端打印过滤条数

### Requirement: 模型本地就绪
ASR 模型 SHALL 缓存于项目内 `.cache/hf`（通过 HF_HOME 指定），由 `ja-video-subtitles download` 显式下载；转写阶段 SHALL NOT 触发模型下载，模型未就绪时该阶段不可达（已被预检拦截）。模型实例 SHALL 按模型 ID 缓存复用，批量处理多个视频时只加载一次。

#### Scenario: 模型已就绪
- **WHEN** 用户已通过 `ja-video-subtitles download` 下载模型
- **THEN** 转写直接加载本地缓存，不产生任何网络下载

### Requirement: 字幕分段
转写结果 SHALL 按句末标点（。！？!?）拆分为适合屏幕阅读的字幕条目，时间戳按字符占比线性分配；无标点且超过 2 倍单条上限的文本 SHALL 按字数硬拆。不得出现整段多句糊在同一时间轴上的字幕。

#### Scenario: 长段落拆分
- **WHEN** 某段转写结果含多个句子、时长超过 10 秒
- **THEN** 拆分为多条字幕，时间戳连续且不越界，画面同一时刻只出现一句话

