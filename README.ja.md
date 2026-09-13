# ja-video-subtitles

**日本語動画を入れると、1コマンドで「日本語＋中国語」二カ国語の焼き付き字幕付き動画が出てきます。**

パイプライン：`動画 → 日本語文字起こし(kotoba-whisper) → 日中翻訳(DeepSeek) → 語彙表 → 二カ国語合成 → 焼き付け(ffmpeg)`

## 処理の流れ

| 段階 | 内容 | 出力 |
|---|---|---|
| 文字起こし | ローカル ASR（kotoba-whisper、CPU）：日本語音声 → タイムスタンプ付き字幕。VAD・ハルシネーション除去・句読点分割つき | `xxx.ja.srt` |
| 翻訳 | DeepSeek API で日中翻訳。バッチ処理＋文脈付き、番号照合、異常時は自動リトライ | `xxx.zh.srt` |
| 語彙表 | ローカル形態素解析・基本形への正規化・非公式 JLPT レベル判定。設定済み API で簡体字中国語の語義を生成 | `xxx.vocab.md`、`xxx.vocab.json` |
| 二カ国語合成 | 日/中を行単位で整列（上段日本語・下段中国語）。ローカル処理で一瞬 | `xxx.bilingual.srt` |
| 焼き付け | ffmpeg が字幕をフレームに描画し、VideoToolbox で再エンコード | `xxx.sub.mp4` |

文字起こし、語彙抽出・JLPT 照合、合成、焼き付けはローカルで実行します。翻訳では字幕テキストを設定済み API に送り、語義生成では重複除去した単語と日本語の例文を同じサービスへ送ります。これらの工程で音声・動画をアップロードすることはありません。既定の API モデルは `deepseek-flash` です。各段階の所要時間は `report-*.md` を参照してください。

mp4/mov 対応。単一ファイルでもフォルダ一括でも可。`burn` には複数のファイルやフォルダをまとめて指定できます。成果物はすべて `-o` ディレクトリに出力され、元の動画は変更されません。

> **`run` の入力は日本語の音声に限ります。** 文字起こしは `language="ja"` 固定（kotoba-whisper は日本語専用モデル）で、言語判定は行いません。日本語以外の音声を入れてもエラーにはならず、意味のない字幕が黙って生成されるので注意してください。`burn` は既存の SRT を使うため、文字起こしを行いません。

## 対応プラットフォーム

**macOS（Apple Silicon）専用。Windows / Linux は非対応**です。焼き付けが VideoToolbox ハードウェアエンコード・PingFang SC フォント・Homebrew の ffmpeg パスに依存するためです。非対応 OS では事前チェック時点で即エラー終了します。

## 必要なもの

