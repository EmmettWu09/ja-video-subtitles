# Validation: document-vocabulary-config-fallback

验证日期：2026-09-15。

- 配置专项测试：`.venv/bin/python -m unittest discover -s tests -p test_vocabulary_config.py -v`，27 项通过；新增 4 项使用真实临时 TOML 的回退测试。
- 提交前全套回归：`RUN_FFMPEG_TESTS=1 .venv/bin/python -m unittest discover -s tests`，139 项通过，6.423 秒，无跳过；包含真实 ffmpeg 合成媒体验证，无真实 API 或模型推理。
- `run --help` 已显示词汇参数先读取 config.toml、再采用内置默认值的规则。
- 本机 config.toml 已补齐 `output_dir = ""`、`format = "both"`，通过真实配置加载确认格式为 both、路径跟随 `-o`；写入前后校验其他配置值一致。该文件仍被 Git 忽略。
- OpenSpec `validate document-vocabulary-config-fallback --strict --no-interactive` 通过，`git diff --check` 通过。

## 项目注释核查

覆盖 `ja_video_subtitles` 下全部 16 个 Python 源模块，包括数据重建脚本。所有模块都有说明；补充关键函数的输入输出契约、配置回退、缓存新鲜度、词义降级、批次失败、成片覆盖与 MP3 原子替换等注释，纠正模型就绪检查和 HF_HOME 环境变量行为的说明。

注释核查前后，移除模块、类和函数 docstring 后比较 Python AST：16 个模块全部一致，确认此次注释调整没有改变运行逻辑。测试通过使用场景名称和断言记录行为，不对简单语句添加逐行注释。

## 归档

2026-09-15 使用 OpenSpec `archive document-vocabulary-config-fallback --yes` 完成归档，目录为 `openspec/changes/archive/2026-09-15-document-vocabulary-config-fallback/`；`config` 主规格已同步新增「词汇输出配置回退」要求。归档后 `validate --all --strict --no-interactive` 通过。

本次复用已实现的配置读取和覆盖逻辑，补齐本机配置、说明、项目关键注释与回归测试。
