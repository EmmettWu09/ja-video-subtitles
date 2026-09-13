# Tasks: add-standalone-burn-command

## 1. OpenSpec 与接口

- [x] 1.1 定义单文件、多文件、文件夹输入及字幕映射方式，完成 proposal、design 与 cli/burning/config delta specs
- [x] 1.2 新增 `burn` 参数解析，保持现有 `run` 和 `download` 接口不变

## 2. 预检与安全

- [x] 2.1 实现有序目录展开、源路径去重、同主干冲突及输出覆盖任一源文件的保护
- [x] 2.2 实现显式/目录/默认字幕映射，在任何烧录前验证整批 SRT 可读、有效且非空
- [x] 2.3 提供不要求配置文件或 API key 的烧录配置加载，仍应用样式和码率覆盖
- [x] 2.4 提供烧录专用预检，仅检查平台、烧录依赖、磁盘空间及输出目录

## 3. 执行与用户反馈

- [x] 3.1 复用统一覆盖确认与串行烧录，支持 `-y`、EOF 跳过、失败继续和退出码
- [x] 3.2 复用日志与报告，明确 burn-only / N/A 字段和实际字幕来源
- [x] 3.3 更新英文、中文、日文 README，覆盖单文件、多文件、文件夹与独立烧录依赖
- [x] 3.4 修复共用烧录路径的 ffmpeg 两层转义，支持空格、中日韩字符、单引号、方括号、冒号和反斜杠

## 4. 验证

- [x] 4.1 添加离线测试覆盖参数、输入展开/去重、字幕映射、整批校验及源文件保护
- [x] 4.2 添加离线测试覆盖独立配置/预检、覆盖确认、失败继续、退出码及报告
- [x] 4.3 运行完整离线测试，确认现有 `run` 行为无回归
- [x] 4.4 在本机使用小样本完成单文件及多文件实际 ffmpeg 烧录检查
- [x] 4.5 验证 OpenSpec change 结构与场景完整性
- [x] 4.6 添加路径特殊字符转义测试，并使用真实 ffmpeg 验证相应字幕路径的烧录

## 验证记录（2026-09-13）

- `RUN_FFMPEG_TESTS=1 .venv/bin/python -m unittest discover -s tests`：46 项测试全部通过，含既有流水线回归与真实 ffmpeg 集成测试。
- 真实烧录覆盖单文件、多文件（去重）、目录批量、显式字幕、默认字幕匹配、独立字幕目录及特殊字符路径；在无配置和模型的代码副本中执行。
- ffprobe 确认成片含 H.264 视频和 AAC 音频、时长正常；画面像素验证字幕可见，另人工查看抽帧确认日中字幕；源视频与字幕哈希未变化。
- `OPENSPEC_TELEMETRY=0 npm exec --yes --package=@fission-ai/openspec -- openspec validate add-standalone-burn-command --strict --no-interactive`：通过。
- `git diff --check`：通过。
