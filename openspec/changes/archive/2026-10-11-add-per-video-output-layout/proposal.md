# Proposal: add-per-video-output-layout

## Why

当前 `run` 把全部视频的字幕、成片、MP3 平铺在主输出目录，高光精华视频又藏在 `<stem>.highlights/` 子目录里，查看一个视频的产物需要在两层目录间找文件，且 `.sub.mp4`、`clip-001.mp4` 等命名与原始视频名脱节。用户需要：每个视频一个文件夹，最终精华视频与烧录成片并排放在该文件夹根部，文件名沿用原始视频名，重跑时同名直接覆盖。

## What Changes

- `run` 的按视频产物统一写入 `<out>/<stem>/`（一个视频一个文件夹，文件夹名为原始视频主干名）：
  - 烧录成片 `<stem>.sub.mp4` 改名为 `<stem>.mp4`（原始文件名；位于独立子文件夹，不与源视频冲突）。
  - `<stem>.ja.srt`、`.ja.json`、`.zh.srt`、`.bilingual.srt`、`<stem>.mp3` 一并移入该文件夹，文件名不变。
  - 精华视频从 `<stem>.highlights/highlights.mp4` 移至 `<stem>/<stem>.highlights.mp4`，与烧录成片并排放置，SHALL NOT 放在 highlights 子目录内。
  - 其余高光产物保留在 `<stem>/highlights/`（原 `<stem>.highlights/` 改名）：切片改名 `<stem>.clip-NNN.mp4`，配套 SRT 改名 `<stem>.clip-NNN.srt` 与 `<stem>.highlights.srt`；`summary.md`、`index.html`、`analysis/`、`plans/`、`state.json`、`report.json` 等内部名称不变。
- `run.log` 与 `report-<时间戳>.md` 仍为主输出目录根的批次级文件，SHALL NOT 移入视频文件夹。
- 重跑时已存在的同名产物直接覆盖（沿用既有 `-y`/`--force`/覆盖确认机制，不为了避免重名而改名）。旧版平铺布局的遗留产物不参与复用，按新布局重新生成；SHALL NOT 自动删除或迁移旧文件。
- 覆盖确认、输出冲突检查、产物复用与强制重跑、运行报告的产物清单同步更新到新路径；主干名冲突仍拒绝整批。
- `burn` 命令布局不变（仍输出 `<out>/<stem>.sub.mp4`）；词汇产物的目录与命名不变（含 `vocabulary.output_dir` 为空时回退主输出目录）。
- 更新 CLI 帮助、`config.example.toml` 注释与三语 README 的产物说明。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `cli`: `run` 产物改为按视频文件夹布局，烧录成片改用原始文件名；覆盖确认、冲突检查、复用与报告路径同步。
- `highlights`: 精华视频移至视频文件夹根部并随原始文件名命名；高光目录改名 `<stem>/highlights/`，切片与 SRT 随原始文件名命名。
- `audio-export`: MP3 输出路径改为 `<out>/<stem>/<stem>.mp3`。

## Impact

- 影响 `cli.py`、`report.py`、`audio.py`、`burn.py`、高光包（`__init__.py`/`artifacts.py`/`render.py` 等）及相应测试；`transcribe.py`、`translate.py`、`merge.py` 仅需接受按视频产物目录。
- 这是布局破坏性变更：旧输出目录中的平铺产物不再被复用，首次按新布局运行会重生成各阶段产物；旧文件保留在原处由用户自行清理。
- `burn`、词汇配置与 DeepSeek/ASR 行为不变；无新外部依赖。
