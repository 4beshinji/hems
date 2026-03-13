# HEMS センサー購入ガイド（技適準拠・Amazon.co.jp）

> 作成日: 2026-03-13
> 対象: 日本国内で設備のスマート化を行いたい方
> 方針: **全製品が技適認証済み + PSE適合 + Amazon.co.jpで購入可能**

---

## 目次

1. [技適・PSEの基礎知識](#1-技適pseの基礎知識)
2. [購入チェックリスト](#2-購入チェックリスト)
3. [デバイスカタログ（Amazon.co.jp限定）](#3-デバイスカタログaabordzoncojp限定)
4. [HEMS機能逆引き表](#4-hems機能逆引き表)
5. [推奨購入パッケージ](#5-推奨購入パッケージ)
6. [注意事項・FAQ](#6-注意事項faq)

---

## 1. 技適・PSEの基礎知識

### 1.1 なぜ技適が必要か

日本国内で無線機器を使用するには**電波法**に基づく**技術基準適合証明（技適）**が必要。技適マークのない無線機器の使用は電波法違反（1年以下の懲役または100万円以下の罰金）。

```
対象: 2.4GHz帯を使用する全デバイス
  → Wi-Fi (IEEE 802.11b/g/n/ax)
  → Bluetooth / BLE
  → Zigbee (IEEE 802.15.4)
  → Thread / Matter (802.15.4ベース)
```

### 1.2 技適の確認方法

1. **技適マーク**: 製品本体またはパッケージに `〒` に似たマークがある
2. **総務省データベース**: https://www.tele.soumu.go.jp/giteki/SearchServlet?pageID=js01 で型番検索
3. **Amazon商品ページ**: 「技適認証済み」「技適マーク取得」の記載を確認
4. **メーカー公式**: 仕様ページに技適番号（例: `R 210-XXXXXX`）の記載

### 1.3 PSE（電気用品安全法）

**AC電源に接続する製品**（スマートプラグ、USB充電アダプタ等）にはPSEマークが必要。

| マーク | 対象 | 例 |
|--------|------|-----|
| ◇PSE（ひし形） | 特定電気用品 | ACアダプタ、電源タップ |
| ○PSE（丸形） | 特定以外 | LED電球、モーター |

### 1.4 本ガイドの選定基準

本ガイドに掲載する全製品は以下を満たす:

- [x] **技適認証済み**（Wi-Fi/BLE/Zigbee使用製品）
- [x] **PSE適合**（AC電源接続製品）
- [x] **Amazon.co.jp公式または正規代理店販売**
- [x] **Home Assistant連携確認済み**
- [x] **HEMS Brain統合可能**

> AliExpress専売品（SONOFF SNZB-02P、Tuya ZY-M100等）は技適未確認のため本ガイドでは**除外**。
> これらの製品については `docs/smart-home-device-guide.md` を参照。

---

## 2. 購入チェックリスト

デバイス購入前に確認すべき項目:

```
□ 技適マーク or 技適番号の記載があるか
□ PSEマーク（AC電源製品の場合）
□ Amazon.co.jpの販売元が公式ストアまたは正規代理店か
□ Home Assistantの対応統合が存在するか
□ 日本のコンセント規格（Type A / 100V）に対応しているか
□ 必要なハブ/ゲートウェイが手元にあるか
```

---

## 3. デバイスカタログ（Amazon.co.jp限定）

> **Amazon検索リンク**: 各製品にAmazon.co.jp検索リンクを記載。クリックで直接検索結果に遷移。
> 価格は2026年3月時点の参考価格。セール時は20-40%OFFになることがある。

---

### 3.1 ハブ・コーディネーター

スマートホームの中枢。センサー/デバイスの統合に必要。

#### SONOFF ZBDongle-E（Zigbeeコーディネーター）

- **価格**: ~¥2,500
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=SONOFF%20ZBDongle-E)
- **技適**: 認証済み（EFR32MG21チップ、2.4GHz Zigbee）
- **接続**: USB → Home Assistant（ZHA or Zigbee2MQTT）
- **HEMS実現機能**:
  - Zigbeeセンサーネットワークの構築
  - ローカル制御（クラウド不要）
  - 最大100台のZigbeeデバイス管理
- **注意**: USB延長ケーブル（1-2m）でサーバーのRFノイズから離して設置すること

#### SwitchBot Hub 3（BLE/Wi-Fi/IRハブ）

- **価格**: ~¥12,980
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=SwitchBot%20Hub%203)
- **技適**: 認証済み（Wi-Fi + BLE + IR）
- **PSE**: 適合（ACアダプタ付属）
- **接続**: Wi-Fi → SwitchBot Cloud → HA統合 / Matter bridge
- **HEMS実現機能**:
  - SwitchBotデバイス最大30台のMatter bridge
  - IR家電制御（エアコン、TV、扇風機等）
  - 温湿度センサー内蔵
  - SwitchBot直接統合（`switchbot` profile）にも対応
- **備考**: IRハブ + BLEハブ + 温湿度センサーの3-in-1

#### SwitchBot Hub 2（BLE/Wi-Fi/IRハブ）

- **価格**: ~¥9,980
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=SwitchBot%20Hub%202)
- **技適**: 認証済み
- **PSE**: 適合
- **HEMS実現機能**: Hub 3と同等（Matter bridge 8台まで）+ 照度センサー内蔵

#### Nature Remo nano（Matter対応IRリモコン）

- **価格**: ~¥3,980
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=Nature%20Remo%20nano)
- **技適**: 認証済み（R 210-XXXXXX）
- **PSE**: 適合
- **接続**: Wi-Fi → **Matter native**（HAローカル制御）
- **HEMS実現機能**:
  - エアコン制御 → `control_climate` ツール
  - TV・扇風機等のIR家電制御
  - Matter経由でローカル制御（クラウド不要）
  - 最大3台のIR家電登録
- **備考**: IRハブだけ欲しい場合のコスパ最強。Matter native対応でHA統合が最もクリーン

#### Nature Remo Lapis（上位IRリモコン）

- **価格**: ~¥7,980
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=Nature%20Remo%20Lapis)
- **技適**: 認証済み
- **PSE**: 適合
- **HEMS実現機能**: nano + 温湿度センサー内蔵 + BLE対応 + IR家電20台まで

---

### 3.2 温湿度センサー

各部屋の環境モニタリングに必須。Brain の温度アラート抑制（30分）と連動。

#### Aqara 温湿度センサー（WSDCGQ11LM）

- **価格**: ~¥2,980
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=Aqara%20%E6%B8%A9%E6%B9%BF%E5%BA%A6%E3%82%BB%E3%83%B3%E3%82%B5%E3%83%BC)
- **技適**: 認証済み（Zigbee 3.0）
- **電源**: CR2032ボタン電池（約2年）
- **精度**: ±0.3°C / ±3%RH
- **接続**: Zigbee → ZBDongle-E → HA → ha-bridge → MQTT
- **HEMS実現機能**:
  - `hems/home/{zone}/sensor/sensor.{name}_temperature/state` に自動反映
  - Brain が温度データを基にエアコンON/OFF判断
  - 30分温度アラート抑制（エアコン起動後の緩やかな変化を考慮）
  - WorldModel の PhysicalSpace に温湿度反映
