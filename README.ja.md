# ja-video-subtitles

**日本語動画を入れると、1コマンドで「日本語＋中国語」二カ国語の焼き付き字幕付き動画が出てきます。**

パイプライン：`動画 → 日本語文字起こし(kotoba-whisper) → 日中翻訳(DeepSeek) → 二カ国語合成 → 焼き付け(ffmpeg)`

## 処理の流れ

| 段階 | 内容 | 出力 |
|---|---|---|
| 文字起こし | ローカル ASR（kotoba-whisper、CPU）：日本語音声 → タイムスタンプ付き字幕。VAD・ハルシネーション除去・句読点分割つき | `xxx.ja.srt` |
| 翻訳 | DeepSeek API で日中翻訳。バッチ処理＋文脈付き、番号照合、異常時は自動リトライ | `xxx.zh.srt` |
| 二カ国語合成 | 日/中を行単位で整列（上段日本語・下段中国語）。ローカル処理で一瞬 | `xxx.bilingual.srt` |
| 焼き付け | ffmpeg が字幕をフレームに描画し、VideoToolbox で再エンコード | `xxx.sub.mp4` |

文字起こしと焼き付けはマシンの性能次第、翻訳はネットワーク次第、合成は瞬時。各段階の所要時間は `report-*.md` を参照。

mp4/mov 対応。単一ファイルでもフォルダ一括でも可。成果物はすべて `-o` ディレクトリに出力され、元のディレクトリには一切書き込みません。

> **入力は日本語の音声に限ります。** 文字起こしは `language="ja"` 固定（kotoba-whisper は日本語専用モデル）で、言語判定は行いません。日本語以外の音声を入れてもエラーにはならず、意味のない字幕が黙って生成されるので注意してください。

## 対応プラットフォーム

**macOS（Apple Silicon）専用。Windows / Linux は非対応**です。焼き付けが VideoToolbox ハードウェアエンコード・PingFang SC フォント・Homebrew の ffmpeg パスに依存するためです。非対応 OS では事前チェック時点で即エラー終了します。

## 必要なもの

| 依存 | 用途 | インストール |
|---|---|---|
| Homebrew | パッケージ管理 | `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"` |
| uv | Python 環境管理 | `brew install uv` |
| Python 3.12 | ランタイム | `uv venv` が自動で用意 |
| ffmpeg-full | 字幕焼き付け（libass） | `brew install homebrew-ffmpeg/ffmpeg/ffmpeg-full` |
| DeepSeek API キー | 日中翻訳 | <https://platform.deepseek.com>（1時間の動画で数円程度） |

字幕フォントは macOS 標準の苹方を使うため、追加インストール不要です。

## セットアップ

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp config.example.toml config.toml   # deepseek.api_key を記入
./ja-video-subtitles download                 # ASR モデルの初回ダウンロード（約 1.5GB）
```

モデルはプロジェクト内 `.cache/hf/` に保存され（`HF_HOME` で固定）、成功時に `.model-ready` マーカーが書かれます。ダウンロードは既定で `hf-mirror.com` ミラーを使用。`HF_ENDPOINT=https://huggingface.co` で変更可能です。

## 使い方

```bash
./ja-video-subtitles run /path/to/xxx.mp4 -o /path/to/output   # 単一ファイル
./ja-video-subtitles run /path/to/dir   -o /path/to/output     # フォルダ一括
./ja-video-subtitles run /path/to/dir   -o out -y              # 同名ファイルを自動上書き
./ja-video-subtitles run xxx.mp4 -o out --force                # 全工程をやり直し
```

成果物（すべて `-o` ディレクトリ内）：`xxx.ja.srt`（日本語字幕）、`xxx.zh.srt`（中国語字幕）、`xxx.bilingual.srt`（二カ国語：上段日本語・下段中国語）、`xxx.sub.mp4`（完成動画）、`report-<タイムスタンプ>.md`（実行レポート）、`run.log`（ログ）。

動作のポイント：

- 相対パスはコマンド実行時のカレントディレクトリ基準。設定ファイルとモデルキャッシュは常にプロジェクトディレクトリから読み込まれます。
- 既存の正常な中間生成物は自動スキップ（途中再開が可能）。壊れた生成物は自動でやり直します。
- 同名の完成動画がある場合、処理開始前にまとめて上書き確認。焼き付け中に確認で止まることはありません。非対話環境では「上書きしない」が既定です。
- 事前チェックは 8 項目（OS、Python 依存、ffmpeg+libass、config/api_key、DeepSeek 接続、モデル有無、ディスク容量、出力先の書き込み権限）。1 つでも失敗したら即終了し、対処法を表示します。
- 焼き付け中の Ctrl+C は ffmpeg を確実に終了させ、中途半端なファイルを削除します。

## テスト

```bash
.venv/bin/python -m unittest discover -s tests
```

オフラインのユニットテスト。モデルも API も不要です。

## 処理時間の目安（1時間の動画、M シリーズ）

文字起こし：約 10–20 分、翻訳：約 2–5 分、焼き付け：約 5–15 分（VideoToolbox）。

## ライセンス

MIT。`LICENSE` を参照してください。
