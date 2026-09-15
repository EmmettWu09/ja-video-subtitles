# Design: document-vocabulary-config-fallback

## Context

`Config` 已定义 `vocabulary_output_dir = ""` 和 `vocabulary_format = "both"`。`load()` 从 `[vocabulary] output_dir`、`format` 读取配置；argparse 对省略的词汇选项保留 `None`；预检仅覆盖非 `None` 的 CLI 值。现有逻辑已经满足本次请求，缺口是既有本机配置的可发现性和省略参数场景的明确验证。

## Goals / Non-Goals

- 让用户能够编辑配置后运行 `run video.mp4 -o out`，无需重复传词汇参数。
- 保证格式和目录分别覆盖，不因只指定一个 CLI 参数而重置另一个配置。
- 默认同时输出两种词表，目录与生成的 `.sub.mp4` 一致。
- 不新增配置别名、源视频目录默认规则或自动迁移用户配置的运行时代码。

## Decisions

沿用 `[vocabulary]` 名称及 `output_dir`、`format` 字段，不增加重复的 `[vocab]`。空目录使用 `-o`；显式相对目录继续以命令执行时的 cwd 为基准。

本机配置只补缺失字段，并在写入前用 TOML 解析确认其他设置不变。示例配置及 README 显式说明默认值与对应 CLI 参数。CLI 帮助说明省略参数时先读取配置，而不是无条件采用内置默认值。

验证使用真实配置解析、替代外部依赖的预检测试覆盖：省略两个参数、仅覆盖格式、仅覆盖目录、缺失两个配置字段。无需真实 API 或模型推理。

项目注释核查覆盖全部 Python 源模块，补充关键入口、返回值约定、缓存有效性、失败降级和资源清理的说明。注释修改前后比较移除 docstring 的 Python AST，确保没有顺带修改运行逻辑；简单语句沿用可读的命名。

## Risks / Trade-offs

“MP4 同目录”可能被理解为源视频目录。本项目既有 `-o` 定义为产物目录，本次明确指生成的 `.sub.mp4` 目录。输出位置兼容既有命令。

## Migration Plan

旧配置无需迁移即可使用内置默认值；本机显式补充两个字段便于用户后续编辑。其他安装可以参照更新的示例配置填写。