- **推奨数量**: 2-3台（リビング + 寝室 + 作業部屋）

#### SwitchBot 温湿度計プラス

- **価格**: ~¥2,480
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=SwitchBot%20%E6%B8%A9%E6%B9%BF%E5%BA%A6%E8%A8%88%E3%83%97%E3%83%A9%E3%82%B9)
- **技適**: 認証済み（BLE）
- **電源**: 単4電池 x2（約1年）
- **精度**: ±0.4°C / ±2%RH（スイス製センサー）
- **接続**: BLE → SwitchBot Hub → HA / SwitchBot直接統合
- **HEMS実現機能**: Aqara同等 + LCD表示で目視確認可能
- **備考**: SwitchBot Hub必須（Hub 2/3/AI Hub）

#### SwitchBot CO2センサー（温湿度+CO2）

- **価格**: ~¥7,980
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=SwitchBot%20CO2%E3%82%BB%E3%83%B3%E3%82%B5%E3%83%BC)
- **技適**: 認証済み（BLE + Wi-Fi）
- **電源**: USB-C給電
- **CO2精度**: NDIR実測（推定値ではない）
- **接続**: BLE+Wi-Fi → SwitchBot Hub → HA
- **HEMS実現機能**:
  - CO2モニタリング → 10分アラート抑制
  - CO2 > 1000ppm → Brain が換気促進タスク生成
  - CO2 > 1500ppm → 緊急アラート
  - CO2 + 窓開閉センサー連動で換気状態追跡
  - WorldModel に CO2レベル反映
- **推奨設置**: リビングまたは作業部屋（人がいる時間が長い場所）

---

