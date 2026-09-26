# Realtime Narration Video

[English](README.en.md) | 日本語

> 汎用動画拡散モデルLTXを用いた、ローカル完結可能なフルフレーム会話キャラクターパイプライン。RTX 5090級の検証環境で、送信から先頭動画完成まで最短約2.6秒を実測。

動画下のチャット入力をGemma 4へ送り、ストリーミング応答をAivisSpeechで音声化します。約5秒の音声チャンクをLTX-2.5へ渡し、完成した動画から順次再生する技術検証アプリです。LTXが生成した音声は使用せず、最終MP4には元のTTS音声を差し戻します。

開発中に行った速度・解像度・steps・実写リップシンクの比較は、[改良の経緯と測定記録](docs/development-notes.md)にまとめています。構成、API、パラメータ、運用方法は[テクニカルガイド](docs/technical-guide.md)を参照してください。

## 動作サンプル

[![Realtime Narration Videoの動作サンプル(GIF、実速度)](docs/assets/demo.gif)](docs/assets/demo.mp4)

上のGIFは実速度の抜粋(12秒)です。クリックすると、LLMの応答をTTSと動画へ順次変換して再生する約57秒のフルデモ動画を開きます。直接開く場合は[MP4版（1.8MB）](docs/assets/demo.mp4)をご覧ください。

### リアルタイム会話デモ(実時間・72秒)



https://github.com/user-attachments/assets/a5eb5e5c-3b14-4a47-97b9-b8ca1d9cbb53



実写系キャラクターとのリアルタイム会話を編集なしの実時間で収録したものです(RTX PRO 6000 Blackwellで収録)。冒頭のテキスト入力のエンターが開始点で、以降は完全に連続再生されます。ファイルとして開く場合は[MP4版（6.0MB）](docs/assets/demo-conversation.mp4)をどうぞ。

この動画はGitHub掲載用に圧縮しているため、実際の生成・表示画質よりも若干劣化しています。

## 現在のMVP

- 文・節単位の分割と文単位TTS
- OpenAI互換Gemma 4への会話履歴付きストリーミングチャット
- LLM受信中に確定した文からTTSを並列開始
- 文末・読点を優先し、語尾保護の範囲内で約22〜26文字からTTSを先行する動的動画チャンク
- TTS音声チャンク準備とLTX動画生成のパイプライン処理
- キャラクター画像とTXTファイルのドラッグ＆ドロップ入力
- 動画への具体的な指示を発話動画の生成プロンプトへ即時反映
- 会話入力の文頭にある`[動作指示]`を読み上げず、そのターンだけの動画指示として優先適用
- 貼り付け・キーボード入力・TXTドロップに対応した、LLMを通さない文章朗読
- 日本語・英語のUI切り替えと、自動／日本語／英語の独立した会話言語設定
- 実際のWAV時間を使ったチャンク編成
- LTX-2.5 Audio-to-Video生成
- Realtime Video Studioと同一の16/20/24fps・横型/4:3/縦型プロファイル
- 実写の口固定を避けるため、登録時に生成した発話用アンカーを全チャンクで再参照
- 実写キャラクター登録時にLTXを事前ロードし、選択解像度・8 stepsで口を開いた高品質な発話用アンカーを自動生成
- 元TTS音声への差し替え
- 初期1チャンクで再生開始し、表裏2つのvideo要素で次チャンクを先読み
- 実測LTX生成時間より長い再生バッファを確保する動的開始判定と切替ギャップ表示
- 短い発話も5秒動画として生成し、完成済みなら発話終了後に次へ切替。5秒を超える発話は最終映像フレームを維持して元TTS音声を最後まで再生
- 全動画プロファイルで各ターン先頭を同画角系の低解像度、後続を選択解像度で生成。stepsはUIから変更可能（既定4。先頭は`min(4, steps)`）
- 待機映像はプレイリスト方式: 設定時に3〜5本(選択可)を生成し、全て入力ポーズで始まり終わるクリップを順次再生。再生1周ごとに裏で1本追い足して常に新しい動きを供給し、チャット到着時は追い生成を即中断して会話生成を優先。タブ非表示・5分間無操作のときは追い生成を休止しGPUを解放
- 会話の開始画像(送信瞬間の待機フレームで静止→そのポーズから話し始める)と会話の終了姿勢(最終チャンクの末尾を待機開始ポーズへFLF錨止め)をUIで選択でき、両方を有効にすると待機→会話→待機の全サイクルがポーズ連続になる(既定は従来動作=口動作優先)
- 上手く調整できたキャラクターは設定・アイドル動画・発話アンカーごとプリセット保存でき、画像アイコン一覧からワンクリックで復元(再生成ゼロ・即時)・削除できる
- 実写の発話動作が最も安定したseed 1004を既定値とし、UIから変更して全チャンクへ適用可能
- 実写の準備生成はmodality_scale 1.3で高品質なアンカーを作成。会話中のscale 1.3はUIの「口動作強調」で切替（既定は無効＝高速。蒸留4 stepsで口の開きは維持できることを実測確認済み）
- ターン送信時に元キャラクター画像へ戻し、次動画の再生開始まで前ターンの最終フレームを覆う
- ユーザー選択のキャラクター種別で生成方針を切替（標準: scaleなし・指定seedを基準にチャンクごとに変化・ターン内連結、実写優先: modality scale 1.3・指定seed・毎回発話用アンカー）
- Gatewayジョブを100ms間隔で監視
- SSEによる250ms単位の状態更新とLLM/TTS/LTX工程時刻の記録
- Gateway/TTSエラーの表示と永続化

