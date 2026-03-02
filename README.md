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

- **環境管理**: 温度・CO2・湿度センサーからの自動タスク生成
- **アラート抑制**: タスク作成後の重複生成を防止 (温度30分・CO2 10分)
- **AI キャラクター**: YAML 定義の人格 (ツンデレ、優しい先輩、執事等) + ホットリロード
- **プラグイン式 TTS**: espeak / VOICEVOX / Edge TTS (VoiSona Talk・Style-Bert-VITS2 は計画中)
- **XP ゲーミフィケーション**: タスク完了で XP 獲得
- **ルールベースフォールバック**: GPU 高負荷時に LLM なしで動作
- **PC/サービス監視**: Gmail・GitHub 未読数、CPU/GPU メトリクスを LLM に提供 (OpenClaw)
- **ナレッジストア**: Obsidian vault 連携 — 検索・書込・決定ログ自動記録
- **Google 連携**: Calendar・Tasks・Gmail・Sheets・Drive (GAS Bridge)
- **スマートホーム**: Home Assistant 経由の照明/空調/カバー制御 + スケジュール学習
- **バイオメトリクス**: Gadgetbridge 連携 — 心拍/睡眠/ストレス/疲労スコア
- **カメラ知覚**: YOLOv11s-pose — 在室検知・姿勢分類・活動追跡
- **拡張トラッキング**: HRV・体温・呼吸数・スクリーンタイム
- **データマート**: SOMS 互換の event_store (将来的連携対応)

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                   HEMS Core (常時)                    │
├─────────────┬──────────┬─────────┬───────────────────┤
│  mosquitto  │  brain   │ backend │     frontend      │
│  (MQTT)     │  (LLM/   │ (API+   │     (React)       │
│             │  Rule)   │ Points) │                   │
├─────────────┼──────────┴─────────┼───────────────────┤
│voice-service│                    │     mock-llm      │
│  (TTS)      │                    │     (dev)         │
└─────────────┴────────────────────┴───────────────────┘

Optional: voicevox | ollama | postgres | openclaw | obsidian
         | gas | ha | biometric | perception
```

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

## Optional Profiles

```bash
# VOICEVOX (高品質日本語 TTS)
docker compose --profile voicevox up -d
# → .env: TTS_PROVIDER=voicevox

# Ollama (ローカル LLM)
docker compose --profile ollama up -d
# → .env: LLM_API_URL=http://ollama:11434/v1

# PostgreSQL (SQLite の代替)
docker compose --profile postgres up -d

# OpenClaw (PC メトリクス + Gmail/GitHub 監視)
docker compose --profile openclaw up -d

# Obsidian (ナレッジストア)
docker compose --profile obsidian up -d

# GAS (Google Calendar/Tasks/Gmail/Sheets/Drive)
docker compose --profile gas up -d

# Home Assistant (スマートホーム制御)
docker compose --profile ha up -d

# Biometric (スマートバンド心拍/睡眠)
docker compose --profile biometric up -d

# Perception (カメラ検知 + 活動追跡)
docker compose --profile perception up -d
```

## Roadmap

- **Phase 1** (完了): Core MVP — Backend + Brain + Voice + Frontend + Character + Alert Suppression
- **Phase 2** (完了): 外部連携 — OpenClaw, Obsidian, GAS, Home Assistant, Biometric
- **Phase 3** (完了): Perception — カメラ検知・姿勢分類・活動追跡 (YOLOv11s-pose)
- **Phase 4** (計画中): Advanced TTS — VoiSona Talk, Style-Bert-VITS2

## License

Private project.
