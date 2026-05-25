# 監査: tapo-bridge — 2026-05-25

## スコープ
- 対象 path(`services/tapo-bridge/src/`): `main.py`・`config.py`・`tapo_client.py`・`device_mapper.py`・`mqtt_publisher.py` — 計 ~408 LOC
- **監査深度**: canonical 契約(topic / route / tool / env)を grep 検証 + 構造スキャン。
- 参照 canonical doc: `docs/CLAUDE-bridges.md` §Tapo

## doc 乖離(本パスで修正適用済)

| # | doc claim | code reality (file:line) | 修正先 doc | 状態 |
|---|---|---|---|---|
| 1 | §Tapo Brain tools = 「`control_actuator` 経由」のみ | `get_power_consumption` も Tapo 専用 tool として存在(tapo `/api/devices/{ref}/status` + `/api/devices`、tool_handlers_home.py:140-178) | CLAUDE-bridges.md §Tapo | ✅ 追記 |

検証 OK(乖離なし):
- publish topic `hems/tapo/{vendor_ref}/state` + `hems/tapo/bridge/status` ✓(§4.3 と一致)。
- HTTP route `/api/devices`・`/api/devices/{ref}/status`・`/api/devices/{ref}/command` ✓。
- 30秒 polling で電力/電圧/電流/総消費 → MQTT、Device Registry `tapo.{vendor_ref}` 自動登録は doc 通り。

## 命名所見 / スコープ所見 / 可読性所見(refactor-ready)
- 特筆なし。tapo_client(python-kasa)/ device_mapper / mqtt_publisher の分割は明快。

## 後続リファクタ推奨(優先度順サマリ)
- **P0/P1/P2**: 構造スキャン範囲では特筆すべき負債なし。クリーンな bridge。
