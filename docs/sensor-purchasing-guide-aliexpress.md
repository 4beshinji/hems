# HEMS センサー購入ガイド（AliExpress・コスト最優先）

> 作成日: 2026-03-13
> 対象: コスパを極限まで追求したい自己責任の民
> 方針: **最安・最多品揃え・技適/PSE未確認品を含む・全て自己責任**

---

> **⚠️ 法的リスクに関する重要な警告**
>
> 本ガイドに掲載する製品の多くは**技適認証を取得していない**可能性があります。
> 技適マークのない無線機器の日本国内での使用は**電波法違反**（1年以下の懲役または100万円以下の罰金）です。
>
> - 技適未確認のZigbee/BLE/Wi-Fiデバイスの使用は完全に**自己責任**
> - 本ガイドは製品情報の提供のみを目的としており、違法行為を推奨するものではありません
> - 合法的に導入したい場合は `docs/sensor-purchasing-guide-jp.md` を参照してください
>
> **現実**: 個人宅のZigbeeセンサーで摘発された事例は確認されていない。
> 2.4GHz帯・10mW以下の微弱無線は実質的に取り締まり対象外だが、法的にはアウト。

---

## 目次

1. [AliExpress購入の基礎知識](#1-aliexpress購入の基礎知識)
2. [デバイスカタログ](#2-デバイスカタログ)
3. [HEMS機能逆引き表](#3-hems機能逆引き表)
4. [推奨購入パッケージ](#4-推奨購入パッケージ)
5. [購入Tips・トラブル対策](#5-購入tipsトラブル対策)

---

## 1. AliExpress購入の基礎知識

### 1.1 Amazon.co.jp vs AliExpress コスト比較

| 項目 | Amazon.co.jp | AliExpress |
|------|-------------|------------|
| 温湿度センサー | ¥2,980（Aqara） | **¥1,000**（SONOFF SNZB-02P） |
| PIR人感センサー | ¥2,980（Aqara） | **¥1,200**（SONOFF SNZB-03P） |
| ドアセンサー | ¥2,980（Aqara） | **¥1,000**（SONOFF SNZB-04P） |
| mmWaveセンサー | ¥7,000（Aqara FP2） | **¥3,000**（Tuya ZY-M100） |
| スマートプラグ | ¥1,160（Tapo P110M） | **¥2,000**（SONOFF S60ZBTPB） |
| IRブラスター | ¥3,980（Nature Remo nano） | **¥1,800**（Tuya ZS06） |
| LED電球 | ¥1,980（SwitchBot） | **¥1,200**（Tuya E27 RGBCCT） |
| リレースイッチ | ¥3,980（SwitchBot） | **¥1,200**（SONOFF ZBMINIR2） |
| **フルセット概算** | **~¥28,000** | **~¥13,000** |

**約半額**。同じHEMS機能を実現できる。

### 1.2 配送・決済

| 項目 | 詳細 |
|------|------|
| 配送期間 | 2-4週間（AliExpress Standard Shipping） |
| 送料 | 多くの製品で無料（¥2,000未満は送料あり） |
| 決済 | クレジットカード、PayPal、コンビニ払い |
| 関税 | 個人輸入 ¥16,666以下は免税（課税価格×0.6） |
| 返品 | 到着後15日以内、Buyer Protection あり |
| 初期不良率 | 体感2-5%（Amazon比やや高い） |

### 1.3 技適ステータス早見表

| ブランド | 技適状況 | 備考 |
|---------|---------|------|
| **SONOFF** | 一部モデル技適取得（S60ZBTPBなど） | グローバル版は未取得が多い |
| **Tuya** | 基本的に未取得 | OEM元による。ホワイトラベル品は個別確認不可 |
| **Aqara** | AliExpress版は中国版（技適なし） | Amazon.co.jp版とは別SKU |
| **Zemismart** | 未取得 | Tuya OEM |
| **Gledopto** | 未取得 | Zigbee LED コントローラー専業 |
| **Moes** | 未取得 | Tuya OEM |
| **Heiman** | 一部モデルCE/FCC取得、技適なし | 防災系センサー専業 |

---

## 2. デバイスカタログ

> **価格**: AliExpress通常価格（2026年3月時点）。セール時はさらに20-50%OFF。
> **HA連携**: 全製品 Zigbee2MQTT (Z2M) or ZHA で動作確認済み（記載のあるもの）。

---

### 2.1 Zigbeeコーディネーター

#### SONOFF ZBDongle-E（推奨）

- **価格**: ~¥1,900
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-SONOFF-ZBDongle-E.html)
- **チップ**: EFR32MG21 / 3.0dBi アンテナ
- **技適**: 一部ロットで取得確認あり（個体差）
- **HA連携**: ZHA / Zigbee2MQTT
- **HEMS実現機能**:
  - Zigbeeメッシュネットワーク構築（最大100台）
  - 完全ローカル制御（クラウド不要）
- **AE vs Amazon**: ¥600安い

#### SONOFF Dongle Plus MG24

- **価格**: ~¥2,200
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-SONOFF-ZBDongle-MG24.html)
- **チップ**: EFR32MG24 / 4.5dBi アンテナ
- **HA連携**: ZHA / Zigbee2MQTT
- **HEMS実現機能**: ZBDongle-E同等（最新チップ、受信感度向上）
- **備考**: 広い家や多デバイス環境向き

---

### 2.2 温湿度センサー

#### SONOFF SNZB-02P（推奨）

- **価格**: ~¥1,000
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-SONOFF-SNZB-02P.html)
- **プロトコル**: Zigbee 3.0
- **精度**: ±0.2°C / ±2%RH
- **電源**: CR2477（約4年）
- **技適**: 未確認
- **HA連携**: ZHA / Z2M（即認識）
- **HEMS実現機能**:
  - `hems/home/{zone}/sensor/sensor.{name}_temperature/state` に自動反映
  - Brain が温度データを基にエアコンON/OFF判断
  - 30分温度アラート抑制
  - WorldModel の PhysicalSpace に温湿度反映
- **推奨数量**: 3-5台（全部屋に配置してもAqara 1台分の価格）
- **AE vs Amazon Aqara**: **1/3の価格**で精度は上

#### SONOFF SNZB-02D（LCD付き）

- **価格**: ~¥1,400
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-SONOFF-SNZB-02D.html)
- **プロトコル**: Zigbee 3.0
- **精度**: ±0.2°C / ±2%RH
- **電源**: CR2450（約2年）
- **技適**: 未確認
- **HEMS実現機能**: SNZB-02P同等 + LCD画面で目視確認可能
- **備考**: 見える場所に置くならこちら

#### Tuya 温湿度センサー（最安）

- **価格**: ~¥600-800
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Tuya-Zigbee-temperature-humidity-sensor.html)
- **プロトコル**: Zigbee 3.0
- **精度**: ±0.5°C / ±5%RH（SONOFFより劣る）
- **電源**: CR2032（約1年）
- **技適**: 未確認
- **HEMS実現機能**: SNZB-02P同等（精度は落ちる）
- **備考**: 最安。精度にこだわらないサブ部屋向き

