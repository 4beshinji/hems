# 買い物リスト 使用ガイド

Brain と統合された買い物リスト機能。音声・API・Brain の自動検出で買い物メモを管理し、
外出時の持ち物リマインダーや定期購入の自動リマインドに対応する。

## 基本的な使い方

### API で直接操作する

```bash
BASE=http://localhost:8010
KEY=your-api-key

# リスト取得 (未購入のみ)
curl -H "X-API-Key: $KEY" $BASE/shopping/

# カテゴリ絞り込み
curl -H "X-API-Key: $KEY" "$BASE/shopping/?category=食品"

# アイテム追加
curl -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  $BASE/shopping/ -d '{
    "name": "牛乳",
    "category": "食品",
    "quantity": 2,
    "unit": "本",
    "store": "スーパー",
    "priority": 1
  }'

# 更新 (部分更新)
curl -X PATCH -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  $BASE/shopping/{id} -d '{"quantity": 3, "priority": 2}'

# 購入済みにする
curl -X PUT -H "X-API-Key: $KEY" $BASE/shopping/{id}/purchase

# 削除
curl -X DELETE -H "X-API-Key: $KEY" $BASE/shopping/{id}
```

### Dashboard から操作する

Frontend の **Digital** ページに買い物リストウィジェットがある。
チェックで購入済みにマーク、編集ボタンで詳細を変更できる。

## アイテムのフィールド

| フィールド | 説明 | 例 |
|-----------|------|-----|
| `name` | 商品名 (必須) | `"牛乳"` |
| `category` | カテゴリ | `"食品"`, `"日用品"`, `"薬"` |
| `quantity` | 個数 | `2` |
| `unit` | 単位 | `"本"`, `"個"`, `"袋"` |
| `store` | 購入予定店舗 | `"スーパー"`, `"薬局"` |
| `price` | 想定価格 (円) | `250` |
| `priority` | 優先度。Brain tool schema では `0=低, 1=通常, 2=高`。backend では `int` として受け入れる。 | `0` (低) / `1` (通常) / `2` (高) |
| `notes` | メモ | `"特売の時だけ"` |
| `is_recurring` | 定期購入 | `true` |
| `recurrence_days` | 定期間隔 (日) | `30` |

## 定期購入アイテム

`is_recurring: true` + `recurrence_days` を設定すると、購入済みにした日から
`recurrence_days` 日後に自動的に同じアイテムが再登録される。

```bash
# API で定期購入アイテムを追加 (例: 30日ごとに洗剤)
curl -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  $BASE/shopping/ -d '{
    "name": "洗剤",
    "category": "日用品",
    "is_recurring": true,
    "recurrence_days": 30
  }'

# 期限切れの定期アイテムを確認
curl -H "X-API-Key: $KEY" $BASE/shopping/due

# 定期アイテム一覧
curl -H "X-API-Key: $KEY" $BASE/shopping/recurring
```

Brain は購入期限を過ぎた定期アイテムを自動検出して音声でリマインドする。

## Brain との連携

### 外出時の買い物リマインダー

Brain の world model は複数の情報源（在室センサー、HA Bridge、PC 状態、日程など）を
組み合わせて在室ゼロを判定する。HA Bridge は情報源の一つ。
在室ゼロが判定され、未購入アイテムがあれば外出前に「買い物リストに○件あります」と音声通知する。

→ HA Bridge 設定: [`SMART_HOME_SETUP.md`](SMART_HOME_SETUP.md) 参照

### 定期購入のリマインド

Brain の ReAct ループ中に `due_items` を確認し、期限切れの定期アイテムがあれば
「洗剤の購入期限が来ています」のように通知する。

### 統計情報

```bash
# 購入統計
curl -H "X-API-Key: $KEY" $BASE/shopping/stats
# → {
#     "total_items": 15,
#     "purchased_items": 10,
#     "pending_items": 5,
#     "total_spent_this_month": 3250,
#     "category_breakdown": {...}
#   }
```

## リストの共有

> ⚠️ 共有リンク機能は現状動作しない。以下の実装バグがある:
> - `services/backend/main.py` で `shopping.public_router` が `include_router` されていない。
> - `share_url` が `/shopping/shared/` 形式だが、nginx 設定では backend に到達しない。
>
> 修正完了までは、外出先で確認する際は backend API または Dashboard を直接使うこと。

外出先でスマートフォンから確認できるよう、認証不要の共有リンクを生成できる予定。

```bash
# 共有リンクを発行 (認証が必要)
curl -X POST -H "X-API-Key: $KEY" $BASE/shopping/0/share
# → {"share_url": "http://localhost:8080/shopping/shared/xxxx", "token": "xxxx", ...}

# 発行された URL は認証なしでアクセス可能 (将来の予定)
curl http://localhost:8080/api/shopping/shared/xxxx
```

外部から接続する場合は `.env` の `HEMS_EXTERNAL_URL` を設定する:

```bash
HEMS_EXTERNAL_URL=http://192.168.1.100:8080
```

## REST API 一覧

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/shopping/` | 未購入アイテム一覧 |
| POST | `/shopping/` | アイテム追加 |
| GET | `/shopping/{id}` | 詳細取得 |
| PATCH | `/shopping/{id}` | 部分更新 |
| DELETE | `/shopping/{id}` | 削除 |
| PUT | `/shopping/{id}/purchase` | 購入済みにする |
| GET | `/shopping/due` | 期限切れの定期アイテム |
| GET | `/shopping/recurring` | 定期アイテム一覧 |
| GET | `/shopping/stats` | 購入統計 |
| POST | `/shopping/{id}/share` | 共有トークン生成 |
| GET | `/shopping/shared/{token}` | 共有リンクから取得 (未マウント、現状動作しない) |

## MQTT イベント

買い物リストの変更は MQTT で通知される。他のサービスやスマートフォンアプリから購読できる。

| トピック | タイミング | ペイロード例 |
|---------|-----------|-------------|
| `hems/shopping/added` | アイテム追加時 | `{"id": 1, "name": "牛乳", "category": "食品"}` |
| `hems/shopping/updated` | アイテム更新時 | `{"id": 1, "name": "牛乳"}` |
| `hems/shopping/purchased` | 購入済みにした時 | `{"id": 1, "name": "牛乳", "price": null}` |

```bash
# MQTT で購読する例
# mosquitto ACL に 'hems' ユーザーが存在しないため、ACL で購読を許可した読み取り専用ユーザーを使う。
mosquitto_sub -h localhost -p 1893 -u readonly -P readonly_password \
  -t "hems/shopping/#" -v
```

ACL に適切な読み取りユーザーがない場合は、backend API または Dashboard/SSE 経由で変化を確認する:

```bash
# 最新の未購入アイテムをポーリングする例
curl -H "X-API-Key: $KEY" $BASE/shopping/
```

## トラブルシューティング

**Brain が買い物を追加してくれない**
→ Brain の LLM が `add_shopping_item` ツールを持っているか確認 (`GET /api/tools` は未実装のため Brain ログで確認):

```bash
docker logs hems-brain | grep "add_shopping"
```

**定期アイテムが再登録されない**
→ 購入済みにした後、`next_purchase_at` が設定されているか確認:

```bash
curl -H "X-API-Key: $KEY" $BASE/shopping/?include_purchased=true | \
  python3 -m json.tool | grep -A5 "is_recurring"
```

**外出リマインダーが来ない**
→ Brain の world model が在室ゼロを判定するための情報源（HA Bridge、在室センサー、PC 状態など）が
正常に動作しているか確認。HA Bridge (profile: `ha`) は情報源の一つ。
