# Tasks: add-configurable-vocabulary-output-and-mp3

## 1. 配置与 CLI

- [x] 1.1 增加 `[vocabulary] output_dir`、`format` 默认值及类型/枚举校验，更新 `config.example.toml`
- [x] 1.2 增加 `run --vocab-output-dir`、`--vocab-format`，实现命令行优先与 cwd 相对路径解析
- [x] 1.3 词汇启用时预先创建、检查有效输出目录，禁用时不触及词汇目录；保持 `burn` 隔离

## 2. 词汇产物与复用

- [x] 2.1 按 `md`、`json`、`both` 在有效词汇目录原子生成所选产物
- [x] 2.2 实现 Markdown-only 无 JSON sidecar 的新鲜度校验、JSON-only 复用及双格式一致性检查
- [x] 2.3 验证缺失/损坏/过期缓存、格式和目录切换、旧双格式缓存与 `--force`

## 3. MP3 与流水线

- [x] 3.1 从源视频第一条音轨导出 `<out>/<stem>.mp3`，实现成功退出检查与原子替换
- [x] 3.2 处理无音轨、ffmpeg 失败、中断、临时文件清理及旧 MP3 保留
- [x] 3.3 将 MP3 接入 `run`，保持与 `sub.mp4` 同目录；音频失败标记 partial 并继续批次
- [x] 3.4 在处理前统一确认已有成片和 MP3，支持 `-y`、`--force`、EOF 跳过及路径冲突校验

## 4. 报告与文档

- [x] 4.1 报告实际词汇输出目录、格式、所选路径与音频阶段/MP3；排除未选中的历史词汇文件
- [x] 4.2 更新英文、中文、日文 README 的命令示例、配置、产物、覆盖、失败与复用说明

## 5. 验证

- [x] 5.1 运行配置、CLI、词汇、报告和音频模块离线回归测试
- [x] 5.2 运行真实 ffmpeg 短视频 MP3 导出与失败保留检查
- [x] 5.3 运行 OpenSpec strict 校验，复查规格、实现和用户文档一致性
