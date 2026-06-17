# 推奨フォローアップ作業 — 2026-06-11 リファクタリング後

> **COMPLETED** — 本リストの全項目は [`LEDGER.md`](LEDGER.md) において commit 付きで `done` として記録されています。新規タスクは `../../feature-proposals-2026-06-11.md` を参照してください。

作成経緯: 2026-06-17 に Agent Swarm による実装レビューと full pytest テスト妥当性検証を実施。
受け入れ条件を満たす重大な問題は実装済みだが、品質向上・技術的負債低減・一貫性強化の観点から対応を推奨する残作業を整理する。

検証済みゲート（修正後）:

```bash
make lint
# ruff check . / ruff format --check . ともに pass

PYTHONPATH=services/brain/src:services/backend timeout 1800s .venv/bin/python -m pytest \
  tests/ services/brain/tests/ -v --tb=short -m "not integration and not e2e and not benchmark"
# 2178 passed, 8 skipped, 47 deselected, 0 failed
```

本ドキュメントは以下の観点で整理する:

- **高**: セキュリティ上の防御深さや経路間の一貫性に関わるもの。次の Wave 着手前に対応すべき。
- **中**: 保守性・テスト網羅性・運用安定性に関わるもの。計画的に対応。
- **低**: コメント・軽微なリファクタ・追加テスト。隙間時間で対応。

---

## 高優先度

### H1. LLM / chat / REST 経路の device_id 検証を統一

- **対象ファイル**:
  - `services/brain/src/brain_chat_server.py` L70–L73 (`_handle_device_control`)
  - `services/brain/src/sanitizer.py` L397–L398 (`_validate_control_actuator`)
- **関連 Wave**: W1.4 / W1.8
- **問題**:
  - REST 経路 (`/devices/{id}/control`) と backend パスパラメータでは `is_valid_device_ref()` による書式検証が行われている。
  - 一方、brain chat server 経由と sanitizer (LLM 経路) では空文字チェックまたは `"."` の有無のみで、悪性 ID が dispatch 到達後に拒否されるだけ。
  - defence-in-depth と経路間の検証強度の一貫性が損なわれている。
- **修正案**:
  - `brain_chat_server.py` の `_handle_device_control` で `device_id` の空文字チェック後に `is_valid_device_ref(device_id)` を呼び、不正なら 400 を返す。
  - `sanitizer.py` の `_validate_control_actuator` の `device_id` チェックを `is_valid_device_ref()` に置き換える。
- **受け入れ条件**:
  - `tests/test_device_control_validation.py` / `tests/test_device_id_validation.py` に LLM/chat 経路での不正 device_id 拒否ケースを追加し pass すること。
  - `make lint` / full pytest グリーン維持。

---

## 中優先度

### M1. backend → ha-bridge 呼び出しの Authorization ヘッダー付与をテスト

- **対象ファイル**: `tests/test_backend_home_router.py`
- **関連 Wave**: W3.9
- **問題**:
  - `services/backend/routers/home.py` の `_ha_proxy_call` / `get_home_devices` では `_internal_headers()` 経由で `Authorization: Bearer <HEMS_INTERNAL_TOKEN>` を付与している。
  - しかし、既存テストは `_ha_proxy_call` を AsyncMock で置き換えており、実際に送信される headers の中身を検証していない。
  - W3.9 設計ノート §5.2 の受け入れ条件に対するテスト漏れ。
- **修正案**:
  - httpx.AsyncClient の `post` / `get` を patch し、呼び出し引数の `headers` に `Authorization: Bearer secret` が含まれることを assert するテストを追加する。
  - 既存の `test_light_toggle` と統合するか、独立したテストケースとして追加する。
- **受け入れ条件**:
  - token 未設定時は `Authorization` ヘッダーがないこと、token 設定時は正しい Bearer token が付与されることを検証。

### M2. 内部 HTTP caller 用 Bearer ヘルパーの集約