---

### 2.3 人感・在室センサー

#### SONOFF SNZB-03P（PIR・推奨）

- **価格**: ~¥1,200
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-SONOFF-SNZB-03P.html)
- **プロトコル**: Zigbee 3.0
- **検知**: 110° / 6m（動体のみ）
- **電源**: CR2477（約3年）
- **技適**: 未確認
- **HA連携**: ZHA / Z2M
- **HEMS実現機能**:
  - 廊下/トイレの照明自動ON/OFF
  - キッチン入室検知 → 照明制御
  - 不在時セキュリティ（想定外動体検知アラート）
- **推奨設置**: 廊下、トイレ、キッチン
- **AE vs Amazon Aqara**: **1/2.5の価格**

#### Tuya ZY-M100（mmWave・推奨）

- **価格**: ~¥3,000
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Tuya-ZY-M100-mmWave-presence-sensor.html)
- **プロトコル**: Zigbee 3.0
- **検知**: ~5m（静止人体検知）
- **電源**: USB 5V
- **技適**: 未確認
- **HA連携**: Z2M（要カスタムコンバーター、ZHA非対応の場合あり）
- **HEMS実現機能**:
  - **静止人体検知**（座り仕事中も在室判定）
  - 睡眠検知 → 全照明OFF + カーテン全閉
  - 在室/不在 → ScheduleLearner パターン学習
  - 到着前HVAC予冷/予暖
  - 不在モード → 防犯照明ランダム点灯
- **備考**: Aqara FP2の半額以下。ゾーン検知は非対応だがmmWave基本機能は同等
- **AE vs Amazon FP2**: **1/2.5の価格**

#### Tuya mmWave センサー（24GHz・高機能版）

- **価格**: ~¥4,000-5,000
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Tuya-Zigbee-24GHz-mmWave-human-presence.html)
- **プロトコル**: Zigbee 3.0
- **検知**: 24GHz、距離設定可能、照度センサー付き
- **電源**: USB 5V
- **HEMS実現機能**: ZY-M100同等 + 検知距離カスタマイズ + 照度連動
- **備考**: 照度センサー付きで照明自動化の精度が向上

