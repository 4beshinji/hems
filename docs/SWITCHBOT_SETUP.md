# SwitchBot 連携セットアップガイド

HEMS は Home Assistant (HA) 経由で SwitchBot デバイスを制御する。
SwitchBot 専用のコードはなく、HA のエンティティとして統一的に扱われる。

```
SwitchBot デバイス
  → Home Assistant (SwitchBot 統合)
    → ha-bridge (HEMS Docker サービス)
      → MQTT → Brain ワールドモデル → LLM / ルールエンジン
```

## 1. 前提条件

- Home Assistant が稼働していること（Docker、専用機、どちらでも可）
- SwitchBot デバイスが HA に登録済みであること
- HEMS リポジトリがクローン済みで `.env` が作成済みであること

## 2. Home Assistant 側の準備

### 2.1 SwitchBot 統合の追加

HA の Web UI から:

1. **設定 → デバイスとサービス → 統合を追加**
2. 「SwitchBot」を検索して追加
3. SwitchBot Hub がある場合は API トークンを入力（Hub 経由で IR 機器も制御可能）
4. Bluetooth 接続の場合は HA ホストの Bluetooth が有効であること

### 2.2 エンティティの確認

**設定 → デバイスとサービス → SwitchBot** でエンティティ一覧を確認。
各デバイスのエンティティ ID を控えておく。

| SwitchBot デバイス | HA ドメイン | エンティティ ID 例 |
|---|---|---|
| カラー電球 | `light` | `light.switchbot_color_bulb_xxxx` |
| シーリングライト | `light` | `light.switchbot_ceiling_light_xxxx` |
| プラグミニ | `switch` | `switch.switchbot_plug_mini_xxxx` |
| カーテン | `cover` | `cover.switchbot_curtain_xxxx` |
| ボット (スイッチ) | `switch` | `switch.switchbot_bot_xxxx` |
| 温湿度計 | `sensor` | `sensor.switchbot_meter_xxxx_temperature` |
| Hub 経由エアコン | `climate` | `climate.switchbot_ac_xxxx` |
| Hub 経由テレビ等 | `remote` | （HEMS 非対応、HA 側オートメーションで対応） |

### 2.3 長期アクセストークンの発行

1. HA Web UI 左下の **ユーザー名 → セキュリティ**
2. 「長期間有効なアクセストークン」セクションで **トークンを作成**
3. 名前: `HEMS` などを入力
4. 表示されたトークンをコピー（一度しか表示されない）

## 3. HEMS 側の設定

### 3.1 .env の編集

```bash
# Home Assistant 接続
HA_URL=http://192.168.1.100:8123          # HA の URL（IP アドレスまたはホスト名）
HA_TOKEN=eyJ0eXAiOiJKV1QiLCJhbGci...     # 2.3 で発行したトークン
HA_BRIDGE_URL=http://ha-bridge:8000       # Brain → ha-bridge 内部通信用（変更不要）
```

### 3.2 エンティティマッピング（推奨）

SwitchBot のエンティティ ID は自動生成名が長いため、ゾーンマッピングを設定する。
未設定の場合、エンティティ ID のドメイン以降がそのままゾーン名になる（例: `switchbot_color_bulb_xxxx`）。

`.env` に `HEMS_HA_ENTITY_MAP` を JSON で設定:

```bash
HEMS_HA_ENTITY_MAP={"light.switchbot_color_bulb_xxxx":{"zone":"living_room","domain":"light"},"switch.switchbot_plug_mini_yyyy":{"zone":"living_room","domain":"switch"},"cover.switchbot_curtain_zzzz":{"zone":"bedroom","domain":"cover"},"climate.switchbot_ac_wwww":{"zone":"living_room","domain":"climate"}}
```

複数行で見やすく書くと:

```json
{
  "light.switchbot_color_bulb_xxxx": {
    "zone": "living_room",
    "domain": "light"
  },
  "switch.switchbot_plug_mini_yyyy": {
    "zone": "living_room",
    "domain": "switch"
  },
  "cover.switchbot_curtain_zzzz": {
    "zone": "bedroom",
    "domain": "cover"
  },
  "climate.switchbot_ac_wwww": {
    "zone": "living_room",
    "domain": "climate"
  }
}
```