- **対象ファイル**:
  - `services/backend/routers/{chat,devices,scenes,automations,home}.py`
  - `services/brain/src/{tool_http.py,dashboard_transport.py,boot_load_manager.py,task_reminder.py,voice_capsule/builder.py}`
- **関連 Wave**: W1.1 / W3.9
- **問題**:
  - `HEMS_INTERNAL_TOKEN` 付与ロジックが backend 5 箇所 + brain 複数箇所に分散している。
  - W3.1 で `_common` を新設した意義に反し、重複・改修漏れ・テスト分散のリスクがある。
- **修正案**:
  - backend 側: `hems_common.auth` または backend 内の単一ヘルパーに `_internal_auth_headers()` を集約。
  - brain 側: `brain_constants.brain_auth_headers()` を標準化し、各 tool/http 呼び出しで使用する。
  - 両側で同一の `Bearer <token>` 形式を保証する unit test を追加。
- **受け入れ条件**:
  - 既存の認証テストが pass し、新規集約ヘルパーの単体テストが追加されること。

### M3. frontend API クライアントの二重実装と VITE_BACKEND_URL 対応漏れ

- **対象ファイル**:
  - `services/frontend/src/lib/api-client.ts` L12
  - `services/frontend/src/lib/api.ts`
- **関連 Wave**: W5.1 / W5.5
- **問題**:
  - W5.1 で新設された `api-client.ts` と既存の `api.ts` 内 `get/post/put/del` が混在。
  - `api-client.ts` は `/api` 固定で、`VITE_BACKEND_URL` を無視する。
  - W5.5 の「`VITE_API_BASE` / `VITE_BACKEND_URL` を `VITE_BACKEND_URL` に統一」の趣旨に反する。
- **修正案**:
  - `api-client.ts` の base URL を `(import.meta.env.VITE_BACKEND_URL as string | undefined) ?? '/api'` に変更。
  - 中長期的に `api.ts` の汎用関数を `api-client.ts` に統合し、各コンポーネントの import 先を `src/lib/api/{domain}.ts` に移行する計画を立てる。
- **受け入れ条件**:
  - `pnpm test` pass、`pnpm build` pass、`pnpm lint` のエラー増加なし。
  - `VITE_BACKEND_URL` 変更時にリクエスト先が変わることを確認するテストを追加。

### M4. staleTime = refetchInterval の挙動影響確認

- **対象ファイル**:
  - `services/frontend/src/hooks/queries/use-voice-events.ts` L21
  - `services/frontend/src/hooks/queries/use-tasks.ts` L21
  - `services/frontend/src/hooks/queries/use-zones.ts` L21
- **関連 Wave**: W5.2
- **問題**:
  - `staleTime = refetchInterval` を設定すると、TanStack Query は初回 fetch 後しばらく再 fetch を抑制するため、実質ポーリング間隔が最大 2 倍に伸びる可能性がある。
  - コミットメッセージは「interval は不変」としているが、実際には挙動変更を含む。
- **修正案**:
  - 実際のダッシュボードでポーリング間隔が意図通りか確認。
  - もし間隔が伸びる場合、`staleTime` を `refetchInterval` 未満（例: 半分）に調整する。
- **受け入れ条件**:
  - ブラウザ DevTools Network タブでポーリング間隔が設計値通りであることを確認。

### M5. W2.2 脱結合の軽微なクリーンアップ

- **対象ファイル**:
  - `services/brain/src/rules/gas.py` L14–L18: 不要な `try/except Exception` を削除
  - `services/brain/src/world_model/context_builder.py` L103, L138: `time.time()` を `now` 引数に置き換え
  - `services/brain/src/world_model/digital_updates.py` L345: ファイル先頭の import に `datetime` を統合
  - `services/brain/src/world_model/vip_detector.py` L40–L41: env 読み込みタイミングの混在をコメントで明記
- **関連 Wave**: W2.2 / W2.3
- **受け入れ条件**:
  - `make lint` / full pytest グリーン維持。

---

## 低優先度

### L1. コメント・ドキュメントの陳腐化修正