#### Aqara RTCGQ11LM（AliExpress版）

- **価格**: ~¥1,800
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Aqara-motion-sensor-Zigbee.html)
- **プロトコル**: Zigbee 3.0
- **検知**: 170° / 7m
- **技適**: なし（中国版SKU）
- **HEMS実現機能**: Amazon版と同等
- **備考**: Amazon.co.jp版（¥2,980）の約6割の価格。中身は同じ

---

### 2.4 ドア・窓センサー

#### SONOFF SNZB-04P（推奨）

- **価格**: ~¥1,000
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-SONOFF-SNZB-04P.html)
- **プロトコル**: Zigbee 3.0
- **電源**: CR2477（約5年）
- **技適**: 未確認
- **HA連携**: ZHA / Z2M
- **HEMS実現機能**:
  - **玄関ドア**: 到着/出発パターン学習（ScheduleLearner）
  - **窓**: CO2センサーと連動した換気状態追跡
  - 到着検知 → HVAC自動起動、照明ON
  - 出発検知 → 全照明OFF、エアコンOFF、施錠確認
- **推奨数量**: 3-5台（全ドア+主要窓に。この価格なら惜しくない）
- **AE vs Amazon Aqara**: **1/3の価格**、電池寿命は2.5倍

#### Tuya ドアセンサー（最安）

- **価格**: ~¥600-800
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Tuya-Zigbee-door-window-sensor.html)
- **プロトコル**: Zigbee 3.0
- **電源**: CR2032（約1-2年）
- **HEMS実現機能**: SNZB-04P同等
- **備考**: 最安。電池寿命は短いがサブ窓に

---

### 2.5 スマートプラグ

#### SONOFF S60ZBTPB（Zigbee・日本Type A・推奨）

- **価格**: ~¥2,000
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-SONOFF-S60-Zigbee-plug-Type-A-Japan.html)
- **プロトコル**: Zigbee 3.0
- **コンセント**: **日本Type A対応**
- **電力計測**: W / kWh
- **技適**: 取得済み（SONOFF日本向けモデル）
- **PSE**: 取得済み
- **HA連携**: ZHA / Z2M
- **HEMS実現機能**:
  - 家電ON/OFF制御 → `control_switch` ツール
  - 電力モニタリング → WorldModel に消費電力反映
  - 洗濯機W値変化で完了検知 → `create_task` + `speak`
  - **Zigbeeルーター機能**（メッシュネットワーク強化）
- **備考**: **日本Type A + Zigbee の唯一の選択肢**。AliExpress限定。技適+PSE取得済みの数少ないAE品

#### Tuya TS011F（Zigbee・要変換プラグ）

- **価格**: ~¥1,200
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Tuya-TS011F-Zigbee-smart-plug-16A.html)
- **プロトコル**: Zigbee 3.0
- **コンセント**: EU/US Type（**日本Type A非対応** → 変換アダプタ必要）
- **電力計測**: W / kWh（16A版）
- **技適**: 未確認
- **HEMS実現機能**: S60ZBTPB同等 + Zigbeeルーター
- **備考**: 最安Zigbeeプラグ。US Type版なら日本で物理的に挿さるが幅広で隣と干渉しやすい。**Zigbeeルーターとして最安**

---

### 2.6 IRブラスター（スマートリモコン）

#### Tuya ZS06（Zigbee IR・推奨）

- **価格**: ~¥1,800
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Tuya-ZS06-Zigbee-IR-blaster.html)
- **プロトコル**: Zigbee 3.0 + IR送信
- **電源**: USB 5V
- **技適**: 未確認
- **HA連携**: Z2M（IRコードの学習・送信）
- **HEMS実現機能**:
  - エアコン制御 → `control_climate` ツール（HAでclimateエンティティ化）
  - TV・扇風機等のIR家電制御
  - **Zigbeeルーター**としてメッシュ強化も兼ねる
- **備考**: Nature Remo nano（¥3,980）の半額以下。Matter非対応だがZ2M経由でHA統合可能
- **AE vs Amazon Remo nano**: **半額以下**

#### Moes UFO-R11（Zigbee IR）

- **価格**: ~¥2,000
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Moes-UFO-R11-Zigbee-IR-remote.html)
- **プロトコル**: Zigbee 3.0 + IR
- **HEMS実現機能**: ZS06同等
- **備考**: UFO型デザイン。360° IR送信

---

### 2.7 スマートライト

#### Tuya E27 RGBCCT Zigbee電球（推奨）

