# 監査: biometric-bridge — 2026-05-25

## スコープ
- 対象 path(`services/biometric-bridge/src/`):
  `main.py`・`config.py`・`mqtt_publisher.py`・`send_queue.py`・`data_processor.py`・
  `providers/`(base / gadgetbridge / huami / zepp)— 計 ~1,305 LOC
- **監査深度**: canonical 契約(MQTT topic / HTTP route / brain tool / env)を grep 検証 + 構造スキャン。
  data_processor の fatigue 計算等の行レベル精査は後続。
- 参照 canonical doc: `docs/CLAUDE-bridges.md` §Biometric

## doc 乖離(本パスで修正適用済)

| # | doc claim | code reality | 修正先 doc | 状態 |
|---|---|---|---|---|
| 1 | Brain tools = `get_biometrics` / `get_sleep_summary`(2) | unit 4 schema dump で 4: + `get_biometric_trend` / `get_sleep_history` | CLAUDE-bridges.md §Biometric | ✅ 4 件に補完 |

検証 OK(乖離なし):
- publish topic `hems/personal/biometrics/*` ✓。HTTP route `/api/biometric/{webhook,latest,sleep,activity}` ✓。
- providers(gadgetbridge / huami / zepp)は doc「Gadgetbridge app」+「Huami cloud API」と整合(zepp は未文書だが Huami 系列)。
- `/api/biometric/activity` は brain tool 未公開(§8 記載通り、get_activity_history は perception 側の別物)。

## 命名所見(refactor-ready)
- 特筆なし。

## スコープ所見 / 可読性所見(refactor-ready)

| 優先度 | 問題 | file | 推奨 |
|---|---|---|---|
| P2 | provider に `zepp` があるが canonical(Gadgetbridge/Huami)に未記載 | providers/zepp.py | doc に zepp provider を追記 or provider 一覧を明示 |
| P2 | data_processor の fatigue 計算(HR30/sleep40/stress30%)は doc 記載と一致するが行レベル未精査 | src/data_processor.py | 後続パスで重み付けロジック精読 |

## 後続リファクタ推奨(優先度順サマリ)
- **P2**: zepp provider の doc 化、data_processor の精読。
- **P0/P1**: 構造スキャン範囲では検出なし。webhook→正規化→MQTT の plugin provider 構成は明快。
