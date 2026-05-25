# 監査: weather-bridge — 2026-05-25

## スコープ
- 対象 path(`services/weather-bridge/src/`): `main.py`・`config.py`・`weather_client.py`・`data_poller.py`・`mqtt_publisher.py` — 計 ~882 LOC
- **監査深度**: canonical 契約(topic / route / provider / tool / env)を grep 検証 + 構造スキャン。
- 参照 canonical doc: `docs/CLAUDE-bridges.md` §Weather

## doc 乖離(本パスで修正適用済)
- **なし。** canonical と完全一致。

検証 OK(乖離なし):
- publish topic `hems/weather/{current,forecast,alerts}` + `hems/weather/bridge/status` ✓(§4.3 / §5 WeatherState と一致)。
- HTTP route `/api/weather/{current,forecast,alerts,status}` ✓。
- provider(JMA default / OpenWeatherMap)・always-on(no profile)・`get_weather` tool・`_update_weather_state`(unit 2)consumer は doc 通り。

## 命名所見 / スコープ所見 / 可読性所見(refactor-ready)
- 特筆なし。weather_client(JMA/OWM 抽象)/ data_poller / mqtt_publisher の分割は明快。find-replace 事故・TODO 無し。

## 後続リファクタ推奨(優先度順サマリ)
- **P0/P1/P2**: なし。**最もクリーンなユニットの一つ**。