- **価格**: ~¥1,200
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Tuya-Zigbee-E27-RGBW-bulb.html)
- **プロトコル**: Zigbee 3.0
- **スペック**: E27口金（E26アダプタ要）、RGB+色温度、9W 800lm
- **技適**: 未確認
- **HA連携**: ZHA / Z2M
- **HEMS実現機能**:
  - `control_light(brightness, color_temp)` で直接制御
  - サーカディアンリズム照明
  - 疲労時減光（21-23時 + 疲労スコア>60 → brightness=80, color_temp=400）
  - 睡眠検知 → 全照明OFF
  - 起床検知 → brightness=255
  - 不在時防犯照明ランダム点灯
  - **Zigbeeルーター**（常時通電でメッシュ強化）
- **注意**: E27口金 → 日本のE26ソケットには**E27→E26変換アダプタ**（¥200-300）が必要
- **AE vs Amazon SwitchBot**: ¥800安い + Zigbeeルーター兼務

#### Gledopto GL-C-001P（Zigbee LEDコントローラー）

- **価格**: ~¥2,000
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Gledopto-Zigbee-RGBCCT-controller-Pro.html)
- **プロトコル**: Zigbee 3.0
- **スペック**: 5ch RGBCCT LED テープ/パネル用コントローラー
- **HEMS実現機能**: 電球同等（LED テープ/パネル制御用）
- **備考**: 12V/24V LEDテープに接続。間接照明のDIYに

#### Tuya Zigbee E14 キャンドル電球

- **価格**: ~¥1,000
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Tuya-Zigbee-E14-candle-bulb-RGBCCT.html)
- **プロトコル**: Zigbee 3.0
- **スペック**: E14口金、RGB+色温度、5W
- **HEMS実現機能**: E27電球同等（小型照明向け）

---

### 2.8 スマートリレー/スイッチ

#### SONOFF ZBMINI-L2（中性線不要・推奨）

- **価格**: ~¥1,400
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-SONOFF-ZBMINI-L2.html)
- **プロトコル**: Zigbee 3.0
- **定格**: 6A / 1320W
- **中性線**: **不要**（日本の住宅配線に最適）
- **技適**: 未確認
- **HA連携**: ZHA / Z2M
- **HEMS実現機能**:
  - 既存壁スイッチのスマート化（工事不要、スイッチボックス内設置）
  - `control_switch` ツールで制御
  - **Zigbeeルーター**としてメッシュ強化
- **備考**: 日本の住宅は中性線なしが多い → **ZBMINI-L2一択**。SwitchBot Relay Switch（¥3,980）の1/3
- **AE vs Amazon SwitchBot Relay**: **1/3の価格**

#### SONOFF ZBMINIR2（中性線必要）

- **価格**: ~¥1,200
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-SONOFF-ZBMINIR2.html)
- **プロトコル**: Zigbee 3.0
- **定格**: 10A / 2200W
- **中性線**: 必要
- **HEMS実現機能**: ZBMINI-L2同等
- **備考**: 中性線がある場合はこちらの方が高定格

#### SONOFF ZBMINIL2 Extreme（超小型）

- **価格**: ~¥1,600
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-SONOFF-ZBMINIL2-Extreme.html)
- **プロトコル**: Zigbee 3.0
- **中性線**: 不要
- **HEMS実現機能**: ZBMINI-L2同等
- **備考**: さらに小型化。狭いスイッチボックスに

---

### 2.9 カーテン/ブラインドモーター

#### Zemismart AM43（Zigbee ローラーブラインド）

- **価格**: ~¥5,000-7,000
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-AM43-Zigbee-roller-blind-motor.html)
- **プロトコル**: Zigbee 3.0
- **タイプ**: ローラーブラインド / ロールカーテン
- **電源**: 充電池（USB充電）+ ソーラーパネル対応
- **技適**: 未確認
- **HA連携**: Z2M
- **HEMS実現機能**:
  - `control_cover(position)` で開閉制御（0-100%）
  - 起床前カーテン開放（ScheduleLearner連動）
  - 睡眠検知 → 全閉
- **備考**: SwitchBot カーテン3（¥8,980）より安いが、対応レールが異なる。25mmチューブ対応

#### Tuya Zigbee カーテンモーター

- **価格**: ~¥6,000-10,000
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Tuya-Zigbee-curtain-motor-track.html)
- **プロトコル**: Zigbee 3.0 or Wi-Fi
- **タイプ**: 電動カーテンレール（レールごと交換）
- **HEMS実現機能**: AM43同等
- **備考**: レールごと交換するタイプ。確実だが設置は大掛かり

---

### 2.10 空気質センサー

#### Tuya 6-in-1 Air Box

