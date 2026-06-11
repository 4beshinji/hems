# 機能提案リスト — 2026-06-11

2026-06-11 監査([`audit/2026-06-11/SUMMARY.md`](audit/2026-06-11/SUMMARY.md))で判明した「既に流れているが活用されていないデータ」「構造的に安く実現できる拡張」を機能企画として整理する。リファクタリング計画([`refactor/2026-06-11/PLAN.md`](refactor/2026-06-11/PLAN.md))とは独立した読み物だが、各提案に前提 Wave を明記した。

優先度は「ユーザー価値 × 実装コスト × 既存データの有無」で付けた推奨値。

各提案の**難度とワーカモデル**は [`refactor/2026-06-11/PLAN.md`](refactor/2026-06-11/PLAN.md) §難度とワーカモデルの割当基準 と同一基準(低=Haiku 4.5 / 中=Sonnet 4.6 / 高=Opus 4.8 以上、レビューは常に実装ワーカより上位)。末尾のサマリ表に集約した。

---

## A. 既存データの未活用を機能化(最安・即効)

すでに MQTT で受信し world_model まで届いているのに consume する側がないデータ群(IMPLEMENTATION_MAP §4.4)。**新規センサー・新規ブリッジ不要**で機能になる。

### A1. ブリッジ稼働率ダッシュボード + 障害通知 ★★★

- **現状**: `*/bridge/status` は `bridge_connected` フラグ更新のみで履歴が残らない(CLAUDE.md 既知 gap)。ブリッジが夜間に死んでいても朝まで気づけない。
- **提案**: event_store に bridge status の遷移イベントを記録し、(1) frontend に稼働率カード(直近 24h/7d の uptime バー)、(2) 切断が N 分継続したら voice/ambient speaker で通知。
- **実装箇所**: brain `mqtt_router.py`(status 遷移の event 化)、backend `routers/bridge_status.py`(既に uptime/recent_events エンドポイントの骨格あり)、frontend カード 1 枚。
- **前提**: W3.3(status topic 統一 + 未発行 4 ブリッジへの発行追加)を先にやると計測対象が揃う。
- **工数感**: 1–2 日。

### A2. GAS Sheets / Drive の実用ルール ★★

- **現状**: `hems/gas/sheets/{name}` / `hems/gas/drive/recent` は `_update_gas_state` で world_model に入るが、消費するルール・automation がゼロ(unused)。
- **提案**: 用途を 1 つに絞って配線する。候補:
  - 家計簿 Sheet → 週次サマリを morning briefing に 1 行追加(「今週の支出は ¥xx」)
  - Drive recent → 「昨日追加されたドキュメント」を knowledge ingestion(`knowledge` profile)へ自動連携
- **実装箇所**: `event_automation.py` にアクション 1 本 + boot_load briefing テンプレート。
- **工数感**: 0.5–1 日/用途。

### A3. VLM model swap 履歴と「視覚系の健康診断」 ★

- **現状**: `hems/perception/vlm/model_swap` はフラグ管理のみ(partial)。heavy-swap が頻発しているかどうかを後から知る術がない。
- **提案**: swap イベントを event_store に記録し、swap 頻度・滞在時間を日次集計。GPU 負荷起因の rule-based fallback 頻度(brain 側 Guard 発動)と並べて「LLM/VLM がどれだけ間引かれているか」を dashboard で可視化。PowerModeManager のチューニング材料になる。
- **工数感**: 1 日。

### A4. ShoppingState の context 活用 ★★

- **現状**: R1.3 で reducer は追加されたが `context_builder` が context に含めない(live 化の片側のみ)。LLM は買い物リストを tool 呼び出しでしか見られない。
- **提案**: 未購入アイテム数と直近追加品目を Digital context に 1–2 行で注入。「牛乳が残っている状態で外出 event」→ ambient speaker が一言添える、まで配線すると生活機能になる。
- **実装箇所**: `world_model/context_builder.py` + event_automation 1 ルール。
- **工数感**: 0.5 日。

---

## B. リアルタイム性(アーキテクチャ拡張)

### B1. edge event の即時トリガ経路 ★★★

