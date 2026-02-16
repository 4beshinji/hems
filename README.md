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

- Dashboard: http://localhost
- Backend API: http://localhost:8000/docs
- Voice API: http://localhost:8002/docs

## Features

- **環境管理**: 温度・CO2・湿度センサーからの自動タスク生成
- **AI キャラクター**: YAML 定義の人格 (ツンデレ、優しい先輩、執事等) + ホットリロード
- **プラグイン式 TTS**: espeak / VOICEVOX / Edge TTS / VoiSona Talk / Style-Bert-VITS2
- **XP ゲーミフィケーション**: タスク完了で XP 獲得
- **ルールベースフォールバック**: GPU 高負荷時に LLM なしで動作
- **データマート**: SOMS 互換の event_store (将来的連携対応)

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  HEMS Core (常時)                 │
├─────────────┬──────────┬────────┬───────────────┤
│  mosquitto  │  brain   │backend │   frontend    │
│  (MQTT)     │  (LLM/   │(API+   │   (React)     │
│             │  Rule)   │Points) │               │
├─────────────┼──────────┴────────┼───────────────┤
│voice-service│                   │   mock-llm    │
│  (TTS)      │                   │   (dev)       │
└─────────────┴───────────────────┴───────────────┘

Optional: voicevox | ollama | perception | postgres
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
| `default` | 私 | 2 | フレンドリーアシスタント |
| `tsundere` | あたし | 0 | 素直になれない、世話好き |
| `gentle-senpai` | 私 | 1 | 穏やか、褒め上手 |
| `butler` | わたくし | 4 | 完璧主義、品格 |

## Optional Profiles

```bash
# VOICEVOX (高品質日本語 TTS)
docker compose --profile voicevox up -d
# → .env: TTS_PROVIDER=voicevox

# Ollama (ローカル LLM, AMD ROCm)
docker compose --profile ollama up -d
# → .env: LLM_API_URL=http://ollama:11434/v1

# PostgreSQL (SQLite の代替)
docker compose --profile postgres up -d
# → .env: DATABASE_URL=postgresql+asyncpg://hems:hems_dev_password@postgres:5432/hems
```

## Roadmap

- **Phase 1** (Current): Core MVP — Backend + Brain + Voice + Frontend + Character
- **Phase 2**: External integrations — Google Calendar, Strava, Mi Band, GPU monitor
- **Phase 3**: Perception — USB Webcam auto-detection, occupancy monitoring
- **Phase 4**: Advanced TTS — VoiSona Talk, Style-Bert-VITS2

## License

Private project.