- **価格**: ~¥3,500
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Tuya-Zigbee-air-quality-sensor-6-in-1.html)
- **プロトコル**: Zigbee 3.0
- **計測項目**: CO2（eCO2推定）、PM2.5、温度、湿度、ホルムアルデヒド、VOC
- **電源**: USB 5V
- **技適**: 未確認
- **HA連携**: Z2M
- **HEMS実現機能**:
  - CO2モニタリング → 10分アラート抑制
  - CO2 + 窓開閉センサー連動で換気状態追跡
  - PM2.5 → 空気清浄機自動制御
  - WorldModel に空気質データ反映
- **注意**: eCO2はVOCからの**推定値**であり、NDIR実測ではない。精度は低い
- **AE vs Amazon SwitchBot CO2**: **半額以下**だがCO2は推定値

#### Heiman HS3AQ（NDIR実測CO2）

- **価格**: ~¥7,000
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Heiman-HS3AQ-Zigbee-air-quality.html)
- **プロトコル**: Zigbee 3.0
- **計測項目**: CO2（NDIR実測）、温度、湿度
- **電源**: USB 5V
- **HEMS実現機能**: 正確なCO2値でのモニタリング
- **備考**: SwitchBot CO2センサーと同価格帯だが、AEで買えるZigbee NDIR品

---

### 2.11 水漏れセンサー

#### SONOFF SNZB-05P（推奨）

- **価格**: ~¥1,200
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-SONOFF-SNZB-05P-water-leak-sensor.html)
- **プロトコル**: Zigbee 3.0
- **電源**: CR2477（約5年）
- **技適**: 未確認
- **HA連携**: ZHA / Z2M
- **HEMS実現機能**:
  - 漏水検知 → **urgency=4の緊急タスク生成** + `speak` で音声アラート
- **推奨数量**: 2-3台（シンク下、洗濯機、浴室）
- **備考**: SwitchBot水漏れセンサー（¥1,480）と同価格帯だが電池寿命5年

#### Tuya 水漏れセンサー（最安）

- **価格**: ~¥700-900
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Tuya-Zigbee-water-leak-sensor.html)
- **プロトコル**: Zigbee 3.0
- **電源**: CR2032（約1-2年）
- **HEMS実現機能**: SNZB-05P同等
- **備考**: 最安水漏れセンサー。複数設置に

---

### 2.12 振動センサー

#### Aqara DJT11LM（AliExpress版）

- **価格**: ~¥1,500-2,000
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Aqara-vibration-sensor-Zigbee.html)
- **プロトコル**: Zigbee 3.0
- **電源**: CR2032（約2年）
- **技適**: なし（中国版）
- **HA連携**: ZHA / Z2M
- **HEMS実現機能**:
  - 洗濯機に貼付 → 振動停止検知 → `create_task("洗濯物を干す")` + `speak("洗濯が終わりました")`
  - 乾燥機完了検知
- **AE vs Amazon**: ¥500-1,000安い

---

### 2.13 シーンスイッチ/ボタン

#### Tuya TS0044（4ボタンシーンスイッチ・推奨）

- **価格**: ~¥1,200
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Tuya-TS0044-Zigbee-scene-switch-4-button.html)
- **プロトコル**: Zigbee 3.0
- **ボタン数**: 4（各ボタン: 1クリック / 2クリック / 長押し = 12アクション）
- **電源**: CR2450
- **技適**: 未確認
- **HA連携**: ZHA / Z2M
- **HEMS実現機能**:
  - 物理ボタンでシーン実行（おやすみ、外出、帰宅、全消灯等）
  - `execute_scene` ツール連動
  - 4ボタン × 3アクション = **12種類のシーン**を1デバイスで
- **備考**: SwitchBot リモートボタン（1ボタン・¥1,980）より安くて高機能

#### Tuya TS0043（3ボタン）

- **価格**: ~¥1,000
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Tuya-TS0043-Zigbee-scene-switch.html)
- **HEMS実現機能**: TS0044同等（9アクション）

#### SONOFF SNZB-01P（1ボタン）

- **価格**: ~¥900
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-SONOFF-SNZB-01P-Zigbee-button.html)
- **プロトコル**: Zigbee 3.0
- **HEMS実現機能**: 1クリック / 2クリック / 長押し = 3アクション

---

### 2.14 スマートロック

#### Tuya Zigbee スマートロック

- **価格**: ~¥8,000-15,000
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Tuya-Zigbee-smart-lock-fingerprint.html)
- **プロトコル**: Zigbee + BLE
- **認証方式**: 指紋 / 暗証番号 / NFCカード / アプリ
- **技適**: 未確認
- **HEMS実現機能**:
  - 出発検知 → 自動施錠
  - 施錠状態 → WorldModel に反映
