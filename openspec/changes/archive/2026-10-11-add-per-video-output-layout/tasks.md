# Tasks: add-per-video-output-layout

## 1. 路径推导与流水线接线

- [x] 1.1 `cmd_run` 为每个视频推导 `video_dir = out_dir / video.stem`，处理前创建并检查可写；`process_video` 及转写、翻译、双语合成、烧录、MP3 各阶段改用该目录
- [x] 1.2 烧录成片改名 `<video_dir>/<stem>.mp4`；MP3、ja/zh/bilingual SRT、ja.json 同步移入
- [x] 1.3 `check_run_targets` 与 `confirm_overwrites` 更新为新路径（成片、MP3、精华视频），保留冲突拒绝与确认语义

## 2. 高光布局调整

- [x] 2.1 `generate()` 接收视频产物目录，高光目录改为 `<video_dir>/highlights/`，精华视频输出 `<video_dir>/<stem>.highlights.mp4`
- [x] 2.2 切片与 SRT 改名 `<stem>.clip-NNN.mp4`、`subtitles/clips/<stem>.clip-NNN.srt`、`subtitles/<stem>.highlights.srt`；`index.html` 精华链接指向 `../<stem>.highlights.mp4`
- [x] 2.3 断点恢复、缓存键、原子写入与失败清理在新路径下验证

## 3. 报告与文档

- [x] 3.1 运行报告产物清单按新布局列出（成片、MP3、精华视频及高光目录），阶段记录不变
- [x] 3.2 更新 CLI 帮助、`config.example.toml` 注释与三语 README 的产物结构与文件名说明

## 4. 验证

- [x] 4.1 更新并运行离线回归测试（配置、CLI、报告、高光单元）与集成测试（新布局端到端、覆盖、断点复用）
- [x] 4.2 验证 `burn` 布局与词汇产物不变；旧平铺产物不参与复用
- [x] 4.3 运行 OpenSpec strict 校验，复查规格、实现与用户文档一致性
