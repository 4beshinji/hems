# HEMS — Home Environment Management System

個人・単身者向けのパーソナルAIホームアシスタント基盤です。センサーデータ、生体情報、スケジュール、デバイス状態をLLMの「頭脳」に統合し、ルールと対話で住環境を管理します。常時起動のコアに加え、必要な連携だけをDocker Composeプロファイルで追加できます。

## Quick Start

```bash
make quickstart
```

`.env` がなければ自動生成し、共有Pythonベースイメージをビルドして常時起動コアを立ち上げます。
Backendは起動前にversioned migrationを自動適用し、失敗時はAPIを起動しません。既存PostgreSQL環境は更新前に
backupを取得してください。SQLite軽量モードはhead不一致時にrevision別`*.pre-<head>.bak`を自動作成します。

- ダッシュボード: http://localhost:8080
- Backend API: http://localhost:8010/docs
- Voice API: http://localhost:8012/docs

コアだけではLLMバックエンドが起動しないため、続けてローカルLLMまたは開発用mockを立ち上げてください:

```bash
# ローカルLLM（初回はモデルpullに時間がかかります）
cd infra && docker compose --profile ollama up -d

# または開発用mock LLM（インターネット不要、機能は限定）
cd infra && docker compose --profile mock up -d
```

### 手動セットアップ

```bash
cp env.example .env
python infra/scripts/init_env.py
cd infra
docker compose --profile bootstrap build base
docker compose up -d --build
```

### SQLite軽量モード（PostgreSQL不要）

```bash
make quickstart-sqlite
```

ローカルでBackendだけを起動する場合もmigration-firstの`make backend-run`を使用します。

## HEMSでできること

HEMSは「家の状態」と「あなたの状態」を1つの世界モデルにまとめ、以下を自動化・対話で支援します。

- **環境監視とアラート**: 温湿度、CO₂、VOC、PM2.5、照度などを監視。閾値超過時に通知・タスク化します。
- **デバイス統合制御**: Zigbee、SwitchBot、Tapo、Home Assistant経由の照明・空調・カーテン・スイッチを一元管理。
- **生体情報連携**: スマートバンドの心拍、SpO₂、睡眠、ストレス、HRVなどを取り込み、疲労スコアを推定。
- **カメラ知覚**: 在室検知、姿勢分類、VLMによるシーン理解で在宅状態を把握。
- **パーソナライズドチャット**: ダッシュボード上でAIキャラクターと会話。ナレッジ・生体・環境データを参照した回答を生成します。
- **音声入出力**: テキスト読み上げ（TTS）と音声入力（STT）に対応。発話に連動してアバターがジェスチャーします。
- **イベント自動化**: 起床、帰宅、外出、定時をトリガーに天気・ニュース・挨拶・デバイス操作を自動実行。
- **知識検索**: 外部ドキュメントを取り込み、BM25＋ベクトル＋タイトルブーストのハイブリッド検索で回答に活用。
- **PC/サービス監視**: CPU/GPU/メモリ/ディスク、Gmail/GitHub未読、ブラウザ監視をエッジトリガーに変換。
- **買い物リスト**: 音声・チャット・ルールから買い物アイテムを登録。購入履歴とMQTT通知を管理。

## 構成

HEMSはMQTTを中心バスとしたマイクロサービス構成です。6つのコアサービスを常時起動し、必要に応じてブリッジを追加します。

```
┌─────────────────────────────────────────────────────────────────┐
│                          HEMS Core                               │
├──────────────┬──────────────┬──────────────┬────────────────────┤
│  mosquitto   │    brain     │   backend    │     frontend       │
│    MQTT      │  ReAct/Rule  │  FastAPI/DB  │   React dashboard  │
│              │   Chat       │              │     + VRM avatar   │
├──────────────┼──────────────┼──────────────┼────────────────────┤
│ voice-service│ weather-bridge│             │     mock-llm       │
│  TTS / STT   │  天気・警報  │             │     (dev)          │
└──────────────┴──────────────┴─────────────┴────────────────────┘
        ↕ MQTT
   ブリッジ群（任意）: OpenClaw / Obsidian / GAS / HA / Biometric /
                       Perception / SwitchBot / Tapo / Zigbee / News /
                       Knowledge / STT / VOICEVOX / Ollama
```

### コアサービス

