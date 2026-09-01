# Spec: config

## ADDED Requirements

### Requirement: 配置文件
配置文件 SHALL 从项目根目录（包所在位置）的 `config.toml` 读取，与用户执行命令时的当前目录无关。配置项包含：DeepSeek 的 `base_url`（默认 `https://api.deepseek.com`）、`api_key`（无默认值）、`model`（默认 `deepseek-chat`），翻译用的 system prompt 与 user prompt 模板（均有内置默认值，可覆盖），烧录字幕样式（字体、字号等，可覆盖），以及烧录视频码率 `[video] bitrate`（默认 `8M`，4K 源可调高）。

#### Scenario: 正常加载
- **WHEN** `config.toml` 存在且字段齐全
- **THEN** 使用配置值；未配置的字段回退到内置默认值

#### Scenario: 配置缺失
- **WHEN** `config.toml` 不存在，或 `api_key` 为空/仍为占位符
- **THEN** 预检失败，提示参照 `config.example.toml` 创建配置，退出码非零

### Requirement: 模板与密钥隔离
仓库 SHALL 提供 `config.example.toml` 模板入库；`config.toml` 真实密钥文件 SHALL 被 `.gitignore` 排除，不得入库。

#### Scenario: 首次配置
- **WHEN** 用户首次使用
- **THEN** 可复制 `config.example.toml` 为 `config.toml`，仅需填入 api_key 即可运行