> **注意**: `.env` では1行で記述すること。改行を含めると正しく読み込まれない。

### 3.3 起動

```bash
cd infra
docker compose --profile ha up -d --build
```

HA インスタンスも Docker で動かす場合（オプション）:

```bash
# HEMS_HA_CONFIG_PATH に HA の config ディレクトリを指定
HEMS_HA_CONFIG_PATH=/path/to/ha-config docker compose --profile ha up -d --build
```

## 4. 動作確認

### 4.1 ha-bridge の接続確認

```bash
# ヘルスチェック
curl http://localhost:8016/health

# 全デバイス一覧（SwitchBot エンティティが表示されるか確認）
curl http://localhost:8016/api/devices | python3 -m json.tool
```

### 4.2 MQTT でのステータス確認

```bash
# MQTT トピックを監視（別ターミナル）
docker exec hems-mqtt mosquitto_sub -u hems -P hems_dev_mqtt -t 'hems/home/#' -v
```

SwitchBot デバイスの状態変更（HA UI またはデバイス操作）で `hems/home/{zone}/{domain}/{entity_id}/state` にメッセージが流れる。

### 4.3 Brain ログでの確認

```bash
docker logs -f hems-brain 2>&1 | grep -i "home\|light\|climate\|cover"
```

ワールドモデルの `スマートホーム` セクションに SwitchBot デバイスが表示されていれば成功。

## 5. HEMS が自動で行うこと

エンティティが正しく認識されると、以下のルールが自動的に発動する:

| ルール | 条件 | アクション |
|---|---|---|
| 睡眠検知 → 消灯 | 23:00-05:00、在室、アイドル+姿勢固定 >10分 | 全照明 OFF + 「おやすみなさい」 |
| 帰宅前 HVAC | 不在、帰宅予測 ≤30分 | 季節対応でエアコン ON |
| 起床前カーテン | 起床予測60分前、カーテン閉 | カーテン全開 |
| 起床検知 → 点灯 | 05:00-10:00、活動開始 | 全照明 ON + 「おはようございます」 |
| 疲労時減光 | 21:00-23:00、疲労スコア >60 | 照明を暗く (brightness=80) + 暖色 |
| 生体睡眠検知 | 睡眠ステージ deep/light/rem | 全照明 OFF |

LLM モードでは、AI が状況に応じて自由にデバイスを制御することもできる。

## 6. 手動制御（LLM ツール）

Brain の LLM は以下のツールで SwitchBot デバイスを制御する:

```
control_light   — ON/OFF、明るさ (0-255)、色温度 (153-500 mirek)
control_climate — モード (off/cool/heat/dry/fan_only/auto)、温度 (16-30°C)、風速
control_cover   — open/close/stop、ポジション (0-100)
get_home_devices — 全デバイス状態取得（読み取り専用）
```

安全制限: 温度 16-30°C、明るさ 0-255、カーテンポジション 0-100。

## 7. トラブルシューティング

### ha-bridge が HA に接続できない

```bash
# コンテナ内から HA に到達できるか確認
docker exec hems-ha-bridge python3 -c "
import urllib.request
req = urllib.request.Request('http://host.docker.internal:8123/api/',
    headers={'Authorization': 'Bearer YOUR_TOKEN'})
print(urllib.request.urlopen(req).read())
"
```

- `HA_URL` が Docker コンテナ内から到達可能か確認（`host.docker.internal` または実 IP）
- `HA_TOKEN` が正しいか確認
- HA の CORS 設定が問題になることがある

### デバイスが表示されない

- HA 側で SwitchBot 統合が正常に動作しているか確認
- `_TRACKED_DOMAINS` は `light`, `climate`, `cover`, `switch`, `sensor`, `binary_sensor` のみ
- `remote` ドメイン（IR リモコン等）は非対応

### エンティティ ID がわからない

```bash
# HA の REST API で全エンティティ取得
curl -s -H "Authorization: Bearer YOUR_TOKEN" \
  http://192.168.1.100:8123/api/states | python3 -m json.tool | grep entity_id
```

### WebSocket が切断される

ha-bridge は WebSocket 切断時に30秒間隔のポーリングにフォールバックする。
再接続は自動で行われる。ログで `WebSocket disconnected` / `reconnecting` を確認。
