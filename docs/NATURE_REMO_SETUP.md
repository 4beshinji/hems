# Nature Remo 連携セットアップガイド

HEMS は Home Assistant (HA) 経由で Nature Remo デバイスを制御する。
Nature Remo は HA の公式統合がないため、HACS カスタムインテグレーションを使用する。

```
家電 (エアコン/照明/TV等)
  ← IR 信号 ← Nature Remo 本体
    → Nature Remo Cloud API
      → Home Assistant (カスタムインテグレーション)
        → ha-bridge (HEMS Docker サービス)
          → MQTT → Brain ワールドモデル → LLM / ルールエンジン
```

## 1. 前提条件

- Home Assistant が稼働していること
- HACS (Home Assistant Community Store) がインストール済みであること
- Nature Remo 本体がセットアップ済みで、Nature Remo アプリに家電が登録済みであること
- HEMS リポジトリがクローン済みで `.env` が作成済みであること

## 2. Nature Remo API トークンの取得

1. ブラウザで https://home.nature.global にアクセス
2. Nature Remo アプリと同じアカウントでログイン
3. 左下の **「Generate access token」** をクリック
4. 表示されたトークンをコピー（**一度しか表示されない**ので必ず保存）

動作確認:

```bash
curl -s -H "Authorization: Bearer YOUR_TOKEN" \
  https://api.nature.global/1/appliances | python3 -m json.tool
```

## 3. Home Assistant 側の準備

### 3.1 HACS のインストール（未導入の場合）

```bash
# HA の config ディレクトリで実行
wget -O - https://get.hacs.xyz | bash -
```

HA を再起動後、**設定 → デバイスとサービス → 統合を追加 → HACS** で初期設定。

### 3.2 Nature Remo カスタムインテグレーションの追加