### 3.3 人感・在室センサー

在室検知、スケジュール学習、睡眠検知の入力データ。

#### Aqara 人感センサー（RTCGQ11LM）— PIR

- **価格**: ~¥2,980
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=Aqara%20%E4%BA%BA%E6%84%9F%E3%82%BB%E3%83%B3%E3%82%B5%E3%83%BC)
- **技適**: 認証済み（Zigbee 3.0）
- **検知**: 170° / 7m（動体のみ）
- **電源**: CR2450（約2年）
- **HEMS実現機能**:
  - 廊下/トイレの照明自動ON/OFF
  - キッチン入室検知 → 照明制御
  - 不在時セキュリティ（想定外の動体検知アラート）
- **推奨設置**: 廊下、トイレ、キッチン（通過検知向き）
- **注意**: PIRは静止している人を検知できない → デスク作業中は反応しない

#### Aqara FP2（mmWave在室センサー）

- **価格**: ~¥7,000-9,000
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=Aqara%20FP2)
- **技適**: 認証済み（Wi-Fi）
- **検知**: ~8m、ゾーン検知（1部屋を複数ゾーンに分割可能）
- **電源**: USB-C給電
- **接続**: Wi-Fi → HA直接統合（Zigbeeハブ不要）
- **HEMS実現機能**:
  - **静止人体検知**（座り仕事中も在室と判定）
  - 睡眠検知 → 全照明OFF + カーテン全閉
  - 在室/不在 → ScheduleLearner に到着/出発パターン学習
  - 到着前HVAC予冷/予暖
  - 不在モード → 防犯照明ランダム点灯
  - ゾーン検知でリビング/ダイニング区別可能
- **推奨設置**: リビングまたは寝室（長時間滞在する部屋）
- **備考**: PIR + mmWaveの機能差は大きい。主要居室にはmmWave推奨

#### SwitchBot 人感センサー

- **価格**: ~¥2,980
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=SwitchBot%20%E4%BA%BA%E6%84%9F%E3%82%BB%E3%83%B3%E3%82%B5%E3%83%BC)
- **技適**: 認証済み（BLE）
- **検知**: 110° / 9m（PIR、動体のみ）
- **電源**: 単4電池 x2（約3年）
- **HEMS実現機能**: Aqara PIR同等
- **備考**: SwitchBot Hub必須

#### SwitchBot 人感センサーPro（mmWave）

- **価格**: ~¥3,980
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=SwitchBot%20%E4%BA%BA%E6%84%9F%E3%82%BB%E3%83%B3%E3%82%B5%E3%83%BC%20Pro)
- **技適**: 認証済み（BLE）
- **検知**: mmWave静止人体検知
- **電源**: USB給電
- **HEMS実現機能**: Aqara FP2同等（ゾーン検知なし）
- **備考**: Aqara FP2より安価だがゾーン分割不可。SwitchBot Hub必須

---

### 3.4 ドア・窓センサー

到着/出発検知と換気状態追跡。ScheduleLearner のパターン学習に直結。

#### Aqara 開閉センサー（MCCGQ11LM）

- **価格**: ~¥2,980
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=Aqara%20%E9%96%8B%E9%96%89%E3%82%BB%E3%83%B3%E3%82%B5%E3%83%BC)
- **技適**: 認証済み（Zigbee 3.0）
- **電源**: CR1632（約2年）
- **接続**: Zigbee → ZBDongle-E → HA → ha-bridge → MQTT
- **HEMS実現機能**:
  - **玄関ドア**: 到着/出発パターン学習（ScheduleLearner）
  - **窓**: CO2センサーと連動した換気状態追跡
  - 到着検知 → HVAC自動起動、照明ON
  - 出発検知 → 全照明OFF、エアコンOFF、施錠確認
  - ゲストモード自動解除
- **推奨数量**: 2台（玄関ドア + 主要な窓）

#### Aqara P2 ドアセンサー（Matter/Thread）

- **価格**: ~¥4,480
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=Aqara%20P2%20%E3%83%89%E3%82%A2%E3%82%BB%E3%83%B3%E3%82%B5%E3%83%BC)
- **技適**: 認証済み（Thread）
- **電源**: CR2477（約5年）
- **接続**: Thread → HA Matter統合
- **HEMS実現機能**: MCCGQ11LMと同等
- **備考**: 長寿命電池。Thread対応でメッシュネットワーク参加。Thread Border Router（Apple TV、HomePod mini等）が必要

#### SwitchBot 開閉センサー