- **注意**: **日本のサムターン非対応が多い**。穴あけ工事が必要な場合あり。後付けタイプを選ぶこと
- **備考**: SwitchBot ロックPro（¥17,980）より安いが取り付け互換性に要注意

---

### 2.15 スマート温度計プローブ

#### Tuya Zigbee 温度プローブ

- **価格**: ~¥1,500
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Tuya-Zigbee-temperature-probe-sensor.html)
- **プロトコル**: Zigbee 3.0
- **スペック**: 外付けプローブ、-20°C~100°C
- **HEMS実現機能**:
  - 冷蔵庫/冷凍庫の温度監視
  - サーバールーム温度監視
  - 水槽温度監視
- **備考**: Amazon版では見つからないAE限定カテゴリ

---

### 2.16 土壌水分センサー

#### Tuya Zigbee 土壌水分センサー

- **価格**: ~¥1,500-2,000
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Tuya-Zigbee-soil-moisture-sensor.html)
- **プロトコル**: Zigbee 3.0
- **計測**: 土壌水分 + 温度
- **電源**: 電池（約6ヶ月）
- **HEMS実現機能**:
  - 観葉植物の水やりリマインダー（Brain → `create_task` + `speak`）
  - WorldModel に植物状態反映
- **備考**: AE限定カテゴリ。植物好きには刺さる

---

### 2.17 スマートバルブ（電磁弁）

#### Tuya Zigbee ウォーターバルブ

