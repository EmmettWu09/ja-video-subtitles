# Spec: burning

## MODIFIED Requirements

### Requirement: 双语字幕合成

SHALL 按 index 对齐 `xxx.ja.srt` 与 `xxx.zh.srt`，在 `-o` 输出目录生成 `xxx.bilingual.srt`：每条字幕两行，上行日文原文、下行中文译文，时间轴沿用转写结果。中文缺失的条目 SHALL 仅保留日文行，不阻塞合成。`run` 仅在已有双语字幕可解析、非空，且每条字幕的 index、时间轴和内容与当前日文/中文字幕的合成结果一致时 SHALL 复用该文件；源字幕改变或缓存不一致时 SHALL 重新合成后再烧录。独立 `burn` SHALL 继续直接读取所选 SRT，不执行合成或修改字幕。

#### Scenario: 正常合成

- **WHEN** ja/zh 两个字幕文件条数一致
- **THEN** 输出目录生成条数相同的 `xxx.bilingual.srt`，每条两行

#### Scenario: 修改中文译文后重跑

- **WHEN** 用户编辑现有 `xxx.zh.srt` 后再次执行 `run` 并确认覆盖成片，旧 `xxx.bilingual.srt` 仍可解析但包含修改前译文
- **THEN** 保留用户编辑的中文字幕，刷新词汇语境（若启用），重新生成双语字幕，再把当前译文烧录进成片

#### Scenario: 修改日文或时间轴后重跑

- **WHEN** 当前日文字幕内容、index 或时间轴已改变，既有双语字幕与当前合成结果不一致
- **THEN** `run` 不复用旧双语字幕，按当前日文时间轴和匹配的中文重新合成
