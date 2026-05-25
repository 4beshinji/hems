# 監査: gas-bridge — 2026-05-25

## スコープ
- 対象 path(`services/gas-bridge/src/`): `main.py`・`config.py`・`data_poller.py`・`gas_client.py`・`mqtt_publisher.py` — 計 ~452 LOC
  (GAS 側 `scripts/gas-bridge/Code.gs` は本パス対象外)
- **監査深度**: canonical 契約(topic / route / poll 間隔 / env)を grep 検証 + 構造スキャン。
- 参照 canonical doc: `docs/CLAUDE-bridges.md` §GAS

## doc 乖離(本パスで修正適用済)

| # | doc claim | code reality | 修正先 doc | 状態 |
|---|---|---|---|---|
| 1 | §GAS に Brain tools 行が無い(Brain rules のみ) | brain tool 3 件が存在: `get_recent_emails` / `gas_query_free_slots` / `gas_query_sheet`(§3.2 + tool_dispatch) | CLAUDE-bridges.md §GAS | ✅ Brain tools 行を追加 |

検証 OK(乖離なし):
- publish topic `hems/gas/{calendar/upcoming,calendar/free_slots,tasks,gmail/summary,gmail/recent,sheets/{name},drive/recent,bridge/status}` ✓(§4.3 と一致)。
- HTTP route `/api/gas/{calendar,tasks,gmail,sheets/{name},drive,status}` ✓。
- poll 間隔(calendar 120s / tasks・gmail 300s / sheets・drive 600s)は data_poller と整合。

## 命名所見 / スコープ所見 / 可読性所見(refactor-ready)
- 特筆なし。data_poller(間隔別 poll)/ gas_client(GAS Web App proxy)/ mqtt_publisher の分割は明快。

## 後続リファクタ推奨(優先度順サマリ)
- **P0/P1/P2**: 構造スキャン範囲では特筆すべき負債なし。
- 既知の wiring gap(`hems/gas/sheets/*`・`hems/gas/drive/recent` を消費する rule が無い)は root CLAUDE.md の orphans に既記載で本 bridge の問題ではない。
