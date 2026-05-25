# 監査: news-bridge — 2026-05-25

## スコープ
- 対象 path(`services/news-bridge/src/`): `main.py`・`config.py`・`news_fetcher.py`・`news_summarizer.py`・`urgency.py`・`mqtt_publisher.py` — 計 ~619 LOC
- **監査深度**: canonical 契約(topic / route / tool / env)を grep 検証 + 構造スキャン。
- 参照 canonical doc: `docs/CLAUDE-bridges.md` §News

## doc 乖離(本パスで修正適用済)
- **なし。** canonical と完全一致。

検証 OK(乖離なし):
- publish topic `hems/news/{daily,urgent}` + `hems/news/bridge/status` ✓(§4.3 / §5 NewsState と一致)。
- HTTP route `/api/news/latest`・`/api/news/refresh` ✓(BootLoad〔unit 1〕/ EventAutomation〔unit 3〕が叩く経路と一致)。
- `get_news_summary` tool・urgent news speak rule・daily summary(default 07:30)は doc 通り。
- urgency score 0.8+ → MQTT alert は `urgency.py` と整合。

## 命名所見 / スコープ所見 / 可読性所見(refactor-ready)
- 特筆なし。news_fetcher(RSS)/ news_summarizer(Ollama)/ urgency(scoring)/ mqtt_publisher の分割は明快。find-replace 事故・TODO 無し。

## 後続リファクタ推奨(優先度順サマリ)
- **P0/P1/P2**: なし。クリーンな bridge。
- 既知の wiring gap(`hems/services/{name}/event` の即時トリガ無し等)は news-bridge とは無関係。