| Service | Container | Port | 役割 |
|---------|-----------|------|------|
| Mosquitto | hems-mqtt | 1893 | MQTTブローカー |
| Brain | hems-brain | — | ReAct認知ループ、チャットサーバー、世界モデル |
| Backend | hems-backend | 8010 | FastAPI REST API、永続化、ダッシュボード向けデータ |
| Frontend | hems-frontend | 8080 | Reactダッシュボード（nginx） |
| Voice | hems-voice | 8012 | プラグインTTS、STT連携 |
| Weather | hems-weather-bridge | — | 天気予報・警報・朝夜レポート発行 |

### 主要なオプションプロファイル

| Profile | Service | Port | 内容 |
|---------|---------|------|------|
| `mock` | Mock LLM | 8011 | 開発用ダミーLLM（依存なし） |
| `ollama` | Ollama | 11444 | ローカルLLM推論 |
| `voicevox` | VOICEVOX | 50031 | 高品質日本語TTS |
| `stt` | STT | 8023 | Whisper/sherpa-onnx/qwen3-asr音声認識 |
| `openclaw` | OpenClaw Bridge | 8013 | PCメトリクス・サービス監視 |
| `obsidian` | Obsidian Bridge | 8014 | Obsidian vault連携 |
| `gas` | GAS Bridge | 8015 | Google Calendar/Tasks/Gmail/Sheets/Drive |
| `ha` | HA Bridge | 8016 | Home Assistant連携 |
| `biometric` | Biometric Bridge | 8017 | スマートバンド生体データ |
| `perception` | Perception | 8018 | YOLOv11s-poseカメラ検知 + VLM |
| `switchbot` | SwitchBot Bridge | 8019 | SwitchBot直接API制御 |
| `tapo` | Tapo Bridge | 8020 | Tapo P110/P115直接LAN制御 |
| `zigbee` | Zigbee2MQTT | 8090 | Zigbee USB coordinator制御 |
| `news` | News Bridge | 8021 | RSS + Ollama要約ニュース |
| `knowledge` | Knowledge Bridge | 8022 | マルチフォーマット文書取込・検索 |

ポートは `HEMS_PORT_*` 環境変数で変更できます。

## ダッシュボード

React 19 + TypeScript + Tailwind CSS 4で構築されたSPAです。

| ビュー | 内容 |
|--------|------|
| Dashboard | AIチャット、アバター、タスク、統合タイムライン、天気・ニュース |
| Devices | ゾーン環境、照明/空調/カーテン、デバイスレジストリ、Zigbeeペアリング |
| Digital | PCメトリクス、サービス状態、GAS/Obsidian連携、買い物リスト |
| User | プロフィール、生体情報、疲労スコア、設定 |
| Mobile | モバイルコンパニオン登録・管理 |

## AIキャラクターとアバター

### キャラクター

YAMLで人格を定義。同梱テンプレートを使うか、完全にカスタマイズできます。

```bash
# テンプレート指定
echo 'CHARACTER=yukari' >> .env

# フルカスタム
cp config/character.yaml.example config/character.yaml
# 編集後、コンテナ再起動なしでホットリロード
mosquitto_pub -h localhost -u hems -P hems_dev_mqtt \
  -t hems/brain/reload-character -m reload
```

同梱テンプレート例: `default`, `ena`, `tsundere`, `gentle-senpai`, `butler`, `nurserobo-typet`, `una`, `yukari` など。

### VRMアバター

VRMモデルを配置するだけで3Dアバターが起動します。発話内容に応じて `config/motions.yaml` からモーションを自動選択し、音声波形でリップシンクします。

```bash
cp your-character.vrm services/frontend/public/models/avatar.vrm
```

表示モード: hidden → panel → overlay（ヘッダー/サイドバーのアバターボタンで切替）。

## 音声入出力

### TTS（テキスト読み上げ）

プラグイン式。Primary失敗時はFallbackに自動切替します。

| Provider | 概要 |
|----------|------|
| `voicevox` | VOICEVOX（Docker、デフォルト、speaker 47） |
| `voisona` | VoiSona Talk（ホストアプリ） |
| `edge-tts` | Microsoft Edge TTS（クラウド） |
| `aivoice` | A.I.VOICE Editor（Wine/Windowsホスト） |
| `espeak` | espeak-ng（ローカル・軽量、デフォルトFallback） |

