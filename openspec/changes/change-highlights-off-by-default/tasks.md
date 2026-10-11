# Tasks: change-highlights-off-by-default

## 1. 默认值翻转

- [x] 1.1 `config.py` 的 `DEFAULT_HIGHLIGHTS_ENABLED` 改为 `False`，`cli.py` 帮助文本同步
- [x] 1.2 `config.example.toml` 与三语 README 更新默认关闭说明及开启方式

## 2. 测试与验证

- [x] 2.1 更新默认值断言与默认运行场景的测试；补充默认运行不创建 highlights 目录、跳过音色预检的用例
- [x] 2.2 运行全量测试与 OpenSpec strict 校验，确认规格、实现与文档一致
