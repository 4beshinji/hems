# 監査: obsidian-bridge — 2026-05-25

## スコープ
- 対象 path(`services/obsidian-bridge/src/`):
  `main.py`・`config.py`・`vault_index.py`・`vault_watcher.py`・`note_writer.py`・`mqtt_publisher.py`
  — 計 ~842 LOC
- **監査深度**: canonical 契約(topic / route / tool / writeback / safety / env)を grep 検証 + 構造スキャン。
- 参照 canonical doc: `docs/CLAUDE-bridges.md` §Obsidian

## doc 乖離(本パスで修正適用済)

| # | doc claim | code reality | 修正先 doc | 状態 |
|---|---|---|---|---|
| 1 | Brain tools = `search_notes` / `write_note` / `get_recent_notes`(3) | unit 4 schema dump で 4: + `list_note_tags`(route `/api/notes/tags`) | CLAUDE-bridges.md §Obsidian | ✅ 4 件に補完 |

検証 OK(乖離なし):
- publish topic `hems/personal/notes/{changed,stats}` ✓。
- HTTP route `/api/notes/{search,recent,read,write,decision-log,learning-memo,tags}` ✓。
- writeback(decision-log / learning-memo)は brain(unit 1 `_write_decision_log`)が直接叩く内部経路と整合(§8 記載通り)。
- safety(`HEMS/` のみ書込・path traversal block・10000字 limit)は sanitizer(unit 1 `_validate_write_note`)で enforce 済。

## 命名所見 / スコープ所見 / 可読性所見(refactor-ready)
- 特筆なし。vault_index(TF-IDF)/ vault_watcher(watchdog)/ note_writer の責務分割は明快。

## 後続リファクタ推奨(優先度順サマリ)
- **P0/P1/P2**: 構造スキャン範囲では特筆すべき負債なし。クリーンな bridge。