- **価格**: ~¥2,480
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=SwitchBot%20%E9%96%8B%E9%96%89%E3%82%BB%E3%83%B3%E3%82%B5%E3%83%BC)
- **技適**: 認証済み（BLE）
- **電源**: 単4電池 x2（約3年）
- **HEMS実現機能**: Aqara同等
- **備考**: SwitchBot Hub必須。モーション検知機能付き

---

### 3.5 スマートプラグ

家電制御と電力監視。日本のType Aコンセント対応・PSE認証済み品のみ。

#### TP-Link Tapo P110M（推奨）

- **価格**: ~¥1,160
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=TP-Link%20Tapo%20P110M)
- **技適**: 認証済み（Wi-Fi）
- **PSE**: 適合（ひし形PSE）
- **定格**: 15A / 1500W
- **電力計測**: W / kWh
- **Matter**: 対応
- **接続**: Wi-Fi → HA統合（Matter or Tapo統合）
- **HEMS実現機能**:
  - 家電のON/OFF制御 → `control_switch` ツール
  - **電力モニタリング** → WorldModel に消費電力反映
  - 洗濯機のW値変化で完了検知 → `create_task("洗濯物を干す")` + `speak("洗濯が終わりました")`
  - 電気ケトル沸騰完了検知
  - 待機電力カット（PC周辺機器、充電器等）
- **推奨数量**: 2-4台（洗濯機、電気ケトル、PC周辺、待機電力カット用）

#### TP-Link Tapo P105

- **価格**: ~¥900
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=TP-Link%20Tapo%20P105)
- **技適**: 認証済み（Wi-Fi）
- **PSE**: 適合
- **電力計測**: なし
- **HEMS実現機能**: ON/OFF制御のみ（電力データ不要な場合に）
- **備考**: 電力計測不要ならこちらがコスパ最強

#### SwitchBot プラグミニ（JP）

- **価格**: ~¥1,980
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=SwitchBot%20%E3%83%97%E3%83%A9%E3%82%B0%E3%83%9F%E3%83%8B)
- **技適**: 認証済み（Wi-Fi + BLE）
- **PSE**: 適合
- **電力計測**: W / kWh
- **HEMS実現機能**: Tapo P110M同等
- **備考**: SwitchBotエコシステム統一したい場合に。Hub経由でMatter対応

#### Meross スマートプラグ MSS310JP

- **価格**: ~¥1,790
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=Meross%20%E3%82%B9%E3%83%9E%E3%83%BC%E3%83%88%E3%83%97%E3%83%A9%E3%82%B0%20MSS310)
- **技適**: 認証済み（Wi-Fi）
- **PSE**: 適合
- **電力計測**: W / kWh
- **HEMS実現機能**: Tapo P110M同等
- **備考**: HomeKit対応が必要な場合に

---

### 3.6 スマートライト

照明自動制御、サーカディアンリズム調整、疲労時減光。

#### SwitchBot LED電球（E26）

- **価格**: ~¥1,980
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=SwitchBot%20LED%E9%9B%BB%E7%90%83)
- **技適**: 認証済み（BLE + Wi-Fi）
- **PSE**: 適合（丸形PSE）
- **スペック**: E26口金、RGB+色温度調整、800lm
- **HEMS実現機能**:
  - `control_light(brightness, color_temp)` で直接制御
  - **サーカディアンリズム照明**: 時間帯に応じた色温度自動変化（朝: 昼白色 → 夜: 電球色）
  - **疲労時減光**: 21-23時 + 疲労スコア>60 → brightness=80, color_temp=400
  - 睡眠検知 → 全照明OFF
  - 起床検知 → brightness=255
  - 不在時防犯照明ランダム点灯
- **推奨数量**: 2-4台（リビング、寝室、作業部屋）

#### SwitchBot シーリングライトPro

- **価格**: ~¥9,980（6畳）/ ~¥11,980（8畳）
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=SwitchBot%20%E3%82%B7%E3%83%BC%E3%83%AA%E3%83%B3%E3%82%B0%E3%83%A9%E3%82%A4%E3%83%88%20Pro)
- **技適**: 認証済み（BLE + Wi-Fi + IR）
- **PSE**: 適合
- **HEMS実現機能**: LED電球同等 + **IRハブ機能内蔵**（別途Hub購入不要でエアコン等を制御可能）
- **備考**: シーリングライト + IRリモコンの2-in-1。日本の引掛シーリング対応

#### SwitchBot テープライト