単一GPUでは動画生成が再生時間より遅い場合があります。現段階ではバッファが尽きると次チャンクの完成を待つ準リアルタイム方式です。

## 動作環境の目安

| GPU構成 | 判定 |
|---|---|
| RTX 5090 32GB単騎 + TE（Text Encoder）移設 | ◎ 余裕大（GPU 0：約18GB） |
| 24GB（Blackwell）+ 16GB | ○ 余裕あり（速度は要実測） |
| 16GB（Blackwell）+ 16GB（世代不問） | △ メモリ削減策を全投入して余裕±0GB。擬似検証必須 |
| RTX 4090 24GB | ✕ FP4カーネル非対応（NF4なら動作するが低速） |

上記は本構成でFP4を利用する場合の目安です。実際の使用量と速度は、動画プロファイル、モデル配置、同時稼働プロセスおよびドライバー環境によって変動します。

## 起動

Python 3.11以上、ffmpeg、稼働中のdiffusers-movie-server gateway、AivisSpeech Engineが必要です。

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
PATH="$PWD/.venv/bin:$PATH" ./run.sh
```

ブラウザーで `http://localhost:8782` を開きます。

LLM、Gateway、TTSの接続先は`.env`で設定します。`.env.example`のlocalhost設定を環境に合わせて変更してください。`LLM_MODEL`が空の場合は`/v1/models`から名前に`44b`を含むモデルを優先し、なければ先頭のモデルを自動選択します。

Gatewayはバックエンドを排他的に管理します。8631/8632で管理外のH3/LTXプロセスが起動している場合は、生成受付が409になります。

## API

- `POST /api/sessions` — character/text/concept/video_instruction等をmultipartで送信
- `PATCH /api/sessions/{id}/settings` — 動画指示などのライブ設定を更新
- `POST /api/sessions/{id}/messages` — ユーザー発言を送信してストリーミング生成を開始
- `POST /api/sessions/{id}/narrations` — 入力文章をLLMへ送らず直接分割・朗読
- `POST /api/presets` / `GET /api/presets` / `POST /api/presets/{id}/restore` / `DELETE /api/presets/{id}` — キャラクタープリセットの保存・一覧・復元(再生成ゼロで即時)・削除
- `POST /api/sessions/{id}/regenerate-idle` — 待機動画プールをリセットして現在の設定で作り直し
- `POST /api/sessions/{id}/idle-pool` — 待機動画プールへ1本追い足し(古い動画は自動削除)
- `GET /api/sessions/{id}/idle-video/{n}` — プール内の待機動画を取得
- `GET /api/sessions/{id}` — セッションとチャンク状態
- `DELETE /api/sessions/{id}` — 現在チャンク終了後にキャンセル
- `GET /api/sessions/{id}/chunks/{index}/video` — 差し替え済みMP4
- `GET /api/sessions/{id}/chunks/{index}/audio` — 元TTS WAV
- `GET /healthz` — アプリ、Gateway、TTS接続状態

## テスト

```bash
.venv/bin/pytest -q
```

## ライセンス

このリポジトリ内のアプリケーションコードは[Apache License 2.0](LICENSE)で公開しています。

Pythonパッケージ、ffmpeg、AivisSpeech、LTX-2.5、Gemmaなどの依存モジュール、外部サービス、モデル、ウェイトは本ライセンスの対象に含まれません。それぞれの提供元が定めるライセンス、利用規約、配布条件に従ってください。このリポジトリにはモデルおよびモデルウェイトを同梱していません。

### 商用利用について

本プロジェクトを商用利用する場合は、導入事例と利用状況の把握、必要に応じた技術支援のため、[GitHub Issues](https://github.com/animede/Realtime_Narration_Video/issues)からご連絡をお願いします。

この連絡は任意の協力依頼であり、Apache License 2.0が認める商用利用に追加条件を課すものではありません。依存モジュール、モデル、ウェイトおよび外部サービスについては、商用利用が認められているかを各提供元のライセンスと利用規約で別途確認してください。