- **現状**: `hems/services/{name}/event` は受信しても次の 30s サイクル待ち(CLAUDE.md 既知 gap、wiring-gap-06 にも記載)。玄関センサー→照明のような「体感即時」が要る系が全部 30s 律速。
- **提案**: `_process_mqtt` に immediate-dispatch hook を設け、ホワイトリストされた event 種(人感・ドア開閉・wake word)だけ rule-based 経路を即時評価する。LLM は従来サイクルのまま(コスト不変)。
- **前提**: **W2.6(`_process_mqtt` 分割)とセットで実装するのが最も安い**。分割後の構造に hook 挿入点が自然に生まれる。
- **工数感**: W2.6 込みで +1–2 日。

### B2. frontend の polling → SSE/WebSocket 移行 ★★

- **現状**: dashboard は 40+ 並行ポーリング(voiceEvents は 3s × 3 箇所)。backend 負荷と表示遅延の両方に効いている。
- **提案**: backend に SSE エンドポイント(`/events/stream`)を 1 本立て、voice_events / task 更新 / bridge status をプッシュ化。TanStack Query は invalidation トリガとして使う。MQTT over WebSocket を直接購読する案より、認証を BACKEND_API_KEY 一本に保てる SSE が HEMS 構成では素直。
- **前提**: W5.2(queryKey 重複排除)を先にやると移行対象が 1 系統に集約されて楽。
- **工数感**: 2–3 日。

---

## C. 新データソース(data-bridge の再起動判断と連動)

### C1. Strava / Fitbit / Garmin intake(data-bridge 本実装) ★★

- **現状**: `services/data-bridge/` は src 空の scaffold。topics(`hems/personal/training/fitness` 等)は予約済み。biometric-bridge(Gadgetbridge 系)は心拍・睡眠・歩数のみで、ワークアウト単位のデータがない。
- **提案**: 運動習慣があるなら、W3.1 の共通ライブラリ完成後に「最初の `_common` ベース新規ブリッジ」として実装するのが一石二鳥(scaffold 検証を兼ねる)。training load を UserState に追加し、ScheduleLearner の疲労考慮・sunrise alarm の強度調整に流す。
- **判断**: **実装決定(2026-06-11)**。data-bridge は存続し、W3.1 完了後の最初の `_common` ベース新規ブリッジとして着手する。
- **工数感**: 2–3 日(共通ライブラリ後)。

### C2. 季節パターン提示(event_store 2 年データの回収) ★

