# Validation: add-configurable-vocabulary-output-and-mp3

验证日期：2026-09-14。

## Implementation

- `run` 支持 `--vocab-output-dir`、`--vocab-format md|json|both` 及对应配置；默认目录跟随 `-o`，默认生成两种格式。
- 单格式产物可独立续跑。Markdown-only 的结构化缓存位于同文件 HTML 注释中，无 JSON sidecar；格式切换只更新所选文件，并优先采用同目录内较新的有效缓存。
- 完整流水线新增第一音轨 MP3，使用 `libmp3lame`、192 kb/s，与成片同目录。临时文件在 ffmpeg 成功退出后原子替换；失败和中断保留旧 MP3。
- 已有成片和音频在批次开始前处理覆盖选择；音频失败保留成片、记录 partial 和原因、继续后续视频。报告仅列实际所选词汇路径和本次成功音频。
- 英文、中文、日文 README 已同步。独立 `burn` 保持既有范围。

## Checks

执行完整离线与真实 ffmpeg 回归：

```bash
RUN_FFMPEG_TESTS=1 .venv/bin/python -m unittest discover -s tests
```

提交前重新运行结果：135 tests，6.125 秒，OK，无跳过。覆盖配置类型与枚举、CLI 优先级、独立词汇目录、三种格式、禁用词汇不创建目录、目录解析错误、缓存修复与强制重跑、报告过滤、输出冲突与覆盖确认、MP3 失败与批次继续。

真实媒体测试使用临时目录中的合成短视频，包括带中文和空格的词汇目录，验证 H.264 字幕成片、MP3 编码与纯音频流、时长和源视频保持不变；没有音轨的失败用例验证旧 MP3 不受损。API、模型就绪与字幕转写使用替身或现成测试字幕，不调用真实付费 API、不执行 ASR 模型推理、不处理用户媒体。

`./ja-video-subtitles run --help` 和 `burn --help` 检查通过；`git diff --check` 通过。

归档前通过本机已有缓存的 OpenSpec CLI 执行：

```bash
node /Users/xudongyi/.npm/_npx/abab5bd700860149/node_modules/@fission-ai/openspec/bin/openspec.js validate add-configurable-vocabulary-output-and-mp3 --strict
```

结果：`Change 'add-configurable-vocabulary-output-and-mp3' is valid`。

## Archive

2026-09-14 使用 OpenSpec `archive add-configurable-vocabulary-output-and-mp3 --yes` 完成归档，目录为 `openspec/changes/archive/2026-09-14-add-configurable-vocabulary-output-and-mp3/`。

主规格新增 `audio-export`，同步 `cli`、`config`、`vocabulary`；归档前后的 `validate --all --strict --no-interactive` 均通过。中英日 README 已更新为归档链接。

本次验证不包含真实用户视频的完整 ASR/API 流水线运行。
