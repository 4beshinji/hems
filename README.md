# HEMS — Home Environment Management System

個人生活統合管理システム。LLM/ルールベースの「頭脳」と IoT センサー、プラグイン式音声合成、
AI キャラクターシステムを組み合わせた、個人・家庭向けパーソナル AI アシスタント基盤。

[SOMS](https://github.com/...) (commit `1216952`) からのフォーク。

## Quick Start

```bash
cp env.example .env
cd infra
docker compose --profile bootstrap build base   # build hems-base:py3.11 (one-time)
docker compose up -d --build
```

- Dashboard: http://localhost:8080
- Backend API: http://localhost:8010/docs
- Voice API: http://localhost:8012/docs

## Features

### コア機能

- **ReAct 認知ループ**: 30秒サイクル・最大5イテレーションの LLM 推論 + ルールベースフォールバック
- **パーソナライズドチャット**: ダッシュボード上でAIキャラクターと直接対話 — 音声入力 (STT) 対応、ナレッジ検索・生体データ等を活用した RAG 回答
- **アラート抑制**: タスク作成後の重複生成を防止 (温度30分・CO2 10分)
- **AI キャラクター**: YAML 定義の人格 (5テンプレート) + ホットリロード
- **VRM アバター**: 3D アバター表示 (hidden / panel / overlay の3モード)、発話連動モーション
- **Ambient Speaker**: 5分間隔でセンサーデータに基づく自然な一言を自動生成・発話
- **プラグイン式 TTS**: espeak / VOICEVOX / Edge TTS / VoiSona Talk
- **XP ゲーミフィケーション**: タスク完了で XP 獲得 (50-500)
- **買い物リスト**: Brain 統合のショッピング管理 + 購入履歴 + MQTT通知
- **イベント自動化**: wake_up / arrival / departure / scheduled → ニュース・天気・挨拶を自動実行
- **データマート**: SOMS 互換の event_store — raw_events / llm_decisions / hourly_aggregates (730日保持)

### 外部連携

- **PC/サービス監視** (OpenClaw): CPU/GPU/メモリ/ディスク + Gmail・GitHub 未読エッジトリガー
- **ナレッジストア** (Obsidian): vault 連携 — 検索・書込・決定ログ自動記録
- **外部ナレッジ** (knowledge-bridge): マルチフォーマット文書取込 (MD/Python/JSON/PDF/DOCX/CSV/HTML) — BM25+ベクトル+タイトルブーストのハイブリッド検索 (3-way RRF)
- **Google 連携** (GAS): Calendar・Tasks・Gmail・Sheets・Drive
- **スマートホーム** (HA): 照明/空調/カバー/スイッチ/センサー/シーン + スケジュール学習
- **SwitchBot** (直接API): HA不要のデバイス制御 + IR リモート (Hub経由)
- **天気** (weather-bridge): JMA (気象庁) / OpenWeatherMap — 降雨・猛暑アラート (常時起動、JMA がデフォルトで API key 不要)
- **ニュース** (news-bridge): RSS + Ollama 要約 — 日次ブリーフィング + 緊急ニュース検知 + イベント駆動音声通知

### バイオメトリクス・パーセプション

- **バイオメトリクス**: Gadgetbridge webhook — 心拍/SpO2/睡眠/ストレス/疲労スコア/HRV/体温/呼吸数
- **カメラ知覚**: YOLOv11s-pose — 在室検知・姿勢分類 (立位/座位/臥位/歩行)・活動追跡
- **VLM シーン理解**: moondream / minicpm-v — 適応的頻度制御 + イベント駆動ブースト + オンデマンド分析

### エッジデバイス

- **ESP32 センサーノード**: XIAO ESP32-S3 + BME680 (温湿度/気圧/VOC) + PIR + CO2
- **ESP32 カメラノード**: Freenove WROVER + OV2640 (MCP/MQTT)
- **Swarm ネットワーク**: Hub (WiFi+MQTT) ← ESP-NOW/UART/I2C/BLE → Leaf デバイス

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    HEMS Core (常時起動)                    │
├──────────────┬──────────┬──────────┬─────────────────────┤
│  mosquitto   │  brain   │ backend  │      frontend       │
│  (MQTT)      │  (ReAct/ │ (API+XP+ │  (React/Tailwind)   │
│              │  Rule/   │ Shopping+│      +VRM           │
│              │  Chat)   │ Chat)    │                     │
├──────────────┼──────────┴──────────┼─────────────────────┤
│ voice-service│                     │      mock-llm       │
│  (TTS×4)     │                     │      (dev)          │
└──────────────┴─────────────────────┴─────────────────────┘

Profiles:  voicevox | ollama | mock | openclaw | obsidian
           gas | ha | biometric | perception | switchbot | tapo
           zigbee | news | knowledge | stt
```

### Brain ツール一覧 (46)

| カテゴリ | ツール | Profile |
|---------|--------|---------|
| 基本 | `create_task`, `speak`*, `get_active_tasks`, `get_zone_status`, `get_device_status`, `send_device_command`, `get_sensor_history` | 常時 |
| 買い物 | `add_shopping_item`, `get_shopping_list` | 常時 |
| デバイスレジストリ | `control_actuator`, `list_devices`, `describe_device`, `execute_scene_by_name`, `list_scenes`, `zigbee_permit_join` | 常時 (デフォルト有効) |
| PC | `get_pc_status`, `run_pc_command`, `control_browser`, `send_pc_notification` | openclaw |
| サービス | `get_service_status` | openclaw |
| ナレッジ (Obsidian) | `search_notes`, `write_note`, `get_recent_notes` | obsidian |
| ナレッジ (外部) | `search_knowledge`, `get_knowledge_sources`, `read_knowledge_document` | knowledge |
| スマートホーム | `control_light`, `control_climate`, `control_cover`, `control_switch`, `get_home_devices`, `get_sensor_data`, `execute_scene` | ha |
| システム | `set_guest_mode`, `get_weather` | ha |
| バイオ | `get_biometrics`, `get_sleep_summary` | biometric |
| カメラ / VLM | `get_perception_status`, `describe_scene`, `list_scene_objects`, `get_scene_timeline` | perception |
| SwitchBot | `get_switchbot_devices`, `control_switchbot`, `send_switchbot_ir` | switchbot |
| ニュース | `get_news_summary` | news |

\* `speak` は MotionRetriever により発話内容・トーンに基づいてアバターモーションを自動選択

### サービスポート

| Service | Port | Container |
|---------|------|-----------|
| Frontend | 8080 | hems-frontend |
| Backend API | 8010 | hems-backend |
| Mock LLM | 8011 | hems-mock-llm |
| Voice | 8012 | hems-voice |
| OpenClaw Bridge | 8013 | hems-openclaw-bridge |
| Obsidian | 8014 | hems-obsidian-bridge |
| GAS | 8015 | hems-gas-bridge |
| HA | 8016 | hems-ha-bridge |
| Biometric | 8017 | hems-biometric-bridge |
| Perception | 8018 | hems-perception |
| SwitchBot | 8019 | hems-switchbot-bridge |
| Tapo | 8020 | hems-tapo-bridge |
| News Bridge | 8021 | hems-news-bridge |
| Knowledge Bridge | 8022 | hems-knowledge-bridge |
| STT | 8023 | hems-stt |
| Zigbee2MQTT (UI) | 8090 | hems-zigbee2mqtt |
| VOICEVOX | 50031 | hems-voicevox |
| Ollama | 11444 | hems-ollama |
| PostgreSQL | 5442 | hems-postgres |
| MQTT | 1893 | hems-mqtt |

ポートは `HEMS_PORT_*` 環境変数でカスタマイズ可能。

## Chat (パーソナライズドAI対話)

ダッシュボード上でAIキャラクターと直接対話。テキスト入力 + 音声入力 (Web Speech API) 対応。

```
ユーザー → Backend (永続化) → Brain Chat Server (:8080)
  └─ LLM ReAct (読み取り専用ツール: search_knowledge, get_biometrics, etc.)
  └─ キャラクター人格に基づいた回答生成
  └─ 短い応答は自動音声合成 (TTS)
```

- **3-way ReAct**: BrainがLLMにtools付きで会話し、ナレッジ・生体・環境データを参照
- **スライディングウィンドウ**: 直近20メッセージを会話コンテキストに保持
- **統合タイムライン**: チャットメッセージと音声イベントを時系列で統合表示

## Knowledge Bridge (ナレッジ取込)

外部ディレクトリからの読み取り専用・マルチフォーマット文書取込。

```bash
# .env
KNOWLEDGE_SOURCE_PWS=/path/to/pws
KNOWLEDGE_SOURCES=[{"name":"pws","path":"/sources/pws","extensions":[".md",".py",".json",".pdf"]}]

# ベクトル検索を有効にする場合 (requires --profile ollama)
EMBEDDING_URL=http://ollama:11434
EMBEDDING_MODEL=nomic-embed-text

docker compose --profile knowledge up -d --build
```

- **8種ローダー**: Markdown, Python (.py AST), JSON, Text, PDF (pdfplumber), DOCX, CSV, HTML
- **ハイブリッド検索**: BM25 (キーワード) + Vector (Ollama embedding) + Title boost → 3-way RRF
- **Ollama 不在時**: BM25 + Title の2-way に自動降格
- **埋め込みキャッシュ**: ディスク永続化、変更ドキュメントのみ再埋め込み

## AI Character System

```bash
# ゼロコンフィグ (デフォルト人格)
docker compose up -d

# ワンライナー (同梱テンプレート)
echo 'CHARACTER=tsundere' >> .env
docker compose restart brain voice-service

# フルカスタム
cp config/character.yaml.example config/character.yaml
vi config/character.yaml
# ホットリロード (コンテナ再起動不要)
mosquitto_pub -h localhost -u hems -P hems_dev_mqtt \
  -t hems/brain/reload-character -m reload
```

| テンプレート | 一人称 | formality | 特徴 |
|-------------|--------|-----------|------|
| `default` | 私 | 2 | フレンドリーアシスタント (デフォルト) |
| `ena` | エナ | 0 | ハイテンションデジタル居候 |
| `tsundere` | あたし | 0 | 素直になれない、世話好き |
| `gentle-senpai` | 私 | 1 | 穏やか、褒め上手 |
| `butler` | わたくし | 4 | 完璧主義、品格 |

バリデーション: `python validate_character.py --all`

## VRM Avatar System

3D アバターを Dashboard に表示する機能。モデルファイルを配置するだけで動作する。

```bash
# VRM モデルを配置 (必須)
cp your-character.vrm services/frontend/public/models/avatar.vrm

# 表示モード切替 (ヘッダーのアバターボタン)
# hidden → panel (サイドパネル) → overlay (画面オーバーレイ) → hidden
```

| 機能 | 説明 |
|------|------|
| モード | hidden / panel / overlay (localStorage に永続化) |
| モーション | 発話時に `motions.yaml` から BM25+トーン親和性でジェスチャー自動選択 |
| リップシンク | 音声波形解析による口パク同期 |
| アイドル | 無操作時の自然なランダムモーション + 視線放浪 |
| フォールバック | VRM 未配置時はプレースホルダーを表示 |

**モーション定義** (`config/motions.yaml`): 10種類のジェスチャー (挨拶・反応・警告・感情・提案)。
YAML に追加するだけで MotionRetriever が自動的に選択候補に組み込む。

## Optional Profiles

```bash
# VOICEVOX (高品質日本語 TTS)
docker compose --profile voicevox up -d
# → .env: TTS_PROVIDER=voicevox

# Ollama (ローカル LLM — GPU自動検出)
python infra/scripts/gpu_setup.py   # docker-compose.gpu.yml 生成
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile ollama up -d
docker exec hems-ollama ollama pull qwen3.5   # 初回のみ

# Ollama (CPU のみ)
docker compose --profile ollama up -d
docker exec hems-ollama ollama pull qwen3.5

# SQLite に戻す場合 (PostgreSQL が既定)
DATABASE_URL=sqlite+aiosqlite:///./data/hems.db docker compose up -d

# OpenClaw (PC メトリクス + Gmail/GitHub 監視)
docker compose --profile openclaw up -d

# Obsidian (ナレッジストア)
docker compose --profile obsidian up -d

# GAS (Google Calendar/Tasks/Gmail/Sheets/Drive)
docker compose --profile gas up -d

# Home Assistant (スマートホーム制御 + スケジュール学習)
# ⚠️ セキュリティ注意: privileged + network_mode:host が必要。
# 同一ホスト運用前に docs/ha-isolation.md を参照すること。
docker compose --profile ha up -d

# Biometric (スマートバンド心拍/睡眠/疲労スコア)
docker compose --profile biometric up -d

# Perception (YOLOv11s-pose カメラ検知 + 活動追跡)
docker compose --profile perception up -d

# SwitchBot (直接API制御 — HA不要)
docker compose --profile switchbot up -d

# News (RSS + Ollama ニュース要約 — ollama 必須)
docker compose --profile news --profile ollama up -d

# Knowledge (外部ドキュメント取込 — ベクトル検索は ollama 推奨)
docker compose --profile knowledge up -d


# 複数プロファイル組み合わせ
docker compose --profile ha --profile biometric --profile switchbot --profile knowledge up -d
```

## Frontend

React 19 + TypeScript + Tailwind CSS 4 + TanStack Query + Framer Motion

| ページ | 内容 |
|--------|------|
| Dashboard | アバター、AIチャット、タスク一覧、XP、音声イベント統合タイムライン |
| Physical | ゾーン環境 (温湿度/CO2)、デバイス状態、天気、エネルギー |
| Digital | PC メトリクス、サービス状態、GAS、Obsidian、買い物リスト |
| User | プロフィール、バイオメトリクス、設定 |

```bash
cd services/frontend
pnpm install
pnpm dev      # Vite dev server (HMR)
pnpm build    # tsc -b && vite build
```

## Tech Stack

| 層 | 技術 |
|----|------|
| Backend | Python 3.11, FastAPI, SQLAlchemy (async), paho-mqtt, Pydantic 2.x |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Query, Framer Motion |
| 3D Avatar | Three.js, React Three Fiber, @pixiv/three-vrm |
| LLM | OpenAI / Anthropic / Ollama (マルチプロバイダー) |
| TTS | espeak-ng, VOICEVOX, Edge TTS, VoiSona Talk |
| Search | BM25 (rank_bm25) + Vector (Ollama embedding + numpy) + RRF |
| DB | PostgreSQL 16 (default) / SQLite |
| Infra | Docker Compose, Mosquitto MQTT |
| Edge | MicroPython (ESP32), SensorSwarm バイナリプロトコル |

## Documentation

| ドキュメント | 内容 |
|-------------|------|
| [avatar-setup.md](docs/avatar-setup.md) | VRM アバター配置・モーション追加・リップシンク |
| [shopping-list.md](docs/shopping-list.md) | 買い物リスト — API 操作・定期購入・外出連携 |
| [event-automation.md](docs/event-automation.md) | イベント自動化 — 起床/帰宅/定時トリガー設定 |
| [SMART_HOME_SETUP.md](docs/SMART_HOME_SETUP.md) | Home Assistant + HEMS 統合セットアップ |
| [ha-isolation.md](docs/ha-isolation.md) | HA 運用隔離ガイド — privileged リスクと VLAN/別ホスト推奨構成 |
| [smart-home-device-guide.md](docs/smart-home-device-guide.md) | マルチプロトコルデバイス総合ガイド |
| [sensor-purchasing-guide-jp.md](docs/sensor-purchasing-guide-jp.md) | センサー購入ガイド (技適準拠・Amazon.co.jp) |
| [sensor-purchasing-guide-aliexpress.md](docs/sensor-purchasing-guide-aliexpress.md) | センサー購入ガイド (AliExpress・コスト最優先) |
| [smartband-setup.md](docs/smartband-setup.md) | スマートバンドセットアップ |
| [voisona-talk-setup.md](docs/voisona-talk-setup.md) | VoiSona Talk TTS セットアップ |

## Roadmap

- **Phase 1** (完了): Core MVP — Backend + Brain + Voice + Frontend + Character + Alert Suppression
- **Phase 2** (完了): 外部連携 — OpenClaw, Obsidian, GAS, Home Assistant, Biometric
- **Phase 3** (完了): Perception — カメラ検知・姿勢分類・活動追跡 (YOLOv11s-pose)
- **Phase 4** (完了): IoT拡張 — SwitchBot直接統合, Weather Bridge, 買い物リスト, Edge Swarm
- **Phase 5** (完了): 知覚・情報統合 — VLM シーン理解, ニュースブリーフィング, イベント自動化, Ollama ネイティブ API
- **Phase 6** (完了): Advanced TTS — VoiSona Talk
- **Phase 7** (完了): ナレッジ・対話 — knowledge-bridge (ハイブリッド検索), パーソナライズドチャット, STT
- **Phase 8** (計画中): SSEストリーミング応答, コマンドモード (チャットからデバイス操作), 会話サマリ圧縮, ユーザープロファイル学習

## License

HEMS is licensed under the **[PolyForm Noncommercial License 1.0.0](LICENSE)**.

Personal, hobbyist, research, educational, and other **noncommercial** use on your own hardware is permitted. See the LICENSE file or <https://polyformproject.org/licenses/noncommercial/1.0.0/> for the full terms.

### Commercial use

**Commercial use** — including bundling HEMS with hardware for sale, redistribution as part of a product, or offering HEMS as a service — is **not permitted under the public license**. Commercial use requires a separate, written commercial license agreement with the author. Contact the author via this repository to inquire about commercial licensing terms.

The software is provided **as is, without warranty or support obligation**.
