# 監査: ha-bridge — 2026-05-25

## スコープ
- 対象 path(`services/ha-bridge/src/`): `main.py`・`config.py`・`ha_client.py`・`entity_mapper.py`・`mqtt_publisher.py` — 計 ~555 LOC
- **監査深度**: canonical 契約(topic / route / tool / safety / env)を grep 検証 + 構造スキャン。
- 参照 canonical doc: `docs/CLAUDE-bridges.md` §HA、`docs/IMPLEMENTATION_MAP.md` §8

## doc 乖離(本パスで修正適用済)

| # | doc claim | code reality (file:line) | 修正先 doc | 状態 |
|---|---|---|---|---|
| 1 | §HA Brain tools が 7+2 件で `get_entity_status` 欠落 | tool 存在: `get_entity_status` → ha `/api/device/{entity_id}`(tool_handlers_home.py:128) | CLAUDE-bridges.md §HA | ✅ 追記 |
| 2 | §8 が ha `/api/device/{entity_id}` GET を「✗ 未ツール化」と記載 | 同上、`get_entity_status` でツール化済 | IMPLEMENTATION_MAP §8 | ✅ ✓ に修正 |

検証 OK(乖離なし):
- publish topic `hems/home/{zone}/{domain}/{entity_id}/state` + `hems/home/bridge/status` ✓(§4.3 と一致)。
- HTTP route `/api/device/control`・`/api/devices`・`/api/device/{entity_id}` ✓。
- safety(temp 16-30 / brightness 0-255 / position 0-100)は sanitizer(unit 1)と整合。
- WebSocket state_changed → MQTT、polling fallback の構成は ha_client と整合。

## 命名所見 / スコープ所見 / 可読性所見(refactor-ready)
- 特筆なし。ha_client(REST/WS)/ entity_mapper(HA entity → hems/home topic)/ mqtt_publisher の分割は明快。

## 後続リファクタ推奨(優先度順サマリ)
- **P0/P1/P2**: 構造スキャン範囲では特筆すべき負債なし。クリーンな bridge。