- **現状**: 730d retention は「ML 季節パターン学習用」とコメントされているが、hourly_aggregates を読む分析機能が存在しない。データを貯めるコスト(SQLite 肥大リスク、W4.5)だけ払っている状態。
- **提案**: 月次で「昨年同月との比較」(室温・在宅時間・睡眠)を briefing に 1 段落追加。
- **判断の前提更新(2026-06-11)**: PostgreSQL 既定化(PLAN W4.5')が決定したため、retention 730d は維持され SQLite 肥大懸念は解消。本提案は「貯めたデータを回収する機能」として純粋に価値判断でき、W4.5' 完了後が着手適期。
- **工数感**: 1–2 日。

---

## D. 音声・キャラクター体験

### D1. 通知のダイジェスト化(alert digest) ★★

- **現状**: alert suppression(30min/10min)は「黙る」機構のみ。抑制された通知は消える。
- **提案**: 抑制中に溜まったイベントを次の発話機会(在宅検知・wake event)でまとめて 1 発話に要約。「留守中に 3 件: 宅配 1、CO2 高 2」。event_store に必要データは既にある。
- **実装箇所**: ambient_speaker + alert suppression の境界に digest queue を 1 つ。
- **工数感**: 1–2 日。

### D2. STT push-to-talk のモバイル統合 ★

- **現状**: STT(8023)は実装済みだが、mobile page(646 行)とは独立。外出先から声で task 追加する経路がない。
- **提案**: mobile page に PTT ボタン → STT → chat brain server の経路を 1 本通す。認証は既存の `verify_mobile_device` + W1.1 の internal token がそのまま使える。
- **前提**: W1.1(brain chat server 認証)。
- **工数感**: 1–2 日。

---

## E. 運用・配布

### E1. セットアップ doctor コマンド ★★

- **現状**: env.example とコードの乖離 ~30 変数(監査 §6)が示す通り、設定ミスは起動後に沈黙する系(ブリッジが silent failure)。distribution.md の wizard 計画とも重なる。
- **提案**: `make doctor` — compose config validation、.env 必須変数チェック、MQTT 接続、各ブリッジ /health、ollama モデル存在確認を一括実行して表にする。W4.3 の CI 突合スクリプトをローカル実行可能にしたものと考えると実装は共通化できる。
- **工数感**: 1 日(W4.3 と共用)。

### E2. ゲストモードの拡充 ★

- **現状**: `hems/brain/guest-mode` トピックは存在するが、認可がバイナリ(BACKEND_API_KEY の有無)なので「ゲストに見せてよい dashboard」が作れない。
- **提案**: read-only スコープの第 2 キー(`BACKEND_API_KEY_READONLY`)を verify_api_key に追加し、frontend に閲覧専用モード。来客時にタブレットを渡せる。配布(マルチテナント)への最初の一歩でもある。
- **前提**: W1 完了後。
- **工数感**: 1–2 日。

---

## 推奨着手順(コスト対効果順)

1. **A4 → A1 → D1**: 新規データ不要・各 0.5–2 日で生活体感が変わる
2. **B1**: W2.6 と同時実装(リファクタの「ついで」が最安)
3. **E1**: W4.3 と共用実装
4. **B2 / D2**: W5 / W1 完了後
5. **C1 / C2**: 意思決定(data-bridge 存続、retention 方針)とセットで判断

| ID | 提案 | 優先 | 工数 | 前提 Wave | 難度 | ワーカ |
|---|---|---|---|---|---|---|
| A1 | ブリッジ稼働率 + 障害通知 | ★★★ | 1–2d | W3.3 | 中(event_store 書込 + backend 集計 + frontend カードの 3 層を跨ぐが、各層とも既存パターンあり) | Sonnet 4.6 |
| B1 | edge event 即時トリガ | ★★★ | +1–2d | W2.6 同時 | 高(認知ループの実行モデルに手を入れる。30s サイクルとの二重発火・順序保証の設計が本体) | Opus 4.8(W2.6 と同一ワーカで連続実施) |
| A4 | ShoppingState context 活用 | ★★ | 0.5d | なし | 低(context_builder への追記 + event_automation ルール 1 本、既存パターン踏襲) | Haiku 4.5 |
| A2 | GAS Sheets/Drive 実用ルール | ★★ | 0.5–1d | なし | 低(event_automation の既存 action パターンに 1 本追加 + briefing テンプレ追記) | Haiku 4.5 |
| D1 | 通知ダイジェスト | ★★ | 1–2d | なし | 中(suppression との境界に digest queue を挟む小さな状態設計。発話タイミングの判断が絡む) | Sonnet 4.6 |
| B2 | SSE/WebSocket 化 | ★★ | 2–3d | W5.2 | 高(配信アーキテクチャの新設 — 認証・再接続・nginx buffering・Query invalidation の整合設計) | Opus 4.8(設計)→ Sonnet 4.6(実装) |
| E1 | make doctor | ★★ | 1d | W4.3 共用 | 中(個々のチェックは定型だが、診断メッセージの質が価値の本体。W4.3 と同一ワーカ推奨) | Sonnet 4.6 |
| C1 | Strava/Fitbit(data-bridge) | ★★ | 2–3d | W3.1(実装決定済 2026-06-11) | 中(`_common` ベースの新規ブリッジ 1 本 + OAuth フロー。W3.1 完成が前提) | Sonnet 4.6 |
| A3 | VLM swap 履歴可視化 | ★ | 1d | なし | 低(A1 確立後はその縮小コピー。A1 より先にやるなら中) | Haiku 4.5(A1 後) |
| C2 | 季節パターン briefing | ★ | 1–2d | W4.5'(PG 既定化)後推奨 | 中(hourly_aggregates のクエリ設計 + 欠損期間の扱い) | Sonnet 4.6 |
| D2 | モバイル PTT | ★ | 1–2d | W1.1 | 中(mobile page UI + STT + brain chat server の 3 サービス配線。各経路は実装済みで接続のみ) | Sonnet 4.6 |
| E2 | read-only キー(ゲスト) | ★ | 1–2d | W1 | 中(verify_api_key のスコープ拡張はコード量こそ小だが認可境界の変更。**レビューは Opus 4.8 必須**) | Sonnet 4.6 |
