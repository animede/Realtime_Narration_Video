# Realtime Narration Video

[English](README.en.md) | 日本語

> 汎用動画拡散モデルLTXを用いた、ローカル完結可能なフルフレーム会話キャラクターパイプライン。RTX PRO 6000 Blackwell（48GB級）の検証環境で、送信から先頭動画完成まで最短約2.6秒を実測。

動画下のチャット入力をGemma 4へ送り、ストリーミング応答をAivisSpeechで音声化します。約5秒の音声チャンクをLTX-2.5へ渡し、完成した動画から順次再生する技術検証アプリです。LTXが生成した音声は使用せず、最終MP4には元のTTS音声を差し戻します。

コンパニオンアプリとして、本アプリをヘッドレスのキャラクターレンダリングサービスとして使う**音声会話クライアント** [Realtime_Conversation_Video](https://github.com/animede/Realtime_Conversation_Video)(マイクVAD→LLM `input_audio` 直渡し、ROLE注入、履歴要約)があります。

動画生成のベース技術は、diffusers 実装の自作エンジン **[Diffusers-LTX2.5](https://github.com/animede/diffusers-ltx2_5)** と **[Diffusers-MinimaxH3](https://github.com/animede/Diffusers_minimax-h3)** です。量子化・低VRAM化・リアルタイム化の技術詳細や単体サーバとしての使い方は、それぞれのリポジトリを参照してください。

開発中に行った速度・解像度・steps・実写リップシンクの比較は、[改良の経緯と測定記録](docs/development-notes.md)にまとめています。構成、API、パラメータ、運用方法は[テクニカルガイド](docs/technical-guide.md)を参照してください。

## 動作サンプル

[![Realtime Narration Videoの動作サンプル(GIF、実速度)](docs/assets/demo.gif)](docs/assets/demo.mp4)

上のGIFは実速度の抜粋(12秒)です。クリックすると、LLMの応答をTTSと動画へ順次変換して再生する約57秒のフルデモ動画を開きます。直接開く場合は[MP4版（1.8MB）](docs/assets/demo.mp4)をご覧ください。

### リアルタイム会話デモ（実時間・60秒、32GB相当VRAMで生成）





https://github.com/user-attachments/assets/e15ecb4d-5237-447e-abc9-7a64e3fea5d9







実写系キャラクターとのリアルタイム会話を編集なしの実時間で収録したものです。**空きVRAMを31GB（ヘッドレスRTX 5090相当）に制限した`nvfp4-32gb`構成で生成**しており、TTS（AivisSpeech）は2枚目のGPUで動作しています。冒頭のテキスト入力のエンターが開始点で、以降は完全に連続再生されます。ファイルとして開く場合は[MP4版（5.2MB）](docs/assets/demo-conversation.mp4)をどうぞ。

この動画はGitHub掲載用に圧縮しているため、実際の生成・表示画質よりも若干劣化しています。

## 現在のMVP

- 文・節単位の分割と文単位TTS
- OpenAI互換Gemma 4への会話履歴付きストリーミングチャット
- LLM受信中に確定した文からTTSを並列開始
- 文末、改行、コロン、日本語の自然な節境界でTTSを先行し、句読点のない位置では強制分割しない動的動画チャンク
- TTS音声チャンク準備とLTX動画生成のパイプライン処理
- キャラクター画像とTXTファイルのドラッグ＆ドロップ入力
- 動画への具体的な指示を発話動画の生成プロンプトへ即時反映
- 会話入力の文頭にある`[動作指示]`を読み上げず、そのターンだけの動画指示として優先適用
- 貼り付け・キーボード入力・TXTドロップに対応した、LLMを通さない文章朗読
- 日本語・英語のUI切り替えと、自動／日本語／英語の独立した会話言語設定
- 実際のWAV時間を使ったチャンク編成
- LTX-2.5 Audio-to-Video生成
- 16/20/24fps・横型/4:3/縦型の全24動画プロファイル
- 実写の口固定を避けるため、登録時に生成した発話用アンカーを全チャンクで再参照
- 実写キャラクター登録時にLTXを事前ロードし、選択解像度・8 stepsで口を開いた高品質な発話用アンカーを自動生成
- 元TTS音声への差し替え
- 初期1チャンクで再生開始し、表裏2つのvideo要素で次チャンクを先読み
- 実測LTX生成時間より長い再生バッファを確保する動的開始判定と切替ギャップ表示
- 短い発話も5秒動画として生成し、完成済みなら発話終了後に次へ切替。5秒を超える発話は最終映像フレームを維持して元TTS音声を最後まで再生
- 全動画プロファイルで各ターン先頭を同画角系の低解像度、後続を選択解像度で生成。stepsはUIから変更可能（既定4。先頭は`min(4, steps)`）
- 待機映像はプレイリスト方式: 登録時は常に3本を生成し、待機中に設定数3〜7本（既定5）まで1本ずつ漸進成長。6本以上はランダム再生。会話中は全セッションの追い生成を止め、チャット到着時は全セッションの進行中待機生成を即中断。タブ非表示・5分間無操作のときは補充を休止
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

## 動画エンジンの選択（LTX-2.5 / MiniMax-H3）

既定は LTX-2.5（従来どおり）。`VIDEO_ENGINE=h3` またはUIの「動画エンジン」で MiniMax-H3 ref2va を選べます（設計: `docs/h3-engine-plan.md`）。

**H3 のキャラクター画像は口を閉じたものを推奨します。** H3 の待機動画(FLF)は始点・終点を
キャラ画像に固定するため、待機中の口元は画像に忠実になります(開いた画像なら開いたまま。
実機確認 2026-10-07)。開いた画像しかない場合は `H3_CLOSED_IDLE_ANCHOR=1` で、登録時に
自動生成する閉口フレームを待機の端点に使えます(画質はわずかに下がります)。

| 環境変数 | 既定 | 内容 |
|---|---|---|
| `VIDEO_ENGINE` | `ltx25` | 新規セッションの既定エンジン |
| `H3_GATEWAY_PRESET` | `dual-realtime-ref2va` | gateway の H3 プリセット（32GB級は `-32gb`） |
| `H3_GPUS` | `0,1` | H3 の実行GPU（denoise=GPU0 / decode=GPU1） |
| `H3_PROFILE` | `h3-portrait-352x608` | 既定解像度（96GB級は `h3-portrait-384x704` 等） |
| `H3_FIRST_CHUNK_SECONDS` / `H3_TARGET_CHUNK_SECONDS` | `3.0` / `5.8` | 先頭／後続チャンクの目標発話長 |

H3は24fps固定・H3専用解像度のみ。リップシンクは音声（vocal_lock）に直接追従し、原音はH3側でmux済みのためr-n-vでの差し替えは行いません。プリセット（キャラ保存）はエンジン別に保存・一覧されます。

## 動作環境の目安

| GPU構成 | 判定 |
|---|---|
| 48GB級（RTX PRO 5000 / 6000 Blackwell） | ◎ リアルタイム動作（全常駐構成 `nvfp4-fast`、常駐実測 約33GB） |
| RTX 5090 32GB単騎 | ◎ リアルタイム動作（32GB向け全常駐構成 `nvfp4-32gb`、常駐実測 約28.8GB・4stepチャンク3.8秒=実時間の0.79倍）。**GPUは動画エンジン専有が前提（TTS・LLMはCPU実行または別ホストに置くこと。ヘッドルームは約2GB）**。upsampler非搭載のため upscale/t2i は不可 |
| RTX 4090 24GB | ✕ FP4カーネル非対応（NF4なら動作するが低速） |

上記はFP4（nvfp4）利用時の実測に基づく目安です。32GB級の行は空きVRAMを31GB（5090ヘッドレス相当）に制限したVRAM制限テストによる実測で、`nvfp4-32gb` プリセット（未使用の latent/temporal upsampler を非ロード −1.2GB、Text Encoder の埋め込みテーブルをCPUへ退避+不要なlogits計算を除去 −2.4GB）により、全常駐のリアルタイム構成が32GB級に収まることを確認しています（512×384・20fps・97フレーム・4stepsで定常3.5〜4秒/チャンク、出力品質は48GB構成と同等。なお32GB構成ではCUDA Graphを無効にします — 会話のような多shape実運用ではcaptureごとのメモリ蓄積が31GB予算に収まらないため。この解像度帯でのgraphの速度利得は僅かで、無効でもリアルタイムを維持します）。実際の使用量と速度は、動画プロファイル、モデル配置、同時稼働プロセスおよびドライバー環境によって変動します。

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
- `GET /healthz` — アプリ、Gateway、TTS、LLM接続状態

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
