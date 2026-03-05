# HEMS スマートホームデバイスガイド（日本向け）

> 作成日: 2026-03-03 (Zigbee版)
> 改訂日: 2026-03-05 (マルチプロトコル対応 — SwitchBot/Nature Remo/Aqara追加、日本入手性・Type A対応整理)
> 対象: 単身居住者向け Home Assistant + HEMS 構成

## 目次

1. [プロトコル戦略](#1-プロトコル戦略)
2. [アーキテクチャ概要](#2-アーキテクチャ概要)
3. [デバイスカタログ](#3-デバイスカタログ)
4. [推奨構成パッケージ](#4-推奨構成パッケージ)
5. [HEMS 機能拡張ロードマップ](#5-hems-機能拡張ロードマップ)
6. [設置ゾーン別プラン](#6-設置ゾーン別プラン)
7. [購入ガイド](#7-購入ガイド)

---

## 1. プロトコル戦略

### 1.1 日本のスマートホームプロトコル比較

| プロトコル | 利点 | 欠点 | 日本での状況 |
|---|---|---|---|
| **Zigbee 3.0** | メッシュ、低消費電力、ローカル制御、安価 | コーディネーター必要 | SONOFF一部は技適+PSE済。Aqara Amazon.co.jp正規販売 |
| **BLE+Wi-Fi (SwitchBot)** | 日本最大シェア、即購入可、PSE済 | Hub必須、BLE距離制限 | 事実上のデファクト |
| **Wi-Fi (Tapo等)** | Hub不要、安価 | メッシュなし、ルーター負荷 | Tapo/Meross Amazon.co.jpで多数 |
| **Matter** | 統一規格、ローカル制御 | 発展途上、デバイス種類少 | SwitchBot Hub 2/3/AI Hub、Nature Remo Lapis対応 |
| **ECHONET Lite** | 日本家電メーカー標準、政府推奨 | センサー/スイッチ非対応 | HA連携はHACS/Matter-ENLブリッジ |

### 1.2 推奨構成: ハイブリッド

| 層 | プロトコル | 用途 | 理由 |
|---|---|---|---|
| **センサー** | Zigbee (Aqara/SONOFF) | 温湿度、ドア、人感、水漏れ | 安価・長寿命・メッシュ・ローカル制御 |
| **アクチュエーター** | SwitchBot (BLE) | カーテン、ロック、ボット | Zigbee同等品なし、日本入手性最良 |
| **IRリモコン** | Nature Remo or SwitchBot Hub | エアコン、TV | Matter対応、HA公式統合 |
| **スマートプラグ** | Wi-Fi (Tapo) or Zigbee | 電力監視、家電制御 | Type A対応品が豊富 |
| **家電制御** | ECHONET Lite | 日本メーカーHVAC | 政府補助金要件 |

### 1.3 HEMSコードのプロトコル非依存性

HEMSはプロトコル非依存。ha-bridgeがHome Assistant APIを中継するため、裏のプロトコル（Zigbee/BLE/Wi-Fi/Matter）に関わらず、HAでエンティティ化されればHEMSコード変更は不要。

```
任意プロトコル → [Home Assistant] → REST/WebSocket → [ha-bridge] → MQTT → [Brain WorldModel]
```

rule_engine.pyの「Zigbee」命名は便宜的。実際には`device_class`属性で判別しており、全プロトコル共通。

---

## 2. アーキテクチャ概要

```
┌─────────────────────────────────────────────────────────┐
│  Zigbee Devices (Aqara/SONOFF sensors, switches)        │
└──────────────────────┬──────────────────────────────────┘
                       │ Zigbee 3.0 (2.4GHz mesh)
                       ▼
              ┌────────────────┐
              │ SONOFF Dongle-E│  USB coordinator
              │ or HA ZBT-2    │
              └───────┬────────┘
                      │ Serial (ZHA or Zigbee2MQTT)
                      ▼
┌─────────────────────────────────────────────┐
│  SwitchBot (BLE)    │  Nature Remo (Wi-Fi)  │
│  Bot/Curtain/Lock   │  IR Blaster (Matter)  │
│  via BLE or Hub→    │                       │
│  Matter bridge      │                       │
└─────────┬───────────┴──────────┬────────────┘
          │                      │
          ▼                      ▼
            ┌──────────────────┐
            │  Home Assistant  │  state_changed events
            └────────┬─────────┘
                     │ WebSocket + REST
                     ▼
            ┌──────────────────┐
            │  HEMS ha-bridge  │  port 8016
            └────────┬─────────┘
                     │ MQTT → hems/home/{zone}/{domain}/{entity}/state
                     ▼
            ┌──────────────────┐
            │  HEMS Brain      │  WorldModel → RuleEngine → Tools
            └──────────────────┘
```

---

## 3. デバイスカタログ

凡例:
- **入手性**: JP = Amazon.co.jp、AE = AliExpress
- **技適/PSE**: 済 = 確認済、- = 不要 or 未確認
- **推奨** = カテゴリ内ベスト（コスパ・入手性・HA連携の総合評価）

### 3.1 Zigbeeコーディネーター

| 製品 | チップ | アンテナ | 価格 | 入手 | 備考 |
|------|--------|---------|------|------|------|
| **SONOFF ZBDongle-E** (推奨) | EFR32MG21 | 3.0dBi | ~¥2,500 | JP/AE | コスパ最強、100台以下なら十分 |
| SONOFF Dongle Plus MG24 | EFR32MG24 | 4.5dBi | ~¥3,000-3,500 | JP/AE | 最新チップ、最強アンテナ |
| HA Connect ZBT-2 | EFR32MG24 | 外部 | ~¥7,000 ($49) | 海外通販 | HA公式、Thread/Matter対応、ESP32-S3コプロセッサ |

> USB延長ケーブル（1-2m）でサーバーのRFノイズから離して設置すること。

---

### 3.2 温湿度センサー

用途: 各ゾーンの環境モニタリング、エアコン自動制御の入力データ

| 製品 | プロトコル | 精度 | 電池寿命 | 価格 | 入手 | HA連携 |
|------|----------|------|---------|------|------|--------|
| **Aqara WSDCGQ11LM** (推奨) | Zigbee | ±0.3°C/±3%RH | CR2032 ~2年 | ~¥2,980 | **JP** | ZHA/Z2M |
| SONOFF SNZB-02P | Zigbee | ±0.2°C/±2%RH | CR2477 ~4年 | ~¥1,000 | AE | ZHA/Z2M |
| SONOFF SNZB-02D (LCD付) | Zigbee | ±0.2°C/±2%RH | CR2450 ~2年 | ~¥1,400 | AE | ZHA/Z2M |
| SwitchBot 温湿度計 | BLE | ±0.4°C/±2%RH | 単4x2 ~1年 | ~¥1,980 | **JP** | BLE/Matter |
| SwitchBot CO2センサー | BLE+Wi-Fi | CO2+温湿度 | USB給電 | ~¥7,980 | **JP** | BLE/Matter |

**HEMS連携**: `hems/home/{zone}/sensor/sensor.{name}_temperature/state` に自動反映。30分温度アラート抑制が実装済み。

---

### 3.3 人感・在室センサー

用途: 在室検知、スケジュール学習、睡眠検知

#### PIRセンサー（動体検知）

| 製品 | プロトコル | 検知角度/距離 | 電池寿命 | 価格 | 入手 |
|------|----------|-------------|---------|------|------|
| **Aqara RTCGQ11LM** (推奨) | Zigbee | 170°/7m | CR2450 ~2年 | ~¥2,980 | **JP** |
| SwitchBot 人感センサー | BLE | 110°/9m | 単4x2 ~3年 | ~¥2,980 | **JP** |
| SONOFF SNZB-03P | Zigbee | 110°/6m | CR2477 ~3年 | ~¥1,200 | AE |

#### mmWaveセンサー（静止人体検知）

| 製品 | プロトコル | 検知距離 | 電源 | 価格 | 入手 |
|------|----------|---------|------|------|------|
| **Aqara FP2** (推奨) | Wi-Fi | ~8m、ゾーン検知 | USB-C | ~¥7,000-9,000 | **JP** |
| SwitchBot 人感センサーPro | BLE | mmWave | USB | ~¥3,980 | **JP** |
| Tuya ZY-M100 | Zigbee | ~5m | USB 5V | ~¥3,000 | AE |

**PIR vs mmWave**: PIRは動く人のみ検知、mmWaveは座り仕事中も検知（呼吸レベル）。主要居室にmmWave、廊下/トイレにPIR推奨。

---

### 3.4 ドア・窓センサー

用途: 到着/出発検知、換気状態追跡

| 製品 | プロトコル | 電池寿命 | 価格 | 入手 | HA連携 |
|------|----------|---------|------|------|--------|
| **Aqara MCCGQ11LM** (推奨) | Zigbee | CR1632 ~2年 | ~¥2,980 | **JP** | ZHA/Z2M |
| Aqara P2 (Matter/Thread) | Thread | CR2477 ~5年 | ~¥4,480 | **JP** | Matter |
| SwitchBot 開閉センサー | BLE | 単4x2 ~3年 | ~¥2,480 | **JP** | BLE/Matter |
| SONOFF SNZB-04P | Zigbee | CR2477 ~5年 | ~¥1,000 | AE | ZHA/Z2M |

**HEMS連携**: 玄関ドアセンサーはScheduleLearnerの到着/出発パターン学習に直接貢献。

---

### 3.5 スマートプラグ（日本Type A対応品）

用途: 家電制御、消費電力監視、Zigbeeルーター

> 全製品が日本のType Aコンセント対応・PSE認証済み（Amazon.co.jp販売品）

| 製品 | プロトコル | 電力計測 | Matter | 価格 | 入手 |
|------|----------|---------|--------|------|------|
| **TP-Link Tapo P110M** (推奨) | Wi-Fi | W/kWh | 対応 | ~¥1,160 | **JP** |
| SwitchBot プラグミニ | Wi-Fi+BLE | W/kWh | Hub経由 | ~¥1,980 | **JP** |
| Meross MSS310JP | Wi-Fi | W/kWh | - | ~¥1,790 | **JP** |
| TP-Link Tapo P105 | Wi-Fi | なし | - | ~¥900 | **JP** |
| **SONOFF S60ZBTPB** (Zigbee唯一) | **Zigbee** | W/kWh | - | ~¥2,000 | **AEのみ** |

**重要**: Zigbeeの日本Type Aプラグは**SONOFF S60ZBTPBのみ**。技適+PSE済だがAliExpress限定。Amazon.co.jpで買うならWi-Fi/Matter品を選択。

**HEMS連携**:
- 電力データ → WorldModelに反映
- 洗濯機のW値変化で完了検知 → `create_task` + `speak`で通知
- Zigbeeプラグ → ルーターとしてメッシュ強化

---

### 3.6 IRブラスター（スマートリモコン）

用途: エアコン・TV・扇風機などの赤外線家電制御

| 製品 | プロトコル | Matter | センサー | 価格 | 入手 | HA連携 |
|------|----------|--------|---------|------|------|--------|
| **Nature Remo nano** (推奨) | Wi-Fi+IR | 対応 (3台) | なし | ~¥3,980 | **JP** | **Matter native** |
| Nature Remo Lapis | Wi-Fi+BLE+IR | 対応 (20台) | 温湿度 | ~¥7,980 | **JP** | Matter native |
| Nature Remo mini 2 | Wi-Fi+IR | - | 温度のみ | ~¥5,480 | **JP** | HACS (非推奨) |
| SwitchBot Hub 2 | Wi-Fi+BLE+IR | 対応 (8台) | 温湿度+照度 | ~¥9,980 | **JP** | BLE/Matter |
| SwitchBot Hub 3 | Wi-Fi+BLE+IR | 対応 (30台) | 温湿度 | ~¥12,980 | **JP** | BLE/Matter |
| Tuya ZS06 (Zigbee) | Zigbee+IR | - | なし | ~¥1,800 | AE | Z2M経由 |

**HA連携の注意点**:
- Nature Remo: Matter対応機種はHA Matter統合でネイティブ動作。旧HACS統合は3年間未更新 → **nano/Lapisを推奨**
- SwitchBot Hub: SwitchBot BLE統合 or Matter bridge経由でHA連携
- SwitchBot Hubを選ぶ場合、他SwitchBotデバイスのハブも兼ねるため一石二鳥

**HEMS連携**: HAで`climate.*`エンティティとして登録 → `control_climate`ツールでそのまま制御可能。コード変更不要。

---

### 3.7 スマートライト

用途: 照明自動制御、色温度調整、疲労時減光

#### 電球

| 製品 | プロトコル | スペック | 価格 | 入手 |
|------|----------|---------|------|------|
| **SwitchBot LED電球** (推奨) | BLE+Wi-Fi | E26 RGB+CW | ~¥1,980 | **JP** |
| Tuya E27 RGBCCT | Zigbee | 9W 800lm | ~¥1,200 | AE |

#### シーリングライト

| 製品 | プロトコル | スペック | 価格 | 入手 |
|------|----------|---------|------|------|
| **SwitchBot シーリングライトPro** | BLE+Wi-Fi+IR | 6畳/8畳、**IRハブ内蔵** | ~¥9,980/¥11,980 | **JP** |

> SwitchBotシーリングライトProはIRハブ機能内蔵。別途ハブ購入不要でエアコン等を制御可能。

#### LEDストリップ

| 製品 | プロトコル | 価格 | 入手 |
|------|----------|------|------|
| SwitchBot テープライト | BLE+Wi-Fi | ~¥2,480 | **JP** |
| Gledopto GL-C-001P | Zigbee | ~¥2,000 | AE |

**HEMS連携**: `control_light(brightness, color_temp)` で直接制御。既存ルール:
- 疲労時減光: 21-23時 + 疲労スコア>60 → brightness=80, color_temp=400
- 睡眠検知: 全照明OFF
- 起床検知: brightness=255

---

### 3.8 スマートリレー/スイッチ

用途: 既存壁スイッチの裏に設置、見た目変更なしでスマート化

| 製品 | プロトコル | 中性線 | 定格 | 価格 | 入手 |
|------|----------|--------|------|------|------|
| **SwitchBot Relay Switch 1PM** (推奨) | Wi-Fi (Matter native) | - | 電力計測付 | ~¥3,980 | **JP** |
| SONOFF ZBMINI-L2 | Zigbee | 不要 | 6A/1320W | ~¥1,400 | AE |
| SONOFF ZBMINIR2 | Zigbee | 必要 | 10A/2200W | ~¥1,200 | AE |

> 日本の住宅は中性線なしが多い → ZBMINI-L2推奨（Zigbee選択時）。SwitchBot Relay Switchは日本仕様でMatter native対応。

---

### 3.9 カーテン/ブラインドモーター

用途: 起床時自動開放、就寝時自動閉鎖

| 製品 | プロトコル | タイプ | 電源 | 価格 | 入手 |
|------|----------|--------|------|------|------|
| **SwitchBot カーテン3** (推奨) | BLE | カーテンレール | 充電池+ソーラー | ~¥8,980 | **JP** |
| SwitchBot ブラインドポール | BLE | ブラインド | 充電池+ソーラー | ~¥4,980 | **JP** |
| Zemismart AM43 | Zigbee | ローラーブラインド | 充電池+ソーラー | ~¥5,000-7,000 | AE |

> SwitchBotカーテン3は最大16kg、25dB以下の静音動作。日本のカーテンレール規格に対応。ソーラーパネル別売（¥2,980）。

**HEMS連携**: `control_cover(position)` で制御。既存ルール:
- 起床前カーテン開放: ScheduleLearner予測起床時刻の0-60分前
- 睡眠検知: 全閉

---

### 3.10 スマートロック

用途: 施錠/解錠自動化、不在時セキュリティ

| 製品 | プロトコル | 認証方式 | 価格 | 入手 |
|------|----------|---------|------|------|
| **SwitchBot ロックPro** (推奨) | BLE | 指紋/NFCカード/暗証番号 | ~¥17,980 | **JP** |
| SwitchBot ロックUltra | BLE | 3D顔認証 | ~¥29,980 | **JP** |
| SESAME 5 | BLE | アプリ/Apple Watch | ~¥4,980 | **JP** |

> ロックは日本のサムターン規格に対応した製品を選択すること。SwitchBot ロックProはAES-128暗号化。

---

### 3.11 空気質センサー

用途: CO2/PM2.5/VOCモニタリング、換気促進

| 製品 | プロトコル | CO2精度 | 価格 | 入手 |
|------|----------|---------|------|------|
| **SwitchBot CO2センサー** (推奨) | BLE+Wi-Fi | NDIR実測 | ~¥7,980 | **JP** |
| Tuya 6-in-1 Air Box | Zigbee | eCO2(推定値) | ~¥3,500 | AE |
| Heiman HS3AQ | Zigbee | NDIR実測 | ~¥7,000 | AE |

> 安価なセンサーのeCO2はVOCからの推定値。正確なCO2値が必要ならNDIR方式を選択。

---

### 3.12 水漏れセンサー

| 製品 | プロトコル | 電池寿命 | 価格 | 入手 |
|------|----------|---------|------|------|
| SONOFF SNZB-05P | Zigbee | CR2477 ~5年 | ~¥1,200 | AE |
| SwitchBot 水漏れセンサー | BLE | 単4x2 ~2年 | ~¥1,480 | **JP** |

**HEMS連携**: 漏水検知 → urgency=4の緊急タスク生成 + `speak`で音声アラート。実装済み。

---

### 3.13 振動センサー

| 製品 | プロトコル | 電池寿命 | 価格 | 入手 |
|------|----------|---------|------|------|
| **Aqara DJT11LM** | Zigbee | CR2032 ~2年 | ~¥2,500 | **JP** |

**HEMS連携**: 洗濯機に貼付 → 振動停止検知 → `create_task("洗濯物を干す")` + `speak("洗濯が終わりました")`。実装済み。

---

### 3.14 シーンスイッチ/ボタン

| 製品 | プロトコル | ボタン数 | 価格 | 入手 |
|------|----------|---------|------|------|
| SwitchBot リモートボタン | BLE | 1 | ~¥1,980 | **JP** |
| Tuya TS0044 | Zigbee | 4 (各3アクション) | ~¥1,200 | AE |

---

## 4. 推奨構成パッケージ

### パッケージA: Amazon.co.jpスターター（~¥25,000-30,000）

全てAmazon.co.jpで購入可能。AliExpress不要。

| # | 製品 | 数量 | 単価 | 小計 | 役割 |
|---|------|------|------|------|------|
| 1 | SONOFF ZBDongle-E | 1 | ¥2,500 | ¥2,500 | Zigbeeコーディネーター |
| 2 | Aqara 温湿度センサー | 2 | ¥2,980 | ¥5,960 | 環境モニタリング |
| 3 | Aqara 人感センサー | 1 | ¥2,980 | ¥2,980 | 動体検知 |
| 4 | Aqara 開閉センサー | 2 | ¥2,980 | ¥5,960 | ドア/窓 |
| 5 | Nature Remo nano | 1 | ¥3,980 | ¥3,980 | IRリモコン (Matter) |
| 6 | TP-Link Tapo P110M | 2 | ¥1,160 | ¥2,320 | スマートプラグ+電力計測 |
| | | | **合計** | **~¥23,700** | |

**実現可能な機能**:
- 各部屋の温湿度監視 → Brainがエアコン判断
- 在室/不在検知 → ScheduleLearner学習
- 玄関ドア開閉 → 到着/出発パターン学習
- エアコン/TV直接制御 (Matter経由)
- 家電電力モニタリング

---

### パッケージB: SwitchBot主軸セットアップ（~¥45,000-55,000）

SwitchBotエコシステムでアクチュエーター強化。

| # | 製品 | 数量 | 単価 | 小計 | 役割 |
|---|------|------|------|------|------|
| | **= パッケージA =** | | | **¥23,700** | |
| 7 | SwitchBot Hub 3 | 1 | ¥12,980 | ¥12,980 | BLEハブ+Matter bridge+IR |
| 8 | SwitchBot カーテン3 | 2 | ¥8,980 | ¥17,960 | カーテン自動開閉 |
| 9 | SwitchBot リモートボタン | 1 | ¥1,980 | ¥1,980 | 物理ボタンシーン |
| | | | **合計** | **~¥56,620** | |

> Hub 3購入時はNature Remo nanoと役割が重複。Hub 3のIR機能で代替し、nanoを省略可（-¥3,980）。

**追加機能**:
- カーテン自動化（起床/就寝連動）
- SwitchBotデバイス30台までMatter bridge
- 物理ボタンでシーン実行

---

### パッケージC: フルセットアップ（~¥80,000-100,000）

全カテゴリカバー。

| # | 製品 | 数量 | 単価 | 小計 |
|---|------|------|------|------|
| | **= パッケージB (Hub 3版) =** | | | **¥52,640** |
| 10 | Aqara FP2 mmWave | 1 | ¥8,000 | ¥8,000 |
| 11 | SwitchBot ロックPro | 1 | ¥17,980 | ¥17,980 |
| 12 | SwitchBot CO2センサー | 1 | ¥7,980 | ¥7,980 |
| 13 | SwitchBot LED電球 | 2 | ¥1,980 | ¥3,960 |
| 14 | SwitchBot ブラインドポール | 1 | ¥4,980 | ¥4,980 |
| 15 | Aqara DJT11LM 振動 | 1 | ¥2,500 | ¥2,500 |
| | | | **合計** | **~¥98,040** | |

---

### パッケージD: Zigbee最安構成（AliExpress、~¥15,000）

コスト最優先。全てAliExpressから購入。到着まで2-4週間。

| # | 製品 | 数量 | 単価 | 小計 |
|---|------|------|------|------|
| 1 | SONOFF ZBDongle-E | 1 | ¥1,900 | ¥1,900 |
| 2 | SONOFF SNZB-02P | 3 | ¥1,100 | ¥3,300 |
| 3 | SONOFF SNZB-03P | 2 | ¥1,200 | ¥2,400 |
| 4 | SONOFF SNZB-04P | 2 | ¥1,100 | ¥2,200 |
| 5 | Tuya ZY-M100 mmWave | 1 | ¥3,000 | ¥3,000 |
| 6 | Tuya ZS06 IRブラスター | 1 | ¥1,800 | ¥1,800 |
| | | | **合計** | **~¥14,600** |

---

## 5. HEMS 機能拡張ロードマップ

### 5.1 実装済み（コード変更不要）

| 機能 | 対応ツール/ルール | 対応プロトコル |
|------|-----------------|-------------|
| 照明ON/OFF/調光 | `control_light` | 全て |
| エアコン制御 | `control_climate` | 全て |
| カーテン制御 | `control_cover` | 全て |
| スイッチ制御 | `control_switch` | 全て |
| デバイス一覧取得 | `get_home_devices` | 全て |
| 温度アラート抑制 | RuleEngine (30分) | 全て |
| CO2アラート抑制 | RuleEngine (10分) | 全て |
| 水漏れ緊急アラート | RuleEngine (urgency=4) | 全て |
| ドア到着/出発連動 | RuleEngine | 全て |
| 電力モニタリング連動 | RuleEngine | 全て |
| 振動→洗濯完了 | RuleEngine | 全て |
| CO2+窓→換気促進 | RuleEngine | 全て |
| PM2.5→空気清浄機 | RuleEngine | 全て |
| 睡眠→照明OFF | Rule 1, 6 | 全て |
| 起床→照明ON | Rule 4 | 全て |
| 起床前カーテン開放 | Rule 3 | 全て |
| 到着前HVAC | Rule 2 | 全て |
| 疲労時減光 | Rule 11 | 全て |

### 5.2 未実装: 優先度中

| 機能 | 概要 |
|------|------|
| `execute_scene` | 複数デバイス一括制御（おやすみ/外出/在宅勤務シーン） |
| `get_sensor_data` | LLMからの能動的センサー値取得 |

### 5.3 未実装: 優先度低

| 機能 | 概要 |
|------|------|
| 不在モード | 防犯照明ランダム点灯 |
| ゲストモード | 来客時の自動化一時停止 |
| 天気連動 | 天気予報APIと窓/カーテン制御 |
| エネルギーダッシュボード | 電力消費の可視化 |
| サーカディアンリズム照明 | 時間帯自動色温度変化 |

---

## 6. 設置ゾーン別プラン

### リビング（主要居室）

| デバイス | エコシステム | 用途 |
|----------|------------|------|
| Aqara FP2 mmWave | Wi-Fi (HA直接) | 在室検知（座っている状態も検知） |
| Aqara 温湿度 | Zigbee | 環境モニタリング |
| Nature Remo Lapis or SwitchBot Hub 3 | Wi-Fi (Matter) | エアコン+TV制御 |
| SwitchBot LED電球 x2 | BLE | 照明制御+色温度調整 |
| SwitchBot リモートボタン | BLE | 物理ボタン制御 |

### 寝室

| デバイス | エコシステム | 用途 |
|----------|------------|------|
| SwitchBot 人感センサーPro | BLE (mmWave) | 睡眠検知 |
| Aqara 温湿度 | Zigbee | 快適温度維持 |
| SwitchBot カーテン3 x2 | BLE | 起床時自動開放 |
| SwitchBot LED電球 | BLE | 暖色照明（就寝モード） |

### キッチン

| デバイス | エコシステム | 用途 |
|----------|------------|------|
| Aqara PIR | Zigbee | 入室検知→照明 |
| SwitchBot 水漏れ or SONOFF SNZB-05P | BLE / Zigbee | シンク下漏水検知 |
| Tapo P110M | Wi-Fi (Matter) | 電気ケトル電力監視 |

### 玄関/廊下

| デバイス | エコシステム | 用途 |
|----------|------------|------|
| Aqara 開閉センサー | Zigbee | 到着/出発検知 |
| Aqara PIR | Zigbee | 照明自動点灯 |
| SwitchBot ロックPro | BLE | 施錠自動化 |

### 洗面所/浴室

| デバイス | エコシステム | 用途 |
|----------|------------|------|
| Aqara PIR | Zigbee | 入室検知→照明+換気扇 |
| SONOFF SNZB-05P | Zigbee | 洗濯機周辺漏水検知 |
| Aqara DJT11LM | Zigbee | 洗濯完了検知 |

---

## 7. 購入ガイド

### 7.1 購入先比較

| 購入先 | 利点 | 欠点 | 推奨ブランド |
|--------|------|------|------------|
| **Amazon.co.jp** | 即日配送、返品容易、PSE/技適保証 | Zigbee品は割高 | SwitchBot, Aqara, Tapo, Meross, Nature Remo |
| **AliExpress** | 最安、品揃え最大 | 2-4週間配送、技適未保証品あり | SONOFF, Tuya, Gledopto, Zemismart |
| **switchbot.jp** | 公式、セール頻繁 | SwitchBotのみ | SwitchBot |

### 7.2 セール時期

- **Amazon プライムデー** (7月): SwitchBot/Aqara 20-40%OFF
- **Amazon ブラックフライデー** (11月): 全ブランド値引き
- **SwitchBot 秋の感謝祭** (10月): 最大59,020円引きセット
- **AliExpress 11.11セール** (11月): Zigbee品が最安

### 7.3 技適・PSEについて

- **PSE**: 電気用品安全法。コンセントに差す製品は必須。Amazon.co.jp販売品は基本PSE済
- **技適**: 無線機器の技術基準適合証明。2.4GHz帯(Zigbee/BLE/Wi-Fi)は本来必要だが、BLE/Wi-Fi製品は海外メーカーもほぼ取得済み。Zigbee製品はSONOFF日本向けモデル(S60ZBTPBなど)が技適取得
- **実用上**: Amazon.co.jpの公式ストア販売品を選べば安全。AliExpress購入品は自己責任

### 7.4 AliExpress検索キーワード

Zigbee品をAliExpressで購入する場合のキーワード:

| 製品 | 検索キーワード |
|------|--------------|
| SONOFF ZBDongle-E | `SONOFF ZBDongle-E` |
| SONOFF SNZB-02P | `SONOFF SNZB-02P` |
| SONOFF SNZB-03P | `SONOFF SNZB-03P` |
| SONOFF SNZB-04P | `SONOFF SNZB-04P` |
| SONOFF SNZB-05P | `SONOFF SNZB-05P water leak sensor` |
| SONOFF ZBMINI-L2 | `SONOFF ZBMINIL2` |
| SONOFF S60ZBTPB | `SONOFF S60 Zigbee plug Type A Japan` |
| Tuya ZY-M100 | `Tuya Zigbee mmWave presence sensor ZY-M100` |
| Tuya ZS06 | `Tuya Zigbee IR blaster ZS06` |
| Tuya TS011F | `Tuya Zigbee smart plug 16A power monitoring TS011F` |
| Tuya E27 RGBCCT | `Tuya Zigbee E27 RGBW bulb` |
| Aqara DJT11LM | `Aqara vibration sensor Zigbee` |
| Zemismart AM43 | `AM43 Zigbee roller blind motor` |
| Gledopto GL-C-001P | `Gledopto Zigbee RGBCCT controller Pro` |

---

## 付録: Zigbeeメッシュネットワーク設計

### ルーターデバイス（電源駆動、メッシュ中継）
- スマートプラグ (S60ZBTPB / TS011F) x2-5
- リレー (ZBMINI-L2) x2-3
- 電球 (Tuya RGBCCT) x2-3
- IRブラスター (ZS06) x1-2

### エンドデバイス（電池駆動、中継しない）
- 温湿度 (Aqara/SNZB-02P) x2-3
- PIR (Aqara/SNZB-03P) x2-3
- ドア (Aqara/SNZB-04P) x2
- 水漏れ (SNZB-05P) x2-3
- 振動 (DJT11LM) x1

### 配置の原則
1. コーディネーターは家の中心付近にUSB延長ケーブルで設置
2. ルーターデバイスを各部屋に最低1台
3. エンドデバイスからルーターまで直線10m以内
4. ハイブリッド構成ではZigbeeルーター台数が少なくなるため、意識的にプラグ/電球を配置