- **価格**: ~¥2,480
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=SwitchBot%20%E3%83%86%E3%83%BC%E3%83%97%E3%83%A9%E3%82%A4%E3%83%88)
- **技適**: 認証済み（BLE + Wi-Fi）
- **PSE**: 適合
- **HEMS実現機能**: LED電球同等（間接照明用）

---

### 3.7 カーテン/ブラインドモーター

起床時自動開放、就寝時自動閉鎖。

#### SwitchBot カーテン3

- **価格**: ~¥8,980
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=SwitchBot%20%E3%82%AB%E3%83%BC%E3%83%86%E3%83%B33)
- **技適**: 認証済み（BLE）
- **電源**: 充電池（USB-C充電、ソーラーパネル別売 ¥2,980）
- **耐荷重**: 最大16kg
- **静音**: 25dB以下
- **HEMS実現機能**:
  - `control_cover(position)` で開閉制御（0-100%）
  - **起床前カーテン開放**: ScheduleLearner予測起床時刻の0-60分前
  - **睡眠検知**: 全閉
  - 天候連動（猛暑日は日中閉鎖等）
- **推奨数量**: 2台（寝室の左右カーテン）
- **備考**: 日本のカーテンレール規格対応。SwitchBot Hub必須

#### SwitchBot ブラインドポール

- **価格**: ~¥4,980
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=SwitchBot%20%E3%83%96%E3%83%A9%E3%82%A4%E3%83%B3%E3%83%89%E3%83%9D%E3%83%BC%E3%83%AB)
- **技適**: 認証済み（BLE）
- **HEMS実現機能**: カーテン3同等（ブラインド用）

---

### 3.8 スマートロック

施錠/解錠自動化。

#### SwitchBot ロックPro

- **価格**: ~¥17,980
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=SwitchBot%20%E3%83%AD%E3%83%83%E3%82%AF%20Pro)
- **技適**: 認証済み（BLE）
- **認証方式**: 指紋 / NFCカード / 暗証番号 / アプリ
- **暗号化**: AES-128
- **HEMS実現機能**:
  - 出発検知 → 自動施錠
  - 到着検知 → 自動解錠（オプション）
  - 施錠状態 → WorldModel に反映
  - ゲストモード時の一時キー発行
- **備考**: 日本のサムターン規格対応。SwitchBot Hub必須（遠隔操作時）

#### SESAME 5

- **価格**: ~¥4,980
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=SESAME%205)
- **技適**: 認証済み（BLE）
- **HEMS実現機能**: ロックPro同等（指紋認証なし）
- **備考**: コスパ重視の選択肢。Wi-Fiモジュール別売

---

### 3.9 水漏れセンサー

#### SwitchBot 水漏れセンサー

- **価格**: ~¥1,480
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=SwitchBot%20%E6%B0%B4%E6%BC%8F%E3%82%8C%E3%82%BB%E3%83%B3%E3%82%B5%E3%83%BC)
- **技適**: 認証済み（BLE）
- **電源**: 単4電池 x2（約2年）
- **HEMS実現機能**:
  - 漏水検知 → **urgency=4の緊急タスク生成** + `speak` で音声アラート
  - 100dBブザー内蔵
- **推奨設置**: シンク下、洗濯機周辺、浴室入口

---

### 3.10 振動センサー

#### Aqara 振動センサー（DJT11LM）

- **価格**: ~¥2,500
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=Aqara%20%E6%8C%AF%E5%8B%95%E3%82%BB%E3%83%B3%E3%82%B5%E3%83%BC)
- **技適**: 認証済み（Zigbee 3.0）
- **電源**: CR2032（約2年）
- **HEMS実現機能**:
  - 洗濯機に貼付 → 振動停止検知 → `create_task("洗濯物を干す")` + `speak("洗濯が終わりました")`
  - 乾燥機完了検知
  - ドア振動でノック検知（応用）

---

### 3.11 シーンスイッチ/リモートボタン

#### SwitchBot リモートボタン

- **価格**: ~¥1,980
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=SwitchBot%20%E3%83%AA%E3%83%A2%E3%83%BC%E3%83%88%E3%83%9C%E3%82%BF%E3%83%B3)
- **技適**: 認証済み（BLE）
- **HEMS実現機能**:
  - 物理ボタンでシーン実行（おやすみシーン、外出シーン等）
  - `execute_scene` ツール連動
- **備考**: ベッドサイドに設置して「おやすみボタン」として便利

---

### 3.12 スマートリレー/壁スイッチ