- **価格**: ~¥3,000-4,000
- **AliExpress**: [検索](https://www.aliexpress.com/w/wholesale-Tuya-Zigbee-smart-water-valve.html)
- **プロトコル**: Zigbee 3.0
- **HEMS実現機能**:
  - 水漏れセンサーと連動して自動止水
  - 自動水やり（土壌センサー連動）
- **備考**: 漏水検知 → 緊急止水の自動化。AE限定

---

## 3. HEMS機能逆引き表

| やりたいこと | AliExpress最安構成 | 最低予算 | Amazon比 |
|-------------|-------------------|---------|---------|
| エアコン自動制御 | ZS06 + SNZB-02P | ~¥2,800 | **60%OFF** |
| 在室/不在検知（動体） | SNZB-03P | ~¥1,200 | **60%OFF** |
| 静止人体検知 | Tuya ZY-M100 | ~¥3,000 | **57%OFF** |
| 到着/出発パターン学習 | SNZB-04P | ~¥1,000 | **67%OFF** |
| 起床時カーテン開放 | Zemismart AM43 | ~¥5,000 | **44%OFF** |
| 洗濯完了通知 | Aqara DJT11LM | ~¥1,500 | **40%OFF** |
| CO2換気促進 | Tuya Air Box + SNZB-04P | ~¥4,500 | **57%OFF** |
| 水漏れ緊急アラート | SNZB-05P | ~¥1,200 | **19%OFF** |
| 照明自動制御 | Tuya E27 RGBCCT | ~¥1,200 | **39%OFF** |
| 壁スイッチスマート化 | ZBMINI-L2 | ~¥1,400 | **65%OFF** |
| 電力モニタリング | S60ZBTPB (Type A) | ~¥2,000 | -（AE限定） |
| 12アクションボタン | TS0044 | ~¥1,200 | -（AE限定） |
| 冷蔵庫温度監視 | Tuya温度プローブ | ~¥1,500 | -（AE限定） |
| 植物水やりリマインダー | 土壌水分センサー | ~¥1,500 | -（AE限定） |
| 漏水自動止水 | SNZB-05P + 電磁弁 | ~¥4,200 | -（AE限定） |

---

## 4. 推奨購入パッケージ

### 4.1 最安構成（~¥10,000）

Amazonスタンダード（¥28,000）と同等機能を1/3の価格で。

| # | 製品 | 数量 | 単価 | 小計 |
|---|------|------|------|------|
| 1 | SONOFF ZBDongle-E | 1 | ¥1,900 | ¥1,900 |
| 2 | SONOFF SNZB-02P | 2 | ¥1,000 | ¥2,000 |
| 3 | SONOFF SNZB-03P | 1 | ¥1,200 | ¥1,200 |
| 4 | SONOFF SNZB-04P | 2 | ¥1,000 | ¥2,000 |
| 5 | Tuya ZS06 IRブラスター | 1 | ¥1,800 | ¥1,800 |
| 6 | Tuya E27 RGBCCT 電球 | 2 | ¥1,200 | ¥2,400 |
| | | | **合計** | **~¥11,300** |

**実現できるHEMS機能**:
- エアコン自動制御（IR経由）
- 2部屋の温湿度監視
- 動体検知（廊下/トイレ）
- 到着/出発パターン学習（ScheduleLearner）
- 窓開閉による換気追跡
- 照明自動制御 + サーカディアンリズム + 疲労連動減光
- 不在時防犯照明
- Zigbeeメッシュネットワーク（電球2台がルーター）

---

### 4.2 全部屋カバー（~¥20,000）

全部屋にセンサー配置 + mmWave + スイッチスマート化。

| # | 製品 | 数量 | 単価 | 小計 |
|---|------|------|------|------|
| | **= 最安構成 =** | | | **¥11,300** |
| 7 | SONOFF SNZB-02P（追加） | 2 | ¥1,000 | ¥2,000 |
| 8 | Tuya ZY-M100 mmWave | 1 | ¥3,000 | ¥3,000 |
| 9 | SONOFF ZBMINI-L2 | 2 | ¥1,400 | ¥2,800 |
| 10 | SONOFF SNZB-05P 水漏れ | 1 | ¥1,200 | ¥1,200 |
| | | | **合計** | **~¥20,300** |

**追加で実現できるHEMS機能**:
- 全4部屋の温湿度監視
- 静止人体検知（mmWave）
- 睡眠検知 → 照明OFF / カーテン閉
- 既存壁スイッチ2箇所のスマート化
- 水漏れ緊急アラート
- メッシュネットワーク強化（ルーター: 電球2 + リレー2 + IRブラスター1 = 5台）

---

### 4.3 ガチ全盛り（~¥35,000）

Amazonフル装備（¥76,000）を超える機能を半額以下で。

| # | 製品 | 数量 | 単価 | 小計 |
|---|------|------|------|------|
| | **= 全部屋カバー =** | | | **¥20,300** |
| 11 | Zemismart AM43 | 2 | ¥5,500 | ¥11,000 |
| 12 | Aqara DJT11LM 振動 | 1 | ¥1,500 | ¥1,500 |
| 13 | Tuya TS0044 4ボタン | 1 | ¥1,200 | ¥1,200 |
| 14 | Tuya 6-in-1 Air Box | 1 | ¥3,500 | ¥3,500 |
| | | | **合計** | **~¥37,500** |

**追加で実現できるHEMS機能**:
- カーテン自動開閉（起床/就寝連動）
- 洗濯完了通知（振動検知）
- 12アクションシーンスイッチ
- CO2/PM2.5/VOC空気質モニタリング
- PM2.5 → 空気清浄機連動

---

### 4.4 パッケージ比較表

| | AE最安 | AE全部屋 | AE全盛り | Amazon スタンダード | Amazon フル |
|--|--------|---------|---------|-------------------|------------|
| **価格** | **¥11,300** | **¥20,300** | **¥37,500** | ¥27,660 | ¥76,570 |
| 温湿度 | 2部屋 | 4部屋 | 4部屋 | 2部屋 | 2部屋 |
| PIR | 1台 | 1台 | 1台 | 1台 | 1台 |
| mmWave | - | 1台 | 1台 | - | 1台 |
| ドアセンサー | 2台 | 2台 | 2台 | 2台 | 2台 |
| IR制御 | Zigbee | Zigbee | Zigbee | Matter | Matter |
| 照明 | 2台 | 2台 | 2台 | 2台 | 2台 |
| リレースイッチ | - | 2台 | 2台 | - | - |
| カーテン | - | - | 2台 | - | 2台 |
| CO2/空気質 | - | - | 6-in-1 | - | NDIR |
| 水漏れ | - | 1台 | 1台 | - | 1台 |
| 振動 | - | - | 1台 | - | 1台 |
| シーンボタン | - | - | 12アクション | - | - |
| バイオメトリクス | - | - | - | - | 1台 |
| **技適** | **未確認** | **未確認** | **未確認** | **全品認証済** | **全品認証済** |

---

## 5. 購入Tips・トラブル対策

### 5.1 AliExpressセール時期

| セール | 時期 | 割引率 |
|--------|------|--------|
| **3.28 Anniversary Sale** | 3月下旬 | 20-50%OFF |
| **6.18 Mid-Year Sale** | 6月中旬 | 20-40%OFF |
| **8.28 Brands Festival** | 8月下旬 | 15-30%OFF |
| **11.11 Global Shopping** | 11月11日 | **最大60%OFF**（年間最安） |
| **12.12 Sale** | 12月12日 | 20-40%OFF |
| **Black Friday** | 11月下旬 | 20-40%OFF |

> 11.11セールが年間最安。まとめ買い推奨。SONOFF公式ストアは11.11で全品40-50%OFFになることがある。

### 5.2 おすすめストア

| ストア | 取扱ブランド | 信頼性 |
|--------|------------|--------|
| **SONOFF Official Store** | SONOFF | ★★★★★ |
| **ITEAD Official Store** | SONOFF (親会社) | ★★★★★ |
| **Zemismart Official Store** | Zemismart | ★★★★ |
| **Gledopto Official Store** | Gledopto | ★★★★ |
| **Moes Official Store** | Moes/Tuya OEM | ★★★★ |
| 各種Tuya OEMストア | Tuya | ★★★（当たり外れあり） |

> 「Official Store」バッジ付きを選ぶこと。無名ストアは初期不良率が高い。

### 5.3 検索キーワード集

| 製品カテゴリ | 検索キーワード |
|-------------|--------------|
| Zigbee全般 | `Zigbee 3.0 sensor` |
| 温湿度 | `SONOFF SNZB-02P` / `Tuya Zigbee temperature humidity` |
| PIR | `SONOFF SNZB-03P` / `Tuya Zigbee PIR motion` |
| mmWave | `Tuya Zigbee mmWave presence ZY-M100` / `24GHz human presence` |
| ドア | `SONOFF SNZB-04P` / `Tuya Zigbee door window` |
| プラグ (Type A) | `SONOFF S60 Zigbee plug Type A Japan` |
| プラグ (汎用) | `Tuya TS011F Zigbee smart plug 16A` |
| IR | `Tuya ZS06 Zigbee IR blaster` |
| 電球 | `Tuya Zigbee E27 RGBW bulb` / `Zigbee E14 candle` |
| リレー | `SONOFF ZBMINIL2` / `ZBMINI-L2 no neutral` |
| カーテン | `AM43 Zigbee roller blind motor` |
| 空気質 | `Tuya Zigbee air quality 6 in 1` |
| 水漏れ | `SONOFF SNZB-05P water leak` |
| 振動 | `Aqara vibration sensor Zigbee` |
| ボタン | `Tuya TS0044 Zigbee scene switch 4 button` |
| 温度プローブ | `Tuya Zigbee temperature probe` |
| 土壌水分 | `Tuya Zigbee soil moisture sensor` |
| 電磁弁 | `Tuya Zigbee smart water valve` |

### 5.4 トラブル対策

**到着しない場合**:
- Buyer Protection期限内（通常60-90日）にDispute（紛争）を開く
- 追跡番号が動かない場合は30日経過後にDispute可能
- 全額返金されることが多い

**初期不良の場合**:
- 到着後15日以内にDispute → 返金 or 再送
- 動画・写真で不良を証拠として提出
- 少額品（~¥1,000）は返送不要で全額返金されることが多い

**Z2M/ZHAで認識しない場合**:
- ファームウェアバージョン違い → Z2Mの最新devブランチで対応していることが多い
- Tuya OEM品は`_TZ3000_`で始まるモデルIDが異なる場合あり → カスタムコンバーター
- ZHAで非対応の場合はZ2Mに切り替えを検討

**日本Type A非対応の場合**:
- スマートプラグ: US Type版なら物理的に挿さる（幅が広い場合は変換アダプタ）
- 電球: E27→E26変換アダプタ（AEで¥100-200）

### 5.5 Zigbeeメッシュ設計（AE構成向け）

AliExpress構成はZigbee中心のためメッシュ設計が重要:

**ルーターデバイス（常時通電、メッシュ中継）**:
- Tuya E27電球 × 2-4（各部屋に1台）
- ZBMINI-L2 × 2-3（壁スイッチ裏）
- ZS06 IRブラスター × 1-2
- S60ZBTPB プラグ × 1-2

**エンドデバイス（電池駆動、中継しない）**:
- SNZB-02P 温湿度 × 3-5
- SNZB-03P PIR × 2-3
- SNZB-04P ドア × 2-4
- SNZB-05P 水漏れ × 2-3
- DJT11LM 振動 × 1
- TS0044 ボタン × 1

**配置の原則**:
1. ZBDongle-Eは家の中心付近にUSB延長ケーブルで設置
2. ルーター（電球/リレー/プラグ）を各部屋に最低1台
3. エンドデバイスからルーターまで直線10m以内
4. AE構成はZigbee統一のためルーター台数が多く、メッシュが強固になりやすい

---

## 関連ドキュメント

- `docs/sensor-purchasing-guide-jp.md` — 技適準拠・Amazon.co.jp版（合法）
- `docs/smart-home-device-guide.md` — マルチプロトコル総合ガイド
- `docs/SMART_HOME_SETUP.md` — Home Assistant + HEMS統合セットアップ
- `edge/test-edge/docs/02_hardware_specs.md` — ESP32エッジノード仕様
