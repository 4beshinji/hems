<!--
HISTORICAL (2026-06-11): これは 2025 年下期の HEMS 外部説明用スライドです。
掲載内容は概ね現在の構成と一致するが、UI/UX・サービスセット・性能数字は
実装進化に伴い変化しています。最新情報は README.md および
docs/README.md を参照。
-->
---
marp: true
theme: uncover
paginate: true
backgroundColor: #0a0a0a
color: #e0e0e0
style: |
  section {
    font-family: 'Noto Sans JP', 'Noto Sans CJK JP', 'Hiragino Kaku Gothic Pro', sans-serif;
    font-size: 28px;
    padding: 50px 60px;
  }
  h1 {
    color: #60a5fa;
    font-size: 48px;
    margin-bottom: 20px;
  }
  h2 {
    color: #93c5fd;
    font-size: 38px;
    margin-bottom: 16px;
  }
  h3 {
    color: #bfdbfe;
    font-size: 30px;
  }
  strong {
    color: #60a5fa;
  }
  table {
    font-size: 22px;
    margin: 0 auto;
  }
  th {
    background-color: #1e3a5f;
    color: #93c5fd;
  }
  td, th {
    padding: 8px 16px;
    border: 1px solid #334155;
  }
  code {
    background-color: #1e293b;
    color: #7dd3fc;
    font-size: 22px;
    padding: 2px 6px;
    border-radius: 4px;
  }
  pre {
    background-color: #0f172a;
    border: 1px solid #1e3a5f;
    border-radius: 8px;
    padding: 20px;
    font-size: 18px;
  }
  pre code {
    background: none;
    padding: 0;
  }
  blockquote {
    border-left: 4px solid #60a5fa;
    padding: 12px 20px;
    background-color: #0f172a;
    font-size: 26px;
  }
  a {
    color: #60a5fa;
  }
  section.lead h1 {
    font-size: 56px;
    text-align: center;
  }
  section.lead p {
    text-align: center;
    font-size: 28px;
  }
  .columns {
    display: flex;
    gap: 30px;
  }
  .columns > div {
    flex: 1;
  }
  footer {
    color: #475569;
    font-size: 14px;
  }
---

<!-- _class: lead -->

# HEMS

**Home Environment Management System**
三空間統合型パーソナル AI 基盤

---

## 問題

スマートホームは**部屋**しか見ない
AI アシスタントは**会話**しかできない
PC 監視ツールは**マシン**しか知らない

<br>

これらは**それぞれ別のアプリ**で、互いに情報を共有しない。
ユーザーの生活は 1 つなのに、ツールはバラバラ。

---

## HEMS の回答

> **実空間・個人電子空間・インターネット**を
> 1 つの認知エンジンに統合する

30秒サイクルの自律判断ループ。
聞かれなくても、三空間の状態を走査し、判断し、行動する。

---

## 三空間とは

| 実空間 | 個人電子空間 | インターネット |
|--------|-------------|--------------|
| 温湿度 / CO2 / VOC | PC CPU/GPU/メモリ | Google Calendar |
| 気圧 / 照度 | プロセス監視 | Gmail 未読 |
| 赤外線 / ミリ波 | ブラウザ状態 | GitHub 通知 |
| カメラ (YOLO+VLM) | Obsidian vault | RSS ニュース |
| スマートホーム状態 | スクリーンタイム | 天気予報 (JMA) |
| 心拍 / SpO2 / HRV | 買い物リスト | |
| 睡眠 / ストレス / 疲労 | | |

---

## アーキテクチャ

```
   実空間              個人電子空間           インターネット
   ──────             ──────────           ──────────
   BME680/CO2          localcraw            GAS Bridge
   PIR/mmWave          Obsidian             News Bridge
   YOLO + VLM          PC metrics           Weather
   HA / SwitchBot                           RSS / API
   Gadgetbridge
        │                  │                    │
        └──────────── MQTT Bus ─────────────────┘
                           │
                    ┌──────┴──────┐
                    │    Brain    │
                    │  LLM ReAct  │
                    │  + Rules    │
                    │  + 33 tools │
                    └──────┬──────┘
                           │
               ┌───────────┼───────────┐
               ▼           ▼           ▼
          照明/空調     音声通知     タスク生成
          デバイス制御   PC操作      ニュース要約
```

---

## センサースタック

「お前を見ているぞ」— 6 モダリティで死角を潰す

| レイヤー | センサー | 検知対象 |
|---------|---------|---------|
| 環境 | BME680, MH-Z19 | 空気質・気圧変動 |
| 赤外線 | PIR | 動体検知 |
| ミリ波 | 24GHz mmWave | 存在 + 微動 (呼吸) |
| 映像 | YOLOv11s-pose | 人数・姿勢・骨格 |
| 映像+言語 | VLM | **シーン理解・状況記述** |
| 生体 | スマートバンド | 心拍/睡眠/ストレス/疲労 |