既存の壁スイッチ裏に設置。見た目変更なしでスマート化。

#### SwitchBot Relay Switch 1PM

- **価格**: ~¥3,980
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=SwitchBot%20%E3%83%AA%E3%83%AC%E3%83%BC%E3%82%B9%E3%82%A4%E3%83%83%E3%83%81)
- **技適**: 認証済み（Wi-Fi）
- **PSE**: 適合
- **Matter**: native対応
- **電力計測**: あり
- **HEMS実現機能**:
  - 既存照明のスマート化（工事不要、スイッチボックス内設置）
  - `control_switch` ツールで制御
  - 電力計測データ → WorldModel
- **備考**: 中性線不要。日本の住宅配線に対応。**電気工事士資格は不要**（スイッチボックス内の低電圧側作業）

---

### 3.13 バイオメトリクスデバイス（スマートバンド）

心拍数、睡眠、活動量、ストレスの継続追跡。

#### Xiaomi Smart Band 9

- **価格**: ~¥5,990
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=Xiaomi%20Smart%20Band%209)
- **技適**: 認証済み（BLE）
- **計測項目**: 心拍数、SpO2、睡眠（ステージ分析）、歩数、ストレス
- **電池寿命**: 最大21日
- **接続**: Mi Fitness アプリ → Health Connect → Gadgetbridge → biometric-bridge webhook
- **HEMS実現機能**（`biometric` profile）:
  - `get_biometrics` ツール: リアルタイム心拍数・ストレス取得
  - `get_sleep_summary` ツール: 昨夜の睡眠サマリー
  - **疲労スコア計算**（HR 30% + 睡眠 40% + ストレス 30%）
  - 高心拍アラート（HR > 120）
  - 低心拍アラート（HR < 45）
  - SpO2低下アラート（SpO2 < 92）
  - 高ストレスアラート（ストレス > 80）
  - 疲労連動照明減光
  - 睡眠検知 → 照明OFF連動
  - ScheduleLearner に睡眠データ提供（起床パターン学習）
- **備考**: コスパ最強のバイオメトリクスデバイス。詳細は `docs/smartband-setup.md` 参照

#### Xiaomi Smart Band 8

- **価格**: ~¥4,490
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=Xiaomi%20Smart%20Band%208)
- **技適**: 認証済み（BLE）
- **HEMS実現機能**: Smart Band 9同等（旧モデル、在庫限り）

---

### 3.14 カメラ（パーセプション用）

人体検知 + 姿勢/活動量トラッキング。

#### ESP32カメラモジュール（FREENOVE ESP32-WROVER）