| 依存 | 用途 | インストール |
|---|---|---|
| Homebrew | パッケージ管理 | `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"` |
| uv | Python 環境管理 | `brew install uv` |
| Python 3.12 | ランタイム | `uv venv` が自動で用意 |
| ffmpeg-full | 字幕焼き付け（libass） | `brew install homebrew-ffmpeg/ffmpeg/ffmpeg-full` |
| DeepSeek API キー | 日中翻訳・語義生成 | [DeepSeek プラットフォーム](https://platform.deepseek.com) |
| SudachiPy / SudachiDict-core | ローカル形態素解析 | `requirements.txt` で導入。辞書のダウンロードは約 70 MB |

字幕フォントは macOS 標準の苹方を使うため、追加インストール不要です。

## セットアップ

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp config.example.toml config.toml   # deepseek.api_key を記入
./ja-video-subtitles download                 # ASR モデルの初回ダウンロード（約 1.5GB）
```

モデルはプロジェクト内 `.cache/hf/` に保存され（`HF_HOME` で固定）、成功時に `.model-ready` マーカーが書かれます。ダウンロードは既定で `hf-mirror.com` ミラーを使用。`HF_ENDPOINT=https://huggingface.co` で変更可能です。

`burn` のみ使う場合は Python、`srt`、`tqdm`、ffmpeg があれば利用でき、設定ファイル・API キー・ASR モデル・語彙辞書は不要です。`config.toml` があれば字幕スタイルと動画ビットレートだけを読み込み、なければ既定値を使います。語彙設定は無視し、形態素解析器や JLPT データを読み込みません。

## 使い方

```bash
./ja-video-subtitles run /path/to/xxx.mp4 -o /path/to/output   # 単一ファイル
./ja-video-subtitles run /path/to/dir   -o /path/to/output     # フォルダ一括
./ja-video-subtitles run /path/to/dir   -o out -y              # 同名ファイルを自動上書き
./ja-video-subtitles run xxx.mp4 -o out --force                # 全工程をやり直し
```

### 既存字幕の焼き付けのみ

```bash
./ja-video-subtitles burn xxx.mp4 -o out                         # out/xxx.bilingual.srt を使用
./ja-video-subtitles burn xxx.mp4 -s edited.srt -o out           # 単一 SRT を指定
./ja-video-subtitles burn first.mp4 second.mov -o out            # 複数ファイル
./ja-video-subtitles burn first.mp4 second.mov --subtitle-dir subtitles -o out -y
./ja-video-subtitles burn /path/to/videos --subtitle-dir subtitles -o out
```

`burn` は既存の字幕を焼き付け、`<out>/<stem>.sub.mp4`、`run.log`、`report-*.md` を出力します。字幕ファイルは作成・変更しません。既定では `<out>/<stem>.bilingual.srt`、`--subtitle-dir` 指定時はそのフォルダの同名字幕を使います。重複を除いた動画が 1 本の場合、`-s/--subtitles` で任意の SRT ファイルを指定できます。`--subtitle-dir` との同時指定はできません。

ファイルとフォルダは混在可能です。フォルダ直下の mp4/mov をファイル名順に処理し、サブフォルダは検索しません。同じ実体パスの動画は 1 回だけ処理します。指定したフォルダのどれかに直下の mp4/mov がなければ、バッチ全体を終了します。異なる動画の拡張子を除いた名前が同じ場合（大文字・小文字を区別しない）、または出力先が元動画を上書きする場合、処理前に一括で拒否します。字幕は読み取り可能で空でない UTF-8 SRT が必要で、1 つでも欠落や破損があれば全動画の焼き付け開始前に終了します。

既存の完成動画は開始前にまとめて上書き確認し、`-y/--yes` で自動上書き、標準入力が EOF の場合はスキップします。`burn` には `--force` はありません。事前チェック後は、1 本のエンコードが失敗しても残りを処理します。終了コードは成功・スキップが `0`、焼き付け失敗があれば `1`、引数・字幕・設定・事前チェックのエラーは `2` です。API や ASR モデルの確認・読み込みは行いません。

### 全工程の成果物と動作

`run` の成果物（すべて `-o` ディレクトリ内）：`xxx.ja.srt`（日本語字幕）、`xxx.ja.json`（文字起こしの信頼度）、`xxx.zh.srt`（中国語字幕）、`xxx.vocab.md`（語彙表）、`xxx.vocab.json`（構造化語彙と再利用用メタデータ）、`xxx.bilingual.srt`（二カ国語：上段日本語・下段中国語）、`xxx.sub.mp4`（完成動画）、`report-<タイムスタンプ>.md`（実行レポート）、`run.log`（ログ）。語彙機能を無効にすると語彙ファイルは生成しません。

動作のポイント：

- 相対パスはコマンド実行時のカレントディレクトリ基準。設定ファイルとモデルキャッシュは常にプロジェクトディレクトリから読み込まれます。
- 既存の正常な中間生成物は自動スキップ（途中再開が可能）。壊れた生成物は自動でやり直します。`run` は現在の日本語・中国語字幕を合成した内容と一致する場合だけ二カ国語字幕を再利用します。どちらかを編集すれば焼き付け前に再合成します。手動編集した単独の SRT をそのまま使う場合は `burn` を使用してください。
- 同名の完成動画がある場合、処理開始前にまとめて上書き確認。焼き付け中に確認で止まることはありません。非対話環境では「上書きしない」が既定です。
- OS、Python 依存、ffmpeg+libass、config/api_key、DeepSeek 接続、モデル有無、ディスク容量、出力先の書き込み権限を事前に確認します。語彙機能が有効なら形態素解析器・ローカル辞書・JLPT データのスキーマ、版、ハッシュも検証し、不備があれば動画処理前に対処法を表示して終了します。
- 語彙工程全体の失敗後も合成・焼き付けを続け、その動画を `partial`（部分成功）、バッチの終了コードを `1` とします。その他の処理失敗は `failed`、確認時のスキップは `skipped` です。単語の語義が再試行後も取得できなければ、語義を空欄にして語彙を残し warning を記録します。これは語義生成の劣化件数として数え、工程全体の失敗とはしません。レポートには succeeded/partial/failed/skipped の件数、レベル別語数、語義劣化件数、エラー、既存成果物を記載し、API キーは含めません。
- 焼き付け中の Ctrl+C は ffmpeg を確実に終了させ、中途半端なファイルを削除します。

### 語彙設定

プロジェクト直下の `config.toml` で次の設定を省略すると、この既定値を使用します。

```toml
[vocabulary]
enabled = true
learner_level = "N3"
include_unknown = true
max_examples = 3
```

`learner_level` は N5/N4/N3/N2/N1 のいずれかです。指定レベルより難しい語だけを選ぶため、N3 なら N2/N1 が対象です。`include_unknown` は未分類の内容語を含めるかを指定し、固有名詞には別途印を付けます。未分類だから難語とは限りません。`enabled` と `include_unknown` は真偽値、`max_examples` は 1〜10 の整数です。各語には基本形、読み、出現形、回数、初出時刻、指定件数までの異なる日本語字幕と既存の中国語訳を記録します。対象語がなくても有効な空の語彙表を生成します。

レベル判定には固定版の非公式ローカル資料を使い、API はレベルを決定しません。[データ説明](ja_video_subtitles/data/README.md) に出典、ライセンス、制約を記載しています。JSON には字幕のハッシュ、設定、データ版、形態素解析の版を記録します。両方の語彙ファイルが正常でメタデータが一致するときだけ再利用し、日本語・中国語字幕、設定、データに変更があれば再生成します。`--force` は全工程をやり直します。既存の完成動画がある場合は `-y` または確認時の上書き選択も必要です。

`enabled = false` にすると語彙工程とその依存チェックを省略できます。依存やデータが壊れている場合は、固定版を再インストールし、必要に応じて同じ版の JLPT 資料を復元してください。

```bash
uv pip install --python .venv/bin/python --reinstall-package SudachiPy --reinstall-package SudachiDict-core -r requirements.txt
.venv/bin/python ja_video_subtitles/data/rebuild_jlpt.py
```

## テスト

```bash
.venv/bin/python -m unittest discover -s tests
```

オフラインのユニットテスト。モデルも API も不要です。

ffmpeg をインストール済みの Mac では、短い動画を自動生成する実際の焼き付けテストも実行できます。モデルや設定ファイルは不要です。

```bash
RUN_FFMPEG_TESTS=1 .venv/bin/python -m unittest discover -s tests
```

焼き付け専用コマンドの OpenSpec は [add-standalone-burn-command](openspec/changes/archive/2026-09-13-add-standalone-burn-command/proposal.md) を参照してください。
語彙表の OpenSpec は [add-jlpt-vocabulary-glossary](openspec/changes/archive/2026-09-13-add-jlpt-vocabulary-glossary/proposal.md) を参照してください。

## 処理時間の目安（1時間の動画、M シリーズ）

文字起こし：約 10–20 分、翻訳：約 2–5 分、焼き付け：約 5–15 分（VideoToolbox）。語彙工程は重複除去後の対象語数と API の応答時間によるため、実測値はレポートを参照してください。

## ライセンス

コードは MIT、`LICENSE` を参照してください。JLPT データの帰属とライセンスは[データ説明](ja_video_subtitles/data/README.md)に記載しています。
