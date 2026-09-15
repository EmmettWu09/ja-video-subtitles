# Proposal: document-vocabulary-config-fallback

## Why

用户希望直接在 `config.toml` 设置词汇格式和目录，省略命令行词汇参数时自动使用配置，默认同时输出 Markdown、JSON，并与生成的 MP4 同目录。上一轮已经实现配置读取与覆盖逻辑，但本机既有配置未显式列出两个新字段，文档也需要明确两个参数分别回退的行为。

## What Changes

- 在本机既有 `[vocabulary]` 中补齐缺失的 `output_dir = ""`、`format = "both"`，保留其余配置；该含密钥文件继续由 Git 忽略。
- 明确两个选项独立按「显式 CLI 参数、对应配置值、内置默认值」解析；目录默认是生成的 `<stem>.sub.mp4` 所在 `-o` 目录。
- 改善示例配置、CLI 帮助和三种语言 README，说明不传参数和只传一个参数时的行为。
- 添加配置回退回归测试，复用既有实现，无需改变输出格式或生成流程。
- 按用户后续要求核查项目 Python 模块注释，补充关键函数契约与缓存、失败处理等说明；不改变运行逻辑。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `config`: 明确词汇输出配置回退及各参数独立覆盖的场景。

## Impact

影响配置示例、CLI 帮助、README、配置测试及项目 Python 模块的注释和 docstring。无新增依赖，不改变默认输出、API 调用、字幕/MP3 路径或独立 `burn` 行为。
