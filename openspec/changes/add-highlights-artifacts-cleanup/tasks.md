# Tasks: add-highlights-artifacts-cleanup

## 1. 配置

- [x] 1.1 `config.py` 新增 `DEFAULT_HIGHLIGHTS_KEEP_ARTIFACTS = False`，解析 `[highlights] keep_artifacts` 并做严格布尔校验
- [x] 1.2 `config.example.toml` 的 `[highlights]` 节加入 `keep_artifacts` 注释示例与默认说明

## 2. 回收逻辑

- [x] 2.1 高光流水线全部成功（精华视频渲染完成）且 `keep_artifacts=false` 时，删除整个 `<out>/<stem>/highlights/` 目录，保留 `<stem>.highlights.mp4`
- [x] 2.2 精华未完成（essence_incomplete）或高光阶段失败时跳过回收，保留 `highlights/` 目录
- [x] 2.3 `keep_artifacts=true` 时不做任何回收，完整保留全部高光产物

## 3. 验证

- [x] 3.1 补充单元与集成测试：默认回收、失败保留、keep_artifacts=true 保留、非法配置报错
- [x] 3.2 运行全量测试与 OpenSpec strict 校验，确认规格、实现与文档一致