- **対象ファイル**:
  - `services/backend/hmac_util.py` L17–L20: 署名メッセージ形式の説明を実装 (`f"{timestamp}:{nonce}:".encode() + body`) に合わせる
  - `tests/security/test_device_id_injection.py` L87–L104, L127–L137, L298–L309: 「W1.7-B1 既知バグ」コメントを削除。現在は連続ドットが拒否されることを明示。
  - `tests/security/test_mqtt_acl.py` L13: コメントの `aclfile` 参照を `acl.txt` に修正。
- **受け入れ条件**:
  - `make lint` pass、誤解を招くコメントがなくなる。

### L2. brain chat server の health path trailing slash 対応

- **対象ファイル**: `services/brain/src/brain_chat_server.py` L25
- **問題**:
  - `brain_auth_middleware` は `request.path not in _HEALTH_PATHS` で判定。`/health/` は一致せず認証が要求される。
  - 一部 HTTP クライアントやリバースプロキシが末尾スラッシュを付ける場合、healthcheck が 401 になる可能性がある。
- **修正案**:
  - `_HEALTH_PATHS = {"/health", "/health/"}` に拡張、または比較を `request.path.rstrip("/") == "/health"` に変更。
- **受け入れ条件**:
  - `tests/test_brain_chat_auth.py` に `/health/` でも 200/401 例外が機能するテストを追加。

### L3. 移行スクリプトの恒真 assertion 修正

- **対象ファイル**: `tests/test_migrate_sqlite_to_pg.py` L239
- **問題**: `assert result is not None or result is None` は常に真。
- **修正案**: `assert result == "not-a-date"` など、入力値がそのまま返ることを検証する。

### L4. init_env.py のユニットテスト追加

- **対象ファイル**: 新規 `tests/test_init_env.py`
- **問題**: W4.6 の核となる `.env` 生成ロジックのユニットテストが存在しない。
- **修正案**:
  - プレースホルダ判定、既存値の保持、`--force` 上書き、`--dry-run` 時の非破壊、存在しない key の末尾追加をカバーするテストを追加。
- **受け入れ条件**:
  - full pytest に追加され pass すること。

### L5. bridge_lifespan の startup 失敗時の disconnect 保証

- **対象ファイル**: `services/_common/hems_common/lifespan.py` L43–L45
- **問題**:
  - `on_startup()` が例外を投げると `async with` の `__aenter__` が失敗し `__aexit__` が走らないため、MQTT 接続が開放されない。
  - プロセス終了で実害は少ないが、堅牢性を高める余地がある。
- **修正案**:
  - `on_startup()` を try/except で囲み、失敗時も `mqtt.disconnect()` を呼ぶ。
- **受け入れ条件**:
  - `tests/test_common_lifespan_status.py` に startup 失敗時の disconnect テストを追加し pass。

### L6. MqttPublisher.subscribe / set_message_callback の単体テスト追加

- **対象ファイル**: `tests/test_common_mqtt.py`
- **問題**:
  - `MqttPublisher` の subscribe 系テストがなく、perception 経由の間接カバレッジに依存。
  - `_common` 単体での契約保護が弱い。
- **修正案**:
  - `subscribe` / `set_message_callback` の呼び出しで、内部 `mqtt_client` の対応メソッドが正しい引数で呼ばれることを mock 検証するテストを追加。

---

## 推奨対応順序

```
H1 → M1 → M2 → M3 → M4 → M5 → L1–L6（並列可）
```

H1 はセキュリティ経路の一貫性に直結するため最優先。M1–M4 は次期開発着手前までに対応すると、回帰リスクを大幅に下げられる。L1–L6 は小粒なため、他作業の合間に対応可能。

---

## 備考

- 本フォローアップは 2026-06-11 PLAN.md の「全 row 完了」後の品質向上位置づけであり、新規 Wave 計画に組み込んでもよい。
- 1 row = 1 commit の規律を踏襲し、各作業を独立した commit で管理することを推奨。
- 各作業完了時は `docs/refactor/2026-06-11/LEDGER.md` に追記し、ゲート結果を更新すること。
