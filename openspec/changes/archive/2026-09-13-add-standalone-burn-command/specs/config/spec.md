# Spec: config

## MODIFIED Requirements

### Requirement: 配置文件

配置文件 SHALL 从项目根目录（包所在位置）的 `config.toml` 读取，与命令执行时的当前目录无关。配置项包含 DeepSeek `base_url`（默认 `https://api.deepseek.com`）、`api_key`（无默认值）、`model`（默认 `deepseek-flash`），有内置默认值的翻译 prompt 模板、烧录字幕样式及 `[video] bitrate`（默认 `8M`）。`run` SHALL 要求配置文件存在且 api_key 有效。`burn` SHALL 允许配置文件不存在或缺少/留空 api_key：不存在时使用默认烧录样式和码率，存在时应用烧录相关覆盖项，SHALL NOT 验证或使用翻译 API 配置。无法解析的 TOML 或非法烧录配置 SHALL 在处理前报错。

#### Scenario: 正常加载

- **WHEN** config.toml 存在且字段合法
- **THEN** 使用配置值，未配置字段回退到内置默认值

#### Scenario: 配置缺失

- **WHEN** 执行 `run`，config.toml 不存在或 api_key 为空/仍为占位符
- **THEN** 预检失败，提示参照 config.example.toml 创建配置，退出码非零

#### Scenario: 独立烧录无配置

- **WHEN** 执行 `burn` 且 config.toml 不存在
- **THEN** 使用默认字幕样式和 `8M` 码率，无需创建配置文件

#### Scenario: 独立烧录只配置样式和码率

- **WHEN** 执行 `burn`，配置只有字幕样式与 `[video] bitrate`，没有有效 DeepSeek key
- **THEN** 应用样式和码率覆盖，不检查 API key 或 API 连通性

#### Scenario: 独立烧录配置损坏

- **WHEN** `burn` 读取的 config.toml 无法解析或包含非法烧录配置
- **THEN** 打印配置错误，以退出码 2 结束，不开始任何视频烧录