- **価格**: ~¥2,000-3,000
- **Amazon**: [Amazon.co.jpで検索](https://www.amazon.co.jp/s?k=Freenove%20ESP32%20WROVER%20%E3%82%AB%E3%83%A1%E3%83%A9)
- **技適**: ESP32-WROVER-B/Eは技適認証済み（Wi-Fi + BLE）
- **センサー**: OV2640（2MP、最大1600x1200）
- **接続**: MQTT（MCP request/response）→ perception サービス
- **HEMS実現機能**（`perception` profile）:
  - YOLOv11s-pose による人体検知 + 17点スケルトン抽出
  - 姿勢分類（立位/座位/臥位/歩行）
  - 活動レベルトラッキング（0.0-1.0）
  - 長時間座位検知 → 休憩促進アラート
  - 在室/不在検知（カメラベース）
- **プライバシー**: RAM処理のみ、画像保存なし、人体クラスのみ（顔認識なし）
- **備考**: ファームウェアは `edge/test-edge/` を参照。ESP32の技適番号は`R 210-XXXXXX`（Espressif公式で確認可能）

---

## 4. HEMS機能逆引き表

「この機能を実現したい」→「何を買えばよいか」の逆引き。

| やりたいこと | 必要なデバイス | 最低予算 |
|-------------|---------------|---------|
| エアコン自動制御 | IRハブ + 温湿度センサー | ~¥7,000 |
| 在室/不在検知 | PIRセンサー or mmWaveセンサー | ~¥3,000 |
| 静止状態でも在室検知 | mmWaveセンサー（FP2 or SwitchBot Pro） | ~¥4,000 |
| 到着/出発パターン学習 | ドアセンサー（玄関） | ~¥2,500 |
| 起床時カーテン自動開放 | カーテンモーター + Hub | ~¥22,000 |
| 睡眠検知→照明OFF | mmWaveセンサー or バイオメトリクス | ~¥4,000 |
| 洗濯完了通知 | 振動センサー or スマートプラグ（電力計測） | ~¥1,200 |
| CO2換気促進 | CO2センサー + 窓開閉センサー | ~¥10,500 |
| 水漏れ緊急アラート | 水漏れセンサー | ~¥1,500 |
| 疲労連動照明 | スマートライト + スマートバンド | ~¥8,000 |
| サーカディアン照明 | スマートライト（色温度対応） | ~¥2,000 |
| 電力消費モニタリング | スマートプラグ（電力計測付き） | ~¥1,200 |
| 防犯照明（不在時） | スマートライト + 在室センサー | ~¥5,000 |
| 心拍/ストレスモニタリング | スマートバンド | ~¥5,000 |
| 人体姿勢トラッキング | ESP32カメラ | ~¥3,000 |
| 施錠自動化 | スマートロック + Hub | ~¥18,000 |
| 物理ボタンでシーン実行 | リモートボタン + Hub | ~¥15,000 |
| 既存壁スイッチのスマート化 | リレースイッチ | ~¥4,000 |

---

## 5. 推奨購入パッケージ

全てAmazon.co.jpで購入可能。技適・PSE認証済み。

### 5.1 ミニマムスタート（~¥12,000）

最低限の環境モニタリングとIR家電制御。

| # | 製品 | 数量 | 単価 | 小計 |
|---|------|------|------|------|
| 1 | Nature Remo nano | 1 | ¥3,980 | ¥3,980 |
| 2 | Aqara 温湿度センサー | 1 | ¥2,980 | ¥2,980 |
| 3 | Aqara 人感センサー | 1 | ¥2,980 | ¥2,980 |
| 4 | TP-Link Tapo P110M | 1 | ¥1,160 | ¥1,160 |
| | | | **合計** | **~¥11,100** |

**必要な追加機材**: SONOFF ZBDongle-E（¥2,500）+ Home Assistant実行環境

**実現できるHEMS機能**:
- エアコン自動制御（温度ベース）
- 在室検知（動体）
- 洗濯完了検知（電力監視）
- 基本的な WorldModel 構築

---

### 5.2 スタンダード（~¥28,000）

主要なHEMS機能をカバー。

| # | 製品 | 数量 | 単価 | 小計 |
|---|------|------|------|------|
| 1 | SONOFF ZBDongle-E | 1 | ¥2,500 | ¥2,500 |
| 2 | Aqara 温湿度センサー | 2 | ¥2,980 | ¥5,960 |
| 3 | Aqara 人感センサー | 1 | ¥2,980 | ¥2,980 |
| 4 | Aqara 開閉センサー | 2 | ¥2,980 | ¥5,960 |
| 5 | Nature Remo nano | 1 | ¥3,980 | ¥3,980 |
| 6 | TP-Link Tapo P110M | 2 | ¥1,160 | ¥2,320 |
| 7 | SwitchBot LED電球 | 2 | ¥1,980 | ¥3,960 |
| | | | **合計** | **~¥27,660** |

**実現できるHEMS機能**:
- ミニマムの全機能
- 到着/出発パターン学習（ScheduleLearner）
- 複数部屋の温湿度監視
- 照明自動制御 + サーカディアンリズム
- 窓開閉による換気追跡
- 不在時防犯照明

---

### 5.3 フル装備（~¥75,000）

全HEMS機能を活用。

| # | 製品 | 数量 | 単価 | 小計 |
|---|------|------|------|------|
| | **= スタンダード =** | | | **¥27,660** |
| 8 | SwitchBot Hub 3 | 1 | ¥12,980 | ¥12,980 |
| 9 | Aqara FP2 mmWave | 1 | ¥8,000 | ¥8,000 |
| 10 | SwitchBot カーテン3 | 2 | ¥8,980 | ¥17,960 |
| 11 | SwitchBot 水漏れセンサー | 1 | ¥1,480 | ¥1,480 |
| 12 | Aqara 振動センサー | 1 | ¥2,500 | ¥2,500 |
| 13 | Xiaomi Smart Band 9 | 1 | ¥5,990 | ¥5,990 |
| | | | **合計** | **~¥76,570** |

> Hub 3購入時はNature Remo nanoのIR機能と重複。nanoを省略可（-¥3,980 → ~¥72,590）

**追加で実現できるHEMS機能**:
- スタンダードの全機能
- 静止人体検知（mmWave）
- カーテン自動開閉（起床/就寝連動）
- 水漏れ緊急アラート
- 洗濯完了通知（振動検知）
- バイオメトリクス全機能（心拍/睡眠/ストレス/疲労スコア）
- 疲労連動照明減光
- SwitchBotデバイスMatter bridge

---

### 5.4 フル装備 + セキュリティ（~¥100,000）

ロック + CO2 + 追加センサー。

| # | 製品 | 数量 | 単価 | 小計 |
|---|------|------|------|------|
| | **= フル装備 =** | | | **¥76,570** |
| 14 | SwitchBot ロックPro | 1 | ¥17,980 | ¥17,980 |
| 15 | SwitchBot CO2センサー | 1 | ¥7,980 | ¥7,980 |
| | | | **合計** | **~¥102,530** |

**追加で実現できるHEMS機能**:
- 施錠自動化（出発→自動施錠、到着→自動解錠）
- CO2モニタリング + 換気促進アラート

---

## 6. 注意事項・FAQ

### 6.1 技適に関するFAQ

**Q: AliExpressで買ったセンサーは使えないの？**
A: 技適マークのない無線機器の使用は電波法違反。ただし、実際の取り締まりは稀であり、SONOFF等の一部製品は技適を取得している場合がある。総務省データベースで型番確認を推奨。本ガイドではリスクを避けるためAmazon.co.jp販売品に限定。

**Q: Zigbee製品は全て技適が必要？**
A: はい。Zigbeeは2.4GHz帯の無線通信であり技適が必要。ただし、Zigbeeコーディネーター（USBドングル）がPCに接続される場合、PC本体の技適でカバーされるという解釈もある（グレーゾーン）。センサー側は個別に技適が必要。

**Q: SwitchBot製品は技適取得済み？**
A: Amazon.co.jpで販売されているSwitchBot製品は全て技適認証済み。SwitchBot Japan が日本向けに認証を取得している。

**Q: Aqara製品は技適取得済み？**
A: Amazon.co.jpのAqara公式ストアで販売されている製品は技適認証済み。Aqaraは日本法人を設立し、日本向け認証を進めている。

### 6.2 HA（Home Assistant）実行環境

本ガイドのセンサーを活用するにはHome Assistantが必要:

| 方式 | 推奨度 | コスト | 備考 |
|------|--------|--------|------|
| **Raspberry Pi 5** | ★★★ | ~¥15,000 | 低消費電力、常時稼働向き |
| **ミニPC (N100等)** | ★★★ | ~¥20,000 | HAだけでなくHEMS全体を実行可能 |
| **既存PC (Docker)** | ★★ | ¥0 | 常時稼働が前提 |
| **Home Assistant Green** | ★★ | ~¥15,000 ($99) | HA公式、海外通販のみ |

### 6.3 購入優先順位

予算が限られている場合の推奨購入順:

1. **IRハブ**（Nature Remo nano）→ エアコン制御だけで生活の質が大幅向上
2. **温湿度センサー**（Aqara）→ Brain の判断精度が飛躍的に向上
3. **ドアセンサー**（Aqara、玄関用）→ ScheduleLearner の学習開始
4. **スマートプラグ**（Tapo P110M）→ 電力監視 + 家電制御
5. **スマートライト**（SwitchBot LED電球）→ 照明自動化
6. **mmWaveセンサー**（Aqara FP2）→ 在室検知の精度が劇的向上
7. **スマートバンド**（Xiaomi Smart Band 9）→ バイオメトリクス全機能
8. **カーテンモーター**（SwitchBot カーテン3）→ 起床体験の改善
9. **スマートロック**（SwitchBot ロックPro）→ セキュリティ強化

### 6.4 セール活用

- **Amazon プライムデー**（7月）: SwitchBot/Aqara 20-40%OFF
- **Amazon ブラックフライデー**（11月）: 全ブランド値引き
- **SwitchBot公式セール**（不定期）: switchbot.jp でセット割引
- **Amazon タイムセール**: Tapo製品が頻繁に対象

フル装備パッケージをセール時に購入すると~¥55,000-60,000で揃う可能性あり。

---

## 関連ドキュメント

- `docs/smart-home-device-guide.md` — AliExpress含むマルチプロトコル総合ガイド
- `docs/SMART_HOME_SETUP.md` — Home Assistant + HEMS統合セットアップ
- `docs/smartband-setup.md` — スマートバンド詳細セットアップ手順
- `edge/test-edge/docs/02_hardware_specs.md` — ESP32エッジノード仕様