### STT（音声入力）

`--profile stt` で有効化。ブラウザはPTT/VAD/OFFモードを切り替えられます。

| Provider | Model | 特徴 |
|----------|-------|------|
| `whisper` | large-v3-turbo | 汎用（デフォルト） |
| `sherpa-onnx` | Parakeet 0.6B JP | 日本語高速 |
| `qwen3-asr` | Qwen3-ASR 1.7B | 高品質 |

## デバイスレジストリ

2層構成で管理します。

- **Backend**: SQLite/PostgreSQL上の永続的な信頼情報源。REST CRUD、heartbeat自動登録、フロントエンドUI。
- **Brain**: メモリ内TTLキャッシュ。LLMコンテキスト、ステートマシン（online/stale/sleeping/offline）、タイムアウト最適化。

MQTT heartbeat → Brainキャッシュ更新 → Backend `/devices/heartbeat` 永続化 → Frontend表示 という流れです。

## Tech Stack

| 層 | 技術 |
|----|------|
| Language | Python 3.11 |
| Web framework | FastAPI, Uvicorn, aiohttp |
| ORM / DB | SQLAlchemy 2.x (async), PostgreSQL 16（デフォルト）/ SQLite |
| Messaging | Mosquitto MQTT (paho-mqtt) |
| Validation / config | Pydantic 2.x, python-dotenv, YAML |
| LLM | OpenAI / Anthropic / Ollama (LLMRouter経由) |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Query, Framer Motion, pnpm |
| 3D Avatar | Three.js, React Three Fiber, @pixiv/three-vrm |
| TTS | espeak-ng, VOICEVOX, Edge TTS, VoiSona Talk, A.I.VOICE |
| STT | faster-whisper, sherpa-onnx, Qwen3-ASR |
| Search | BM25 + vector (Ollama embeddings) + title boost, RRF |
| Perception | RTMO (rtmlib / ONNX Runtime), moondream / minicpm-v VLM |
| Infra | Docker Compose, BuildKit, Mosquitto |
| Edge | MicroPython (ESP32), ESP-NOW/UART/I2C/BLE |

## 開発・運用コマンド

```bash
make lint          # ruff check + format check
make format        # ruff check --fix + format
make test-quick    # pytest（カバレッジなし）
make test          # pytest（カバレッジ付き）
make test-e2e      # 起動済みCore構成のE2E
make test-lite-e2e # 起動済みLite構成のE2E
make build-frontend
make docker-base   # hems-base:py3.11ビルド
make security      # pip-audit + hadolint
make ci            # lint + test + build-frontend + security
```

フロントエンド単体開発:

```bash
cd services/frontend
pnpm install
pnpm dev      # Vite dev server
pnpm build    # tsc -b && vite build
pnpm test     # vitest run
```

## ドキュメント

HEMSはドキュメントグラフ構造を取っています。詳細は各canonicalドキュメントを参照してください。

| ドキュメント | 内容 |
|-------------|------|
| [`CLAUDE.md`](CLAUDE.md) | プロジェクト全体のオリエンテーション・ハブ |
| [`services/brain/CLAUDE.md`](services/brain/CLAUDE.md) | Brain/ReAct/tools/Chat/Event Automation |
| [`services/backend/CLAUDE.md`](services/backend/CLAUDE.md) | Device Registry/Shopping/Chat REST |
| [`services/voice/CLAUDE.md`](services/voice/CLAUDE.md) | TTS/STT |
| [`docs/IMPLEMENTATION_MAP.md`](docs/IMPLEMENTATION_MAP.md) | code↔compose↔MQTT↔tools↔envの正確なマッピング |
| [`docs/CLAUDE-bridges.md`](docs/CLAUDE-bridges.md) | 11ブリッジ統合の詳細 |
| [`docs/README.md`](docs/README.md) | セットアップ・運用ガイド索引 |

## License

HEMS is licensed under the **[PolyForm Noncommercial License 1.0.0](LICENSE)**.

個人・趣味・研究・教育など、**非営利目的かつ自分のハードウェア上での利用**が許可されています。商業利用（ハードウェアへの同梱、製品としての再頒布、サービスとしての提供など）は公開ライセンスでは許可されず、著者との別途書面による商用ライセンス契約が必要です。

The software is provided **as is, without warranty or support obligation**.
