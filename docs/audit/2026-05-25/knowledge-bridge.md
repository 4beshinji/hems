# 監査: knowledge-bridge — 2026-05-25

## スコープ
- 対象 path(`services/knowledge-bridge/src/`):
  `main.py`・`config.py`・`document_index.py`・`vector_store.py`・`embedding.py`・`source_watcher.py`・
  `mqtt_publisher.py`・`loaders/`(markdown / python_loader / json_loader / text / pdf / docx / csv_loader / html_loader / base)
  — 計 ~1,933 LOC(最大の bridge)
- **監査深度**: canonical 契約(topic / route / tool / loader 一覧 / env)を grep 検証 + 構造スキャン。
  hybrid search(RRF)/ embedding cache の行レベル精査は後続。
- 参照 canonical doc: `docs/CLAUDE-bridges.md` §Knowledge

## doc 乖離(本パスで修正適用済)

| # | doc claim | code reality | 修正先 doc | 状態 |
|---|---|---|---|---|
| 1 | Brain tools = `search_knowledge` / `get_knowledge_sources` / `read_knowledge_document`(3) | unit 4 schema dump で 4: + `get_recent_knowledge_changes`(route `/api/knowledge/recent`) | CLAUDE-bridges.md §Knowledge | ✅ 4 件に補完 |

検証 OK(乖離なし):
- publish topic `hems/personal/knowledge/{changed,stats}` ✓。
- HTTP route `/api/knowledge/{search,read,sources,recent,reindex}` ✓。
- loaders: markdown/.py/.json/.txt系/.pdf/.docx/.csv/.html = doc の plugin loader 列挙と一致(9 loader)。
- 3-way RRF(BM25 + vector + title boost)構成は `document_index.py`/`vector_store.py`/`embedding.py` の分割と整合。

## 命名所見 / スコープ所見 / 可読性所見(refactor-ready)

| 優先度 | 問題 | file | 推奨 |
|---|---|---|---|
| P2 | hybrid search(RRF 融合)・embedding cache・graceful degradation は doc 記載通りだが行レベル未精査 | document_index.py / vector_store.py | 後続パスで RRF 重み・cache invalidation を精読 |

## 後続リファクタ推奨(優先度順サマリ)
- **P2**: RRF / embedding cache の行レベル精読(本パス未到達)。
- **P0/P1**: 構造スキャン範囲では検出なし。loader plugin + hybrid search の分割は明快。read-only(mount レベル enforce)も doc 通り。