推奨インテグレーション: [HomeAssistantNatureRemo](https://github.com/Haoyu-UT/HomeAssistantNatureRemo)

1. HACS → **統合** → 右上メニュー → **カスタムリポジトリ**
2. URL: `https://github.com/Haoyu-UT/HomeAssistantNatureRemo`
3. カテゴリ: **Integration** → 追加
4. HACS の統合一覧から **Nature Remo** を検索してインストール
5. HA を再起動

### 3.3 インテグレーションの設定

1. **設定 → デバイスとサービス → 統合を追加**
2. 「Nature Remo」を検索して追加
3. セクション2で取得した API トークンを入力

### 3.4 エンティティの確認

**設定 → デバイスとサービス → Nature Remo** でエンティティ一覧を確認。

| Nature Remo 家電 | HA ドメイン | エンティティ ID 例 | HEMS 対応 |
|---|---|---|---|
| エアコン | `climate` | `climate.nature_remo_ac` | `control_climate` |
| 照明 | `light` | `light.nature_remo_light` | `control_light` |
| TV/その他 IR 家電 | `switch` | `switch.nature_remo_tv` | スイッチ ON/OFF のみ |
| 温度センサー | `sensor` | `sensor.nature_remo_temperature` | ワールドモデルに反映 |
| 湿度センサー | `sensor` | `sensor.nature_remo_humidity` | ワールドモデルに反映 |
| 照度センサー | `sensor` | `sensor.nature_remo_illuminance` | ワールドモデルに反映 |
| 人感センサー | `binary_sensor` | `binary_sensor.nature_remo_motion` | ワールドモデルに反映 |
| 電力量計測 | `sensor` | `sensor.nature_remo_power` | ワールドモデルに反映 |

> **注意**: Nature Remo は IR（赤外線）ベースのため、デバイスの現在状態を取得できない場合がある（例: IR 照明の ON/OFF 状態は推定値）。

## 4. HEMS 側の設定

### 4.1 .env の編集

```bash
# Home Assistant 接続
HA_URL=http://192.168.1.100:8123          # HA の URL
HA_TOKEN=eyJ0eXAiOiJKV1QiLCJhbGci...     # HA の長期アクセストークン（Nature Remo API トークンではない）
HA_BRIDGE_URL=http://ha-bridge:8000
```

> **HA のトークン発行**: HA Web UI 左下 → ユーザー名 → セキュリティ → 長期間有効なアクセストークンを作成

### 4.2 エンティティマッピング（推奨）

Nature Remo のエンティティ ID はデフォルトで `nature_remo_*` という名前になるため、ゾーンマッピングを設定する。

`.env` に `HEMS_HA_ENTITY_MAP` を JSON で設定:

```bash
HEMS_HA_ENTITY_MAP={"climate.nature_remo_ac":{"zone":"living_room","domain":"climate"},"light.nature_remo_light":{"zone":"living_room","domain":"light"},"switch.nature_remo_tv":{"zone":"living_room","domain":"switch"},"sensor.nature_remo_temperature":{"zone":"living_room","domain":"sensor"},"sensor.nature_remo_humidity":{"zone":"living_room","domain":"sensor"}}
```

複数行で見やすく書くと:

```json
{
  "climate.nature_remo_ac": {
    "zone": "living_room",
    "domain": "climate"
  },
  "light.nature_remo_light": {
    "zone": "living_room",
    "domain": "light"
  },
  "switch.nature_remo_tv": {
    "zone": "living_room",
    "domain": "switch"
  },
  "sensor.nature_remo_temperature": {
    "zone": "living_room",
    "domain": "sensor"
  },
  "sensor.nature_remo_humidity": {
    "zone": "living_room",
    "domain": "sensor"
  }
}
```

> **注意**: `.env` では1行で記述すること。改行を含めると正しく読み込まれない。

### 4.3 SwitchBot との併用

SwitchBot と Nature Remo を同時に使う場合、`HEMS_HA_ENTITY_MAP` に両方のエンティティを含める。
同じゾーンに複数デバイスを割り当て可能。

```bash
HEMS_HA_ENTITY_MAP={"climate.nature_remo_ac":{"zone":"living_room","domain":"climate"},"light.switchbot_color_bulb_xxxx":{"zone":"living_room","domain":"light"},"cover.switchbot_curtain_zzzz":{"zone":"bedroom","domain":"cover"}}
```

### 4.4 起動

```bash
cd infra
docker compose --profile ha up -d --build
```

## 5. 動作確認

### 5.1 ha-bridge でデバイス確認

```bash
# 全デバイス一覧
curl http://localhost:8016/api/devices | python3 -m json.tool

# Nature Remo エンティティが含まれているか確認
curl -s http://localhost:8016/api/devices | python3 -c "
import json, sys
devices = json.load(sys.stdin)
for eid, state in devices.items():
    if 'nature' in eid or 'remo' in eid:
        print(f'{eid}: {state}')
"
```

### 5.2 MQTT 監視

```bash
docker exec hems-mqtt mosquitto_sub -u hems -P hems_dev_mqtt -t 'hems/home/#' -v
```

### 5.3 エアコン制御テスト

```bash
# ha-bridge 経由で直接制御テスト
curl -X POST http://localhost:8016/api/device/control \
  -H "Content-Type: application/json" \
  -d '{"entity_id":"climate.nature_remo_ac","service":"climate/set_hvac_mode","data":{"hvac_mode":"cool"}}'
```

## 6. HEMS が自動で行うこと

Nature Remo エンティティも SwitchBot 同様、以下のルールで自動制御される:

| ルール | 条件 | Nature Remo での動作例 |
|---|---|---|
| 帰宅前 HVAC | 不在、帰宅予測 ≤30分 | Nature Remo 経由でエアコン ON |
| 睡眠検知 → 消灯 | 23:00-05:00、アイドル >10分 | Nature Remo 照明 OFF |
| 起床検知 → 点灯 | 05:00-10:00、活動開始 | Nature Remo 照明 ON |
| 疲労時減光 | 21:00-23:00、疲労 >60 | Nature Remo 照明を暗く |

> **IR 制限**: Nature Remo は赤外線送信のため、`control_cover`（カーテン）には非対応。カーテン制御は SwitchBot カーテン等の専用デバイスが必要。

## 7. Nature Remo 固有の注意事項

### 状態取得の制限

Nature Remo は IR ベースのため、家電の実際の状態を正確に取得できない場合がある:

- **エアコン**: Nature Remo Cloud API が状態を記憶しているため比較的正確
- **IR 照明**: ON/OFF 状態は HA 側の推定値。物理スイッチで操作すると不一致が生じる
- **TV 等**: 電源状態の正確な取得は不可能

Brain の LLM はこの制限を考慮し、状態が不明な場合でも安全にコマンドを発行する。

### API レート制限

Nature Remo Cloud API にはレート制限がある（5req/sec/token 程度）。
HA のカスタムインテグレーションがポーリング間隔を管理するため、通常は問題にならない。

### ローカル API（上級者向け）

Nature Remo (Nano を除く) はローカル API を持っており、クラウドを経由せずに IR 信号を送信できる。
レイテンシと信頼性が向上するが、HA カスタムインテグレーション側の対応が必要。
詳細: [Nature Remo Local API Guide](https://medium.com/@kylehase/how-to-use-the-nature-remo-local-api-for-enhanced-latency-and-reliability-on-home-assistant-422150e05dd5)

## 8. トラブルシューティング

### エンティティが HA に表示されない

- Nature Remo アプリで家電が登録されているか確認
- HACS インテグレーションが最新版か確認
- HA のログで Nature Remo 関連のエラーを確認:
  ```
  設定 → システム → ログ → 「nature」で検索
  ```

### エアコンが反応しない

- Nature Remo 本体と家電の距離・向きを確認（IR は直線的）
- Nature Remo アプリから直接操作して動作するか確認
- HA の開発者ツール → サービス で `climate.set_hvac_mode` を手動実行してテスト

### ha-bridge にデバイスが表示されない

- HA 側で Nature Remo エンティティが正常に動作しているか確認
- HEMS の `_TRACKED_DOMAINS` は `light`, `climate`, `cover`, `switch`, `sensor`, `binary_sensor`
- `remote` ドメインは非対応（`switch` として登録された IR 家電は対応）

### 「デバイスが利用不可」エラー

Nature Remo Cloud API の一時的な障害の可能性がある。
Nature Remo の [ステータスページ](https://status.nature.global/) を確認。
