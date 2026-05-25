# 監査: switchbot-bridge — 2026-05-25

## スコープ
- 対象 path(`services/switchbot-bridge/src/`): `main.py`・`config.py`・`switchbot_client.py`・`device_mapper.py`・`mqtt_publisher.py` — 計 ~761 LOC
- **監査深度**: canonical 契約(topic / route / tool / env)を grep 検証 + `_publish_device_state` / topic 生成を精読。
- 参照 canonical doc: `docs/CLAUDE-bridges.md` §SwitchBot、`docs/IMPLEMENTATION_MAP.md` §4.0

## doc 乖離(本パスで修正適用済)

| # | doc claim | code reality (file:line) | 修正先 doc | 状態 |
|---|---|---|---|---|
| 1 | §SwitchBot「Publishes to `hems/switchbot/*` MQTT topics」 | device/sensor state は **`hems/home/{zone}/{domain}/{entity_id}/state`**(`_publish_device_state` L35 が `device_mapper.get_mqtt_topic`、sub-entity も `hems/home/.../sensor/*` L50,63,76,93)。`hems/switchbot/` は `bridge/status` のみ | CLAUDE-bridges.md §SwitchBot | ✅ hems/home 経由を明記 |
| 2 | §4.0 トピックツリーが `hems/switchbot/{device_id}/state` | 同上、実体は `hems/home/*`。SwitchBot は HA デバイスと同じ `_update_home_device` reducer で統合される設計 | IMPLEMENTATION_MAP §4.0 | ✅ 修正 |

検証 OK(乖離なし):
- Brain tools `get_switchbot_devices` / `control_switchbot` / `send_switchbot_ir`(3)= §3.2 と一致。
- HTTP route `/api/devices`・`/api/devices/{id}/status`・`/api/devices/{id}/command`・`/api/webhook` ✓。

## 命名所見 / スコープ所見 / 可読性所見(refactor-ready)

| 優先度 | 問題 | file:line | 推奨 |
|---|---|---|---|
| P2 | SwitchBot 由来デバイスが `hems/home/*`(HA 互換)に流れる設計が canonical の「direct API(HA不要)」表現と一見矛盾(実際は topic 互換で reducer 共有という設計意図)。doc に設計意図を明記すると混乱防止 | (設計) | §SwitchBot に「topic は HA 互換、reducer を共有」と補足済 |

## 後続リファクタ推奨(優先度順サマリ)
- **P0/P1**: 無し。`_publish_device_state` の sub-entity 展開(temp/humidity/co2/power)は明快。
- **P2**: SwitchBot→hems/home の設計意図は doc 補足で解消済。root CLAUDE.md MQTT prefix 一覧(`hems/{tapo,switchbot}/*`)も同じ誤解を招くため SUMMARY で要検討。
