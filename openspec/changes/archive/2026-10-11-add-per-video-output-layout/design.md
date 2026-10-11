# Design: add-per-video-output-layout

## Context

`run` 目前把每个视频的 `ja.srt`/`zh.srt`/`bilingual.srt`/`sub.mp4`/`mp3` 平铺在主输出目录，高光产物放在 `<stem>.highlights/`，精华视频命名为通用的 `highlights.mp4`。用户测试后要求：精华视频与烧录成片放在同一文件夹、全部文件名沿用原始视频名、一个视频一个文件夹、重名直接覆盖。

## Goals / Non-Goals

**Goals:**

- 一个视频一个文件夹：`<out>/<stem>/` 收纳该视频的全部按视频产物。
- 烧录成片使用原始文件名 `<stem>.mp4`；精华视频 `<stem>.highlights.mp4` 与其并排，不进入 highlights 子目录。
- 高光其余产物集中在 `<stem>/highlights/`，切片与配套 SRT 随原始文件名命名。
- 重跑时同名产物直接覆盖（经既有覆盖确认/`-y`/`--force`），不为避免重名而改名。
- 批次级文件（`run.log`、`report-*.md`）留在主输出目录根。

**Non-Goals:**

- 不改变 `burn` 命令的输出布局（仍为 `<out>/<stem>.sub.mp4`）与字幕匹配规则。
- 不改变词汇产物的目录与命名（含 `vocabulary.output_dir` 空值回退主输出目录）。
- 不迁移、不删除旧版平铺布局的遗留产物，不提供布局迁移工具。
- 不改变转写、翻译、分析、渲染的内容与阶段顺序，仅改产物路径与文件名。

## Decisions

### 1. 按视频产物目录在 `run` 入口统一推导

`cmd_run` 在展开视频后，为每个视频定义 `video_dir = out_dir / video.stem`，并在处理前统一创建与检查可写性（沿用 `_check_output` 的探测方式）。`process_video` 内所有阶段（转写、翻译、双语合成、烧录、MP3、高光）都接收该目录作为产物根；各阶段函数签名由「out_dir」改为「按视频产物目录」，不各自拼接 `<stem>` 子目录。

选择入口统一推导而不是各阶段自建，因为覆盖确认、冲突检查、预检和报告都需要同一份路径清单，单点推导可避免不一致。

### 2. 烧录成片用原始文件名，依赖文件夹隔离冲突

`<stem>.mp4` 位于 `<out>/<stem>/`，与源视频天然不同路径；`_check_targets` 的别名检查（resolve/samefile）继续兜底源视频位于输出目录内等边界情况。重跑覆盖沿用既有机制：`yes OR force` 自动覆盖，否则处理前逐个确认；确认语义不变，仅检查路径变为 `<stem>/<stem>.mp4`、`<stem>/<stem>.mp3`、`<stem>/<stem>.highlights.mp4`。不为避免重名生成 `<stem>-1.mp4` 之类的派生名。

`.sub.mp4` 后缀原本用于在平铺目录中区分源与成片；按视频文件夹引入后该区分不再必要，且用户明确要求原始文件名。

### 3. 精华视频上移一层，高光目录改名 `highlights/`

精华视频是「最终成片」之一，与烧录成片同级放在 `<stem>/<stem>.highlights.mp4`；其余高光产物（切片、字幕、分析、计划、状态、报告、总结、回看页）留在 `<stem>/highlights/`。切片命名 `<stem>.clip-NNN.mp4`，配套 SRT 为 `subtitles/clips/<stem>.clip-NNN.srt` 与 `subtitles/<stem>.highlights.srt`，保证脱离目录上下文也能归属到源视频。`summary.md`、`index.html`、`state.json`、`report.json`、`analysis/`、`plans/`、`tts/`、`work/` 等内部名称不变，控制改动面。

高光模块的 `generate()` 接口改为接收视频产物目录（`<out>/<stem>/`），内部自行定位 `highlights/` 子目录与根部的精华视频路径；`index.html` 中的精华链接相应改为 `../<stem>.highlights.mp4`。

### 4. 旧布局产物不复用、不清理

路径变化使既有缓存键/产物探测自然失效：旧平铺目录中的 `ja.srt` 等不再被新布局发现，对应阶段重跑。不删除或搬移旧文件（用户数据，且可能正被引用）。断点恢复、原子写入、失败清理等语义在新路径下保持不变。

### 5. 词汇与 burn 显式排除

词汇产物由独立配置（用户已指向 Obsidian 目录）且命名含主干名，不参与本次布局调整；`vocabulary.output_dir` 空值仍回退 `run` 主输出目录根（不跟随视频文件夹），避免词汇文件散落多个文件夹。`burn` 无高光、无多产物组织需求，保持平铺与 `.sub.mp4` 命名，降低回归面。

## Risks / Trade-offs

- **布局破坏**：旧输出目录再跑会全量重生成。缓解：proposal 明确说明；复用逻辑不变，仅路径变化。
- **路径改动面大**：转写/翻译/合成/烧录/MP3/高光/报告/确认/冲突检查都涉及。缓解：入口单点推导 `video_dir`；测试覆盖路径断言。
- **源与成片同名混淆**：`<stem>/<stem>.mp4` 与源同名不同目录。缓解：报告与日志始终打印完整路径；别名检查兜底。
