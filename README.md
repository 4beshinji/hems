# HEMS — Home Environment Management System

個人生活統合管理システム。LLM/ルールベースの「頭脳」と IoT センサー、プラグイン式音声合成、
AI キャラクターシステムを組み合わせた、独居者向けパーソナル AI アシスタント基盤。

[SOMS](https://github.com/...) (commit `1216952`) からのフォーク。

## Quick Start

```bash
cp env.example .env
cd infra
docker compose up -d --build
```

- Dashboard: http://localhost:8080
- Backend API: http://localhost:8010/docs
- Voice API: http://localhost:8012/docs

## Features

### コア機能

- **ReAct 認知ループ**: 30秒サイクル・最大5イテレーションの LLM 推論 + ルールベースフォールバック
- **アラート抑制**: タスク作成後の重複生成を防止 (温度30分・CO2 10分)
- **AI キャラクター**: YAML 定義の人格 (5テンプレート) + ホットリロード
- **プラグイン式 TTS**: espeak / VOICEVOX / Edge TTS / VoiSona Talk
- **XP ゲーミフィケーション**: タスク完了で XP 獲得 (50-500)
- **買い物リスト**: Brain 統合のショッピング管理 + 購入履歴 + MQTT通知
- **データマート**: SOMS 互換の event_store — raw_events / llm_decisions / hourly_aggregates (730日保持)

### 外部連携

- **PC/サービス監視** (localcraw): CPU/GPU/メモリ/ディスク + Gmail・GitHub 未読エッジトリガー
- **ナレッジストア** (Obsidian): vault 連携 — 検索・書込・決定ログ自動記録
- **Google 連携** (GAS): Calendar・Tasks・Gmail・Sheets・Drive
- **スマートホーム** (HA): 照明/空調/カバー/スイッチ/センサー/シーン + スケジュール学習
- **SwitchBot** (直接API): HA不要のデバイス制御 + IR リモート (Hub経由)
- **天気** (weather-bridge): JMA (気象庁) / OpenWeatherMap — 降雨・猛暑アラート

### バイオメトリクス・パーセプション

- **バイオメトリクス**: Gadgetbridge webhook — 心拍/SpO2/睡眠/ストレス/疲労スコア/HRV/体温/呼吸数
- **カメラ知覚**: YOLOv11s-pose — 在室検知・姿勢分類 (立位/座位/臥位/歩行)・活動追跡

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
│              │  Rule)   │ Shopping)│                     │
├──────────────┼──────────┴──────────┼─────────────────────┤
│ voice-service│                     │      mock-llm       │
│  (TTS×4)     │                     │      (dev)          │
└──────────────┴─────────────────────┴─────────────────────┘

Profiles:  voicevox | ollama | postgres | localcraw | obsidian
           gas | ha | biometric | perception | switchbot
```

### Brain ツール一覧 (30+)

| カテゴリ | ツール | Profile |
|---------|--------|---------|
| 基本 | `create_task`, `speak`, `get_active_tasks`, `get_zone_status`, `get_device_status`, `send_device_command` | 常時 |
| 買い物 | `add_shopping_item`, `get_shopping_list` | 常時 |
| PC | `get_pc_status`, `run_pc_command`, `control_browser`, `send_pc_notification` | localcraw |
| サービス | `get_service_status` | localcraw |
| ナレッジ | `search_notes`, `write_note`, `get_recent_notes` | obsidian |
| スマートホーム | `control_light`, `control_climate`, `control_cover`, `control_switch`, `get_home_devices`, `get_sensor_data`, `execute_scene` | ha |
| システム | `set_guest_mode`, `get_weather` | ha |
| バイオ | `get_biometrics`, `get_sleep_summary` | biometric |
| カメラ | `get_perception_status` | perception |
| SwitchBot | `get_switchbot_devices`, `control_switchbot`, `send_switchbot_ir` | switchbot |

### サービスポート

| Service | Port | Container |
|---------|------|-----------|
| Frontend | 8080 | hems-frontend |
| Backend API | 8010 | hems-backend |
| Mock LLM | 8011 | hems-mock-llm |
| Voice | 8012 | hems-voice |
| localcraw | 8013 | hems-localcraw-bridge |
| Obsidian | 8014 | hems-obsidian-bridge |
| GAS | 8015 | hems-gas-bridge |
| HA | 8016 | hems-ha-bridge |
| Biometric | 8017 | hems-biometric-bridge |
| Perception | 8018 | hems-perception |
| SwitchBot | 8019 | hems-switchbot-bridge |
| VOICEVOX | 50031 | hems-voicevox |
| Ollama | 11444 | hems-ollama |
| PostgreSQL | 5442 | hems-postgres |
| MQTT | 1893 | hems-mqtt |

ポートは `HEMS_PORT_*` 環境変数でカスタマイズ可能。

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
| `ena` | エナ | 0 | ハイテンションデジタル居候 (デフォルト) |
| `default` | 私 | 2 | フレンドリーアシスタント |
| `tsundere` | あたし | 0 | 素直になれない、世話好き |
| `gentle-senpai` | 私 | 1 | 穏やか、褒め上手 |
| `butler` | わたくし | 4 | 完璧主義、品格 |

バリデーション: `python validate_character.py --all`

## Optional Profiles

```bash
# VOICEVOX (高品質日本語 TTS)
docker compose --profile voicevox up -d
# → .env: TTS_PROVIDER=voicevox