---

## VLM の役割 — センサーが取れない「文脈」

他のセンサー → **数値**
VLM → **状況の言語記述**

<br>

| センサー | 出力 |
|---------|------|
| PIR + mmWave | 「誰かがソファにいる」 |
| YOLO | 「1人、臥位」 |
| **VLM** | **「横臥状態。照明点灯中。リモコン落下」** |

<br>

→ Brain の判断材料が「臥位」から **「寝落ちの可能性が高い」** に変わる

---

## VLM 適応的頻度制御

推論コストが高い VLM を状況に応じて使い分ける

```
通常時:       30分に1回 (軽量: moondream ~1.8B)
人の出入り:    1-5分間隔にブースト (重量: minicpm-v ~3B)
無人・安定:    最大2時間間隔に減衰
オンデマンド:   Brain が describe_scene で任意に呼び出し
```

<br>

GPU 協調: VLM 推論中は Brain LLM を自動退避 → ルールエンジンにフォールバック

---

## デモ 1: 三空間の複合判断

```
14:30  [実空間]    CO2 1200ppm, 室温 28°C
       [実空間]    YOLO: 座位を2時間継続
       [電子空間]  GPU 95% (推論中)
       [生体]      心拍 95bpm (通常より高め)

       → Brain (ReAct):
         Thought: CO2高い + 暑い + 長時間座位 + 心拍上昇
                  GPU高負荷で排熱も影響
                  → 換気 + 冷房強化 + 休憩促進
         Action:  control_climate(mode=cool, temp=25)
                  speak("2時間経過。換気と休憩を推奨します")
```

---

## デモ 2: VLM によるセンサー補完

```
23:45  [実空間]    PIR: 反応なし (静止)
       [実空間]    mmWave: 存在あり (微動=呼吸)
       [実空間]    YOLO: 1人・臥位 (ソファ上)
       [実空間]    VLM: 「横臥。照明点灯。リモコン落下」
       [生体]      心拍 58bpm (低下傾向)

       → Brain: 寝落ちと判断
         Action:  control_light(brightness=0)
                  speak("就寝を検知。消灯します", volume=0.3)
```

---

## デモ 3: インターネット空間との連携

```
07:00  [生体]         睡眠終了を検知 → wake_up イベント
       [インターネット] ニュース要約 (RSS + Ollama)
       [インターネット] 天気: 午後から降雨予測
       [電子空間]      GitHub: PR レビュー 3件

       → イベント自動化:
         1. 天気レポート (降雨アラート)
         2. ニュースブリーフィング
         3. 未読通知サマリー
       → 音声で一括通知
```

---

## 既存アプローチとの比較

| | ローカル LLM | opencraw | AI 秘書 | **HEMS** |
|---|---|---|---|---|
| 認知範囲 | なし | PC 1台 | 音声のみ | **三空間** |
| 自律判断 | なし | 閾値のみ | なし | **LLM + Rules** |
| デバイス制御 | なし | 通知のみ | 限定的 | **HA + SwitchBot + MQTT** |
| プライバシー | ローカル | ローカル | クラウド | **完全ローカル** |
| カスタマイズ | prompt | 設定 | 不可 | **オープン** |

---

## ポジショニング

```
        自律性 (聞かれなくても行動する)
          ▲
          │            ┌──────┐
          │            │ HEMS │
          │            └──────┘
          │   ┌──────────┐
          │   │Home Asst.│
          │   └──────────┘
          │                     ┌──────────┐
          │                     │ AI 秘書  │
          │                     └──────────┘
          │ ┌──────────┐
          │ │opencraw  │
          │ └──────────┘
          │           ┌──────────┐
          │           │ローカルLLM│
          │           └──────────┘
          └─────────────────────────────────► 認知範囲
             PC のみ    部屋     三空間統合
```

---

## 数字

| | |
|---|---|
| 統合空間 | **3** (実空間 / 個人電子空間 / インターネット) |
| マイクロサービス | **18** |
| Brain ツール | **33** |
| センサーモダリティ | **6** |
| 認知ループ | **30 秒** |
| LLM プロバイダー | **3** (OpenAI / Anthropic / Ollama) |
| データ保持 | **730 日** |
| 起動コマンド | **1** (`docker compose up`) |

---

## 段階的導入

```bash
# Step 1: 最小構成 (5分)
cp env.example .env
cd infra && docker compose up -d --build

# Step 2: ローカル LLM
docker compose --profile ollama up -d --build

# Step 3: スマートホーム + 生体 + カメラ + ニュース
docker compose --profile ha --profile biometric \
  --profile perception --profile news \
  --profile ollama up -d --build
```

使うものだけプロファイルで有効化。

---

<!-- _class: lead -->

# 三空間を、1 つの判断に。

**HEMS — Home Environment Management System**

Python 3.11 / FastAPI / React 19 / Docker Compose / MQTT / Ollama
