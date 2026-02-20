# スマートホーム連携ガイド

HEMS は Home Assistant (HA) を統合レイヤーとして、各社のスマートホームデバイスを制御する。
デバイスメーカー固有のコードは持たず、HA エンティティとして統一的に扱う。

```
スマートホームデバイス
  → Home Assistant (統合 / カスタムインテグレーション)
    → ha-bridge (HEMS Docker サービス)
      → MQTT (hems/home/{zone}/{domain}/{entity_id}/state)
        → Brain ワールドモデル → LLM / ルールエンジン
          → ha-bridge REST API → HA サービスコール → デバイス制御
```

## 目次

1. [共通セットアップ](#1-共通セットアップ)
2. [SwitchBot](#2-switchbot)
3. [Nature Remo](#3-nature-remo)
4. [複数メーカー併用](#4-複数メーカー併用)
5. [エンティティマッピング](#5-エンティティマッピング)
6. [自動化ルール](#6-自動化ルール)
7. [LLM ツール](#7-llm-ツール)
8. [動作確認](#8-動作確認)
9. [トラブルシューティング](#9-トラブルシューティング)

---

## 1. 共通セットアップ

どのデバイスメーカーでも共通の手順。

### 1.1 前提条件

- Home Assistant が稼働していること（Docker / 専用機 / VM、いずれも可）
- HEMS リポジトリがクローン済みで `.env` が作成済みであること

### 1.2 HA 長期アクセストークンの発行

1. HA Web UI 左下の **ユーザー名 → セキュリティ**
2. 「長期間有効なアクセストークン」セクションで **トークンを作成**
3. 名前: `HEMS` と入力
4. 表示されたトークンをコピー（**一度しか表示されない**）

### 1.3 .env の設定

```bash
# Home Assistant 接続（必須）
HA_URL=http://192.168.1.100:8123          # HA の URL（IP またはホスト名）
HA_TOKEN=eyJ0eXAiOiJKV1QiLCJhbGci...     # 1.2 で発行したトークン
HA_BRIDGE_URL=http://ha-bridge:8000       # Brain → ha-bridge 内部通信（変更不要）

# オプション
# HEMS_PORT_HA_BRIDGE=8016               # ha-bridge ホストポート
# HEMS_HA_POLL_INTERVAL=30               # ポーリング間隔（秒、WebSocket フォールバック時）
# HEMS_HA_ENTITY_MAP={}                  # エンティティマッピング（後述）
```

### 1.4 起動

```bash
cd infra
docker compose --profile ha up -d --build
```

HA も Docker で動かす場合:

```bash
HEMS_HA_CONFIG_PATH=/path/to/ha-config docker compose --profile ha up -d --build
```

### 1.5 対応ドメイン

ha-bridge が追跡する HA ドメイン:

| HA ドメイン | HEMS での扱い | Brain ツール |
|---|---|---|
| `light` | 照明制御 | `control_light` |
| `climate` | 空調制御 | `control_climate` |
| `cover` | カーテン/ブラインド制御 | `control_cover` |
| `switch` | スイッチ ON/OFF | ワールドモデルのみ |
| `sensor` | センサー値 | ワールドモデルのみ |
| `binary_sensor` | 二値センサー | ワールドモデルのみ |

> `remote` ドメインは非対応。IR リモコン系は `switch` として登録された場合のみ対応。

---

## 2. SwitchBot

### 2.1 HA 統合の追加

SwitchBot は HA 公式統合が利用可能。

1. **設定 → デバイスとサービス → 統合を追加**
2. 「SwitchBot」を検索して追加
3. SwitchBot Hub がある場合は API トークンを入力（Hub 経由で IR 機器も制御可能）
4. Bluetooth 接続の場合は HA ホストの Bluetooth が有効であること

### 2.2 デバイス対応表

| SwitchBot デバイス | HA ドメイン | エンティティ ID 例 | HEMS 制御 |
|---|---|---|---|
| カラー電球 | `light` | `light.switchbot_color_bulb_xxxx` | `control_light` |
| シーリングライト | `light` | `light.switchbot_ceiling_light_xxxx` | `control_light` |
| プラグミニ | `switch` | `switch.switchbot_plug_mini_xxxx` | 状態監視 |
| カーテン | `cover` | `cover.switchbot_curtain_xxxx` | `control_cover` |
| ボット | `switch` | `switch.switchbot_bot_xxxx` | 状態監視 |
| 温湿度計 | `sensor` | `sensor.switchbot_meter_xxxx_temperature` | 状態監視 |
| Hub 経由エアコン | `climate` | `climate.switchbot_ac_xxxx` | `control_climate` |
| Hub 経由テレビ等 | `remote` | — | **非対応** |

### 2.3 SwitchBot の特徴

- **Bluetooth + クラウド**: ローカル通信とクラウド API の両方に対応
- **状態取得**: 双方向通信のためデバイス状態は正確
- **カーテン制御**: SwitchBot カーテンは `cover` ドメインとして制御可能（ポジション 0-100）
- **Hub 不要**: Bluetooth 範囲内なら Hub なしで HA 直接接続

---

## 3. Nature Remo

### 3.1 Nature Remo API トークンの取得

Nature Remo の HA インテグレーションには Cloud API トークンが必要。

1. https://home.nature.global にアクセス
2. Nature Remo アプリと同じアカウントでログイン
3. 左下の **「Generate access token」** をクリック
4. トークンをコピー（**一度しか表示されない**）

動作確認:

```bash
curl -s -H "Authorization: Bearer YOUR_NATURE_REMO_TOKEN" \
  https://api.nature.global/1/appliances | python3 -m json.tool
```

### 3.2 HACS カスタムインテグレーションの追加

Nature Remo は HA 公式統合がないため、HACS 経由でカスタムインテグレーションを導入する。

**HACS 未導入の場合:**

```bash
# HA の config ディレクトリで実行
wget -O - https://get.hacs.xyz | bash -
```

HA 再起動後、**設定 → デバイスとサービス → 統合を追加 → HACS** で初期設定。

**Nature Remo インテグレーションの追加:**

推奨: [HomeAssistantNatureRemo](https://github.com/Haoyu-UT/HomeAssistantNatureRemo)

1. HACS → **統合** → 右上メニュー → **カスタムリポジトリ**
2. URL: `https://github.com/Haoyu-UT/HomeAssistantNatureRemo`
3. カテゴリ: **Integration** → 追加
4. 統合一覧から **Nature Remo** をインストール
5. HA を再起動
6. **設定 → デバイスとサービス → 統合を追加 → Nature Remo**
7. 3.1 で取得した API トークンを入力

### 3.3 デバイス対応表

| Nature Remo 家電 | HA ドメイン | エンティティ ID 例 | HEMS 制御 |
|---|---|---|---|
| エアコン | `climate` | `climate.nature_remo_ac` | `control_climate` |
| 照明 | `light` | `light.nature_remo_light` | `control_light` |
| TV/その他 IR 家電 | `switch` | `switch.nature_remo_tv` | 状態監視 |
| 温度センサー | `sensor` | `sensor.nature_remo_temperature` | 状態監視 |
| 湿度センサー | `sensor` | `sensor.nature_remo_humidity` | 状態監視 |
| 照度センサー | `sensor` | `sensor.nature_remo_illuminance` | 状態監視 |
| 人感センサー | `binary_sensor` | `binary_sensor.nature_remo_motion` | 状態監視 |
| 電力量計測 | `sensor` | `sensor.nature_remo_power` | 状態監視 |

### 3.4 Nature Remo の特徴と制限

- **IR ベース**: 赤外線での一方向通信のため、状態取得に制限がある
  - エアコン: Cloud API が状態を記憶しているため比較的正確
  - IR 照明: ON/OFF は HA 側の推定値。物理スイッチ操作で不一致が生じる
  - TV 等: 電源状態の正確な取得は不可能
- **カーテン非対応**: IR では `cover` ドメインが使えない。カーテン制御には SwitchBot カーテン等が必要
- **API レート制限**: Nature Remo Cloud API は 5req/sec/token 程度。HA インテグレーションが管理するため通常問題なし
- **ローカル API（上級者向け）**: Nature Remo (Nano 除く) はローカル API を持ち、クラウド非経由で IR 送信可能。詳細: [Nature Remo Local API Guide](https://medium.com/@kylehase/how-to-use-the-nature-remo-local-api-for-enhanced-latency-and-reliability-on-home-assistant-422150e05dd5)

---

## 4. 複数メーカー併用

SwitchBot と Nature Remo を同時に使うことで、各メーカーの強みを活かせる。

### 推奨構成例

| 用途 | デバイス | 理由 |
|---|---|---|
| エアコン制御 | Nature Remo | IR リモコンの学習が容易 |
| 照明 | SwitchBot カラー電球 | 明るさ・色温度の双方向制御 |
| カーテン | SwitchBot カーテン | IR 非対応のためモーター式が必要 |
| 温湿度監視 | Nature Remo 内蔵センサー | 追加デバイス不要 |
| コンセント制御 | SwitchBot プラグミニ | 消費電力モニタリング付き |

### 併用時の .env 設定

`HEMS_HA_ENTITY_MAP` に全メーカーのエンティティをまとめて記述する:

```bash
HEMS_HA_ENTITY_MAP={"climate.nature_remo_ac":{"zone":"living_room","domain":"climate"},"light.switchbot_color_bulb_xxxx":{"zone":"living_room","domain":"light"},"cover.switchbot_curtain_zzzz":{"zone":"bedroom","domain":"cover"},"sensor.nature_remo_temperature":{"zone":"living_room","domain":"sensor"},"switch.switchbot_plug_mini_yyyy":{"zone":"living_room","domain":"switch"}}
```

---

## 5. エンティティマッピング

### デフォルト動作

マッピング未設定の場合、エンティティ ID の `.` 以降がゾーン名になる:

```
light.living_room           → zone: living_room  (意図通り)
light.switchbot_color_bulb  → zone: switchbot_color_bulb  (意図しない)
climate.nature_remo_ac      → zone: nature_remo_ac  (意図しない)
```

自動生成名が長い SwitchBot / Nature Remo ではマッピング設定を推奨。

### HEMS_HA_ENTITY_MAP の書式

`.env` に JSON 文字列で設定（**1行で記述**、改行不可）:

```bash
HEMS_HA_ENTITY_MAP={"entity_id":{"zone":"zone_name","domain":"domain_name"}, ...}
```

見やすい形式（設定時は1行に変換すること）:

```json
{
  "light.switchbot_color_bulb_xxxx": {
    "zone": "living_room",
    "domain": "light"
  },
  "climate.nature_remo_ac": {
    "zone": "living_room",
    "domain": "climate"
  },
  "cover.switchbot_curtain_zzzz": {
    "zone": "bedroom",
    "domain": "cover"
  }
}
```

### MQTT トピック

マッピング後の MQTT トピック:

```
hems/home/living_room/light/light.switchbot_color_bulb_xxxx/state
hems/home/living_room/climate/climate.nature_remo_ac/state
hems/home/bedroom/cover/cover.switchbot_curtain_zzzz/state
```

### エンティティ ID の確認方法

```bash
# HA REST API で全エンティティ取得
curl -s -H "Authorization: Bearer YOUR_HA_TOKEN" \
  http://192.168.1.100:8123/api/states | python3 -m json.tool | grep entity_id

# ha-bridge 経由（HEMS 起動後）
curl -s http://localhost:8016/api/devices | python3 -m json.tool
```

---

## 6. 自動化ルール

エンティティが認識されると、以下のルールが自動発動する:

| ルール | 条件 | アクション |
|---|---|---|
| 睡眠検知 → 消灯 | 23:00-05:00、在室、アイドル+姿勢固定 >10分 | 全 `light` OFF + 「おやすみなさい」 |
| 帰宅前 HVAC | 不在、帰宅予測 ≤30分 | 全 `climate` ON（季節対応: 夏=冷房26°C, 冬=暖房22°C） |
| 起床前カーテン | 起床予測60分前、カーテン閉 | 全 `cover` 全開 |
| 起床検知 → 点灯 | 05:00-10:00、活動開始 | 全 `light` ON (brightness=255) + 「おはようございます」 |
| 疲労時減光 | 21:00-23:00、疲労スコア >60 | `light` brightness=80, color_temp=400 (暖色) |
| 生体睡眠検知 | 睡眠ステージ deep/light/rem | 全 `light` OFF |

> **デバイス選択**: ルールは HA ドメイン単位で発動する。SwitchBot 照明も Nature Remo 照明も `light` ドメインなら同時に制御される。

LLM モードでは、AI が環境・生体情報を総合的に判断し、状況に応じて自由にデバイスを制御することもできる。

---

## 7. LLM ツール

Brain が使用するスマートホーム制御ツール:

| ツール | 対象ドメイン | パラメータ | 安全制限 |
|---|---|---|---|
| `control_light` | `light` | entity_id, on (bool), brightness (0-255), color_temp (153-500 mirek) | 範囲バリデーション |
| `control_climate` | `climate` | entity_id, mode (off/cool/heat/dry/fan_only/auto), temperature (16-30°C), fan_mode | 温度 16-30°C |
| `control_cover` | `cover` | entity_id, action (open/close/stop), position (0-100) | ポジション 0-100 |
| `get_home_devices` | 全ドメイン | — | 読み取り専用 |

---

## 8. 動作確認

### 8.1 ha-bridge 接続

```bash
# ヘルスチェック
curl http://localhost:8016/health

# 全デバイス一覧
curl http://localhost:8016/api/devices | python3 -m json.tool
```

### 8.2 MQTT 監視

```bash
docker exec hems-mqtt mosquitto_sub -u hems -P hems_dev_mqtt -t 'hems/home/#' -v
```

デバイスの状態変更で `hems/home/{zone}/{domain}/{entity_id}/state` にメッセージが流れることを確認。

### 8.3 制御テスト

```bash
# 照明 ON
curl -X POST http://localhost:8016/api/device/control \
  -H "Content-Type: application/json" \
  -d '{"entity_id":"light.switchbot_color_bulb_xxxx","service":"light/turn_on","data":{"brightness":200}}'

# エアコン 冷房モード
curl -X POST http://localhost:8016/api/device/control \
  -H "Content-Type: application/json" \
  -d '{"entity_id":"climate.nature_remo_ac","service":"climate/set_hvac_mode","data":{"hvac_mode":"cool"}}'

# カーテン 全開
curl -X POST http://localhost:8016/api/device/control \
  -H "Content-Type: application/json" \
  -d '{"entity_id":"cover.switchbot_curtain_zzzz","service":"cover/open_cover","data":{}}'
```

### 8.4 Brain ログ

```bash
docker logs -f hems-brain 2>&1 | grep -i "home\|light\|climate\|cover"
```

ワールドモデルの「スマートホーム」セクションにデバイスが表示されていれば成功。

---

## 9. トラブルシューティング

### 共通

| 症状 | 確認事項 |
|---|---|
| ha-bridge が HA に接続できない | `HA_URL` がコンテナ内から到達可能か (`host.docker.internal` or 実IP)。`HA_TOKEN` が正しいか |
| デバイスが ha-bridge に表示されない | HA 側でエンティティが正常に動作しているか。対応ドメイン (`light`, `climate`, `cover`, `switch`, `sensor`, `binary_sensor`) か |
| WebSocket 切断 | 自動再接続 + 30秒ポーリングフォールバック。ログで `reconnecting` を確認 |
| エンティティ ID がわからない | HA REST API: `curl -s -H "Authorization: Bearer TOKEN" http://HA:8123/api/states \| grep entity_id` |

**HA 接続テスト:**

```bash
docker exec hems-ha-bridge python3 -c "
import urllib.request
req = urllib.request.Request('http://host.docker.internal:8123/api/',
    headers={'Authorization': 'Bearer YOUR_TOKEN'})
print(urllib.request.urlopen(req).read())
"
```

### SwitchBot 固有

| 症状 | 確認事項 |
|---|---|
| Bluetooth デバイスが見つからない | HA ホストの Bluetooth が有効か。デバイスとの距離 |
| Hub 経由デバイスが不安定 | SwitchBot Hub のファームウェア更新。Wi-Fi 接続状態 |
| `remote` ドメインが制御できない | HEMS 非対応。HA 側のオートメーションで対応 |

### Nature Remo 固有

| 症状 | 確認事項 |
|---|---|
| エンティティが HA に表示されない | HACS インテグレーション最新版か。Nature Remo アプリで家電登録済みか。HA ログで `nature` 検索 |
| エアコンが反応しない | Remo 本体と家電の距離・向き（IR は直線的）。Nature Remo アプリから直接操作テスト |
| 照明の ON/OFF が実態と不一致 | IR ベースの制限。物理スイッチ操作で乖離する。Brain LLM は不一致を許容して動作する |
| 「デバイスが利用不可」 | Nature Remo Cloud API の障害。[ステータスページ](https://status.nature.global/) 確認 |
| API レート制限エラー | HA インテグレーションのポーリング間隔を延長 |