# Ollama (ローカル LLM — GPU自動検出)
python infra/scripts/gpu_setup.py   # docker-compose.gpu.yml 生成
docker compose --profile ollama up -d
# → .env: LLM_API_URL=http://ollama:11434/v1

# PostgreSQL (SQLite の代替)
docker compose --profile postgres up -d

# localcraw (PC メトリクス + Gmail/GitHub 監視)
docker compose --profile localcraw up -d

# Obsidian (ナレッジストア)
docker compose --profile obsidian up -d

# GAS (Google Calendar/Tasks/Gmail/Sheets/Drive)
docker compose --profile gas up -d

# Home Assistant (スマートホーム制御 + スケジュール学習)
docker compose --profile ha up -d

# Biometric (スマートバンド心拍/睡眠/疲労スコア)
docker compose --profile biometric up -d

# Perception (YOLOv11s-pose カメラ検知 + 活動追跡)
docker compose --profile perception up -d

# SwitchBot (直接API制御 — HA不要)
docker compose --profile switchbot up -d

# 複数プロファイル組み合わせ
docker compose --profile ha --profile biometric --profile switchbot up -d
```

## Frontend

React 19 + TypeScript + Tailwind CSS 4 + TanStack Query + Framer Motion

| ページ | 内容 |
|--------|------|
| Dashboard | タスク一覧、XP、直近の Brain 判断、音声イベント |
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
| LLM | OpenAI / Anthropic / Ollama (マルチプロバイダー) |
| TTS | espeak-ng, VOICEVOX, Edge TTS, VoiSona Talk |
| DB | SQLite (default) / PostgreSQL 16 |
| Infra | Docker Compose, Mosquitto MQTT |
| Edge | MicroPython (ESP32), SensorSwarm バイナリプロトコル |

## Documentation

| ドキュメント | 内容 |
|-------------|------|
| [SMART_HOME_SETUP.md](docs/SMART_HOME_SETUP.md) | Home Assistant + HEMS 統合セットアップ |
| [smart-home-device-guide.md](docs/smart-home-device-guide.md) | マルチプロトコルデバイス総合ガイド |
| [sensor-purchasing-guide-jp.md](docs/sensor-purchasing-guide-jp.md) | センサー購入ガイド (技適準拠・Amazon.co.jp) |
| [sensor-purchasing-guide-aliexpress.md](docs/sensor-purchasing-guide-aliexpress.md) | センサー購入ガイド (AliExpress・コスト最優先) |
| [smartband-setup.md](docs/smartband-setup.md) | スマートバンドセットアップ |
| [voisona-talk-setup.md](docs/voisona-talk-setup.md) | VoiSona Talk TTS セットアップ |

## Roadmap

- **Phase 1** (完了): Core MVP — Backend + Brain + Voice + Frontend + Character + Alert Suppression
- **Phase 2** (完了): 外部連携 — localcraw, Obsidian, GAS, Home Assistant, Biometric
- **Phase 3** (完了): Perception — カメラ検知・姿勢分類・活動追跡 (YOLOv11s-pose)
- **Phase 4** (完了): IoT拡張 — SwitchBot直接統合, Weather Bridge, 買い物リスト, Edge Swarm
- **Phase 5** (進行中): Advanced TTS — VoiSona Talk 実装済み, Style-Bert-VITS2 計画中

## License

Private project.
