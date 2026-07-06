# Follow-up 計画: 2026-06-11 メタレビュー後の残タスク

> 本計画は [`META_REVIEW_REPORT.md`](META_REVIEW_REPORT.md) の所見を実行可能なタスクに分解したもの。
> 次セッションでは本計画に従い、優先順位に沿って 1 タスクずつ実装・検証・commit する。

## 1. 背景と目的

2026-05-25 / 2026-06-11 の監査・リファクタリングは実装面ではほぼ完了している。
しかし以下の残課題が残っている:

1. **未実装リファクタ**: W3.8b / W3.8c / W4.5'
2. **品質警告**: aiosqlite イベントループ警告、HAParser `_ha_rainbow` 未 await 警告、frontend MSW 未ハンドル警告
3. **テストカバレッジギャップ**: tool handlers 群、`device_registry.py`、`mcp_bridge.py`、frontend 主要コンポーネント
4. **ドキュメント追従**: `IMPLEMENTATION_MAP.md` / `CLAUDE.md` / `README.md` の残存不整合

本計画の目的は、これらを次セッションで即座に着手できる粒度に落とし込み、
受け入れ条件・検証方法・リスクを明確にすること。

## 2. ゴール

- 未実装リファクタ W3.8b / W3.8c / W4.5' を完了させる。
- 品質警告を解消し、`make test-quick` / `pnpm test` が警告ゼロで完走する。
- 最低限の回帰テストを追加し、主要ツール実行経路・デバイスレジストリ・MCP bridge のカバレッジを向上させる。
- ドキュメントを実態に追従させる。

## 3. スコープ

### In-scope

- `edge/` ファームの MQTT topic 変更(W3.8b)
- `office/*` 互換 window の削除条件整備(W3.8c)
- PostgreSQL 既定 DB 切替(W4.5')
- テスト品質警告の解消
- 最低限の追加テスト
- ドキュメント更新

### Out-of-scope

- 大規模な frontend UI テスト追加(別計画)
- ブリッジ HTTP への `HEMS_INTERNAL_TOKEN` 横展開(S3 deferred — 影響小)
- TLS/HSTS(配布 Phase と同期)
- 新機能開発(data-bridge C1 等)

## 4. タスク一覧(優先順位順)

| # | タスク | 優先度 | 工数見積 | 依存 |
|---|---|---|---|---|
| T1 | 品質警告解消: frontend MSW `/api/brain/power-mode` handler 追加 | P0 | 15 min | なし |
| T2 | 品質警告解消: `HAParser._ha_rainbow` 未 await 警告解消 | P0 | 1–2h | なし |
| T3 | 品質警告解消: `test_backend_timeseries_router.py` aiosqlite イベントループ警告 | P0 | 1–2h | なし |
| T4 | W3.8b: `edge/` ファーム topic prefix を `hems/sensors/*` へ変更 + mosquitto ACL 追加 | P1 | 2–3h | T1–T3 完了後 |
| T5 | W4.5': PostgreSQL 既定 DB 切替設計・実装 | P1 | 3–5h | design note 承認後 |
| T6 | ドキュメント追従: `IMPLEMENTATION_MAP.md` / `CLAUDE.md` / `README.md` 残存不整合 | P1 | 2–3h | T4, T5 と並行可 |
| T7 | W3.8c: `office/*` 互換 window 削除(条件達成後) | P2 | 1h | T4 完了 + 旧 topic 受信 7 日間ゼロ |
| T8 | テスト追加: tool handlers / `device_registry.py` / `mcp_bridge.py` 最小 smoke test | P2 | 4–6h | T2, T3 完了後 |

## 5. タスク詳細

### T1 — frontend MSW `/api/brain/power-mode` handler 追加

**問題**: `services/frontend/src/contexts/__tests__/contexts.test.tsx` の `PowerContext` テストで
`GET /api/brain/power-mode` への fetch が MSW 未ハンドル警告を出している。

**対象**:
- `services/frontend/src/test/handlers.ts`
- `services/frontend/src/lib/types.ts` (PowerModeResponse 型があれば)

**実装**:
```ts
http.get('/api/brain/power-mode', () =>
  HttpResponse.json({ mode: 'normal' })
),
```

**受け入れ条件**:
- `cd services/frontend && pnpm test` が警告ゼロで pass すること。

**検証**:
```bash
cd services/frontend
pnpm test
```

---

### T2 — `HAParser._ha_rainbow` 未 await 警告解消

**問題**: `tests/test_device_dispatcher_characterization.py::TestHaRainbow::test_rainbow_returns_immediately_without_waiting`
で `RuntimeWarning: coroutine 'HAParser._ha_rainbow' was never awaited` が発生。

**原因**:
- `services/brain/src/devices/vendors/ha.py:103` で `ctx.asyncio.ensure_future(self._ha_rainbow(...))` として
  coroutine を fire-and-forget している。
- テストで `device_dispatcher.asyncio.ensure_future` を patch しているため、coroutine は生成されるが
  スケジュールされず、pytest-asyncio が GC 時に未 await 警告を出す。

**対象**:
- `services/brain/src/devices/vendors/ha.py`
- `tests/test_device_dispatcher_characterization.py`

**推奨実装(2 案)**:

案 A — 実装側で Task を追跡する(推奨):
```python
self._rainbow_tasks: set[asyncio.Task] = set()

# rainbow action 分岐
if action == "rainbow":
    ...
    task = ctx.asyncio.create_task(self._ha_rainbow(ctx, entity_id, duration))
    self._rainbow_tasks.add(task)
    task.add_done_callback(self._rainbow_tasks.discard)
    return {"success": True, ...}
```

案 B — テスト側で coroutine をキャンセルする:
```python
with patch("device_dispatcher.asyncio.ensure_future") as mock_ef:
    coro = MagicMock()
    mock_ef.side_effect = lambda c: coro  # coroutine を消費
    result = await disp._dispatch_ha(device, "rainbow", {"duration_s": 5})
```

**受け入れ条件**:
- `make test-quick` 実行時に `HAParser._ha_rainbow` の未 await 警告が出なくなること。
- 既存の `test_rainbow_returns_immediately_without_waiting` / `test_rainbow_duration_too_large_rejected` /
  `test_ha_rainbow_hue_step_count` / `test_ha_rainbow_last_call_is_warm_white` が pass すること。

**検証**:
```bash
source .venv/bin/activate
python -m pytest tests/test_device_dispatcher_characterization.py::TestHaRainbow -v
```

---

### T3 — `test_backend_timeseries_router.py` aiosqlite イベントループ警告解消

**問題**: `PytestUnhandledThreadExceptionWarning: RuntimeError: Event loop is closed`
(aiosqlite/core.py: _connection_worker_thread)

**原因**:
- fixture 内で新規イベントループを作成しテーブル作成後 `loop.close()` している。
- その後返却された `TestClient(app)` が別のイベントループを使用し、aiosqlite 接続スレッドが
  閉じられたループにアクセスしている。

**対象**:
- `tests/test_backend_timeseries_router.py`

**推奨実装**:
```python
@pytest.fixture
def client(tmp_path, monkeypatch):
    ...
    import asyncio

    async def _create():
        async with database.engine.begin() as conn:
            await conn.run_sync(database.Base.metadata.create_all)

    # 同じループでテーブル作成 → TestClient もそのループを継承
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        # TestClient の lifespan で作られるループを使う
        loop = asyncio.get_event_loop()
        loop.run_until_complete(_create())
        yield test_client
        # cleanup: engine dispose で aiosqlite スレッドを終了
        loop.run_until_complete(database.engine.dispose())
```

または、pytest-asyncio を使って async fixture にする方がクリーン。

**受け入れ条件**:
- `make test-quick` 実行時に aiosqlite イベントループ警告が出なくなること。
- `tests/test_backend_timeseries_router.py` 全 test が pass すること。

**検証**:
```bash
source .venv/bin/activate
python -m pytest tests/test_backend_timeseries_router.py -v
```

---

### T4 — W3.8b: `edge/` ファーム topic prefix 変更 + mosquitto ACL 追加

**現状**:
- `edge/lib/soms_mcp.py:48-52`: `topic_prefix` default が `office/{zone}/sensor/{device_id}`
- `edge/lib/swarm/hub.py:137`: topic 組み立てが `office/%s/sensor/%s/%s` のまま
- `edge/test-edge/camera-node/simulator.py`: `office/` ハードコード要確認
- `edge/office/sensor-node/main.py`, `edge/office/unified-node/main.py`, `edge/office/sensor-02/main.py`: 直接 topic を組み立てている可能性あり
- `infra/mosquitto/acl.txt:54`: `hems-perception` user に `topic write office/#` のみ
- `infra/mosquitto/aclfile`: 要確認

**変更内容**:
1. `edge/lib/soms_mcp.py`: default `topic_prefix` を `hems/sensors/{zone}/sensor/{device_id}` に変更。
   - config.json で `topic_prefix` を上書きしている既存デバイスは影響を受けない。
2. `edge/lib/swarm/hub.py:137`: topic 組み立てを `hems/sensors/%s/sensor/%s/%s` に変更。
3. `edge/test-edge/camera-node/simulator.py`: `office/` → `hems/sensors/` に変更。
4. `edge/office/*/main.py`: 直接 topic 組み立て箇所があれば `hems/sensors/` に変更。
5. `infra/mosquitto/acl.txt` / `aclfile`:
   - `hems-perception` user に `topic write hems/sensors/#` を追加。
   - `office/#` は W3.8c 完了まで維持(互換 window)。
6. `docs/IMPLEMENTATION_MAP.md` §4 / `CLAUDE.md` MQTT 規約に W3.8b 完了注記を追加。

**受け入れ条件**:
- `grep -R "office/" edge/lib edge/test-edge edge/office edge/swarm` で変更対象外のハードコード topic が残っていないこと。
- `make lint` clean。
- `make test-quick` pass。
- (実機): edge ファームを flash 後、`hems/sensors/{zone}/sensor/{device_id}/{channel}` からデータが届くこと。

**検証**:
```bash
grep -R "office/" edge/lib edge/test-edge edge/office edge/swarm | grep -v ".pyc"
make lint
make test-quick
```

**注意**: 実機 flash と疎通確認はユーザ作業。コード変更だけでは W3.8b は完了しない。

---

### T5 — W4.5': PostgreSQL 既定化の設計準備 + 移行スクリプト検証 + docs 整備

**現状**:
- [`W4.5-design-note.md`](W4.5-design-note.md) で詳細設計は完了。
- ユーザー決定(2026-06-12): **PG 既定化本体(DATABASE_URL デフォルト切替 + compose コア昇格)は distribution Phase 1 後に延期**。
- **移行スクリプトは完成**(`infra/scripts/migrate_sqlite_to_pg.py`)。
- 現時点で着手可能なのは、移行スクリプトの検証と docs 整備のみ。

**現時点で実施すること**:

1. **移行スクリプトの検証**:
   - dry-run モードがエラーなく動作するか確認。
   - backend/brain 用 SQLite ファイルの自動探索 or 引数指定が正しいか確認。
   - テスト用の一時 SQLite → 一時 SQLite(論理検証)で動作確認(または CI 用の PG service container を使った integration test)。

2. **docs 整備**:
   - `docs/IMPLEMENTATION_MAP.md` §9: W4.5' 移行スクリプトの存在と、既定切替が distribution Phase 1 後に延期されていることを明記。
   - `CLAUDE.md` Database セクション: 現状「SQLite default」と書かれている箇所に「PG 既定化は distribution Phase 1 後、移行スクリプトは利用可能」の注記を追加。
   - `README.md`: Quick Start に「現状は SQLite default。PG 移行は任意」という現状を維持しつつ、移行スクリプトへのリンクを追加。
   - `docs/distribution.md`: Phase 1 の `POSTGRES_PASSWORD` 乱数化リストに `POSTGRES_PASSWORD` を追加(まだ未追加なら)。

3. **(将来予約) PG 既定切替**:
   - distribution Phase 1(quickstart で `POSTGRES_PASSWORD` 乱数化)完了後に、以下を実施:
     - `infra/docker-compose.yml`: postgres から `profiles: ["postgres"]` を削除、backend/brain の `depends_on` に postgres 追加、`DATABASE_URL` 既定を PG に変更。
     - `env.example`: `DATABASE_URL` default を PG に変更、SQLite はコメントで案内。
     - `services/backend/database.py`: default を PG に変更、pool 設定追加。
     - 関連 docs 更新。
   - 詳細は [`W4.5-design-note.md`](W4.5-design-note.md) §1–§7 参照。

**変更対象ファイル(現時点)**:
- `infra/scripts/migrate_sqlite_to_pg.py` (検証、必要に応じて微修正)
- `docs/IMPLEMENTATION_MAP.md` §9
- `CLAUDE.md` Database セクション
- `README.md` Quick Start / DB セクション
- `docs/distribution.md` Phase 1

**受け入れ条件**:
- `infra/scripts/migrate_sqlite_to_pg.py --dry-run` がエラーなく動作すること。
- `make lint` clean。
- `make test-quick` pass。
- docs が現状(「SQLite default / PG 移行スクリプトあり / 既定切替は Phase 1 後」)と矛盾しないこと。

**検証**:
```bash
source .venv/bin/activate
PYTHONPATH=services/brain/src:services/backend python infra/scripts/migrate_sqlite_to_pg.py --help
PYTHONPATH=services/brain/src:services/backend python infra/scripts/migrate_sqlite_to_pg.py --dry-run --source ./data/hems.db --target sqlite+aiosqlite:///tmp/dummy.db
make lint
make test-quick
```

---

### T6 — ドキュメント追従

**対象と内容**:

| ドキュメント | 更新内容 |
|---|---|
| `docs/IMPLEMENTATION_MAP.md` | §2.1 Verification コマンドを `devices/` パッケージ対応に。§4.0 トピックツリーに `hems/sensors/*` canonical を明記。§9 W4.5' 完了を反映。 |
| `services/brain/CLAUDE.md` | `DeviceDispatcher` 関連記述を `devices/` パッケージ対応に完全移行。`dashboard_client` split について言及。 |
| `services/backend/CLAUDE.md` | W1.4 実装後の REST 経路 params 検証状態を更新(もし T4/T5 で実装に追随する場合)。 |
| `README.md` | Optional Profiles 表に `mock`/`tapo`/`zigbee`/`stt` が含まれていることを確認。Brain ツール数 58 を維持。 |
| `docs/audit/2026-06-11/SUMMARY.md` | W3.8b / W4.5' 着手後に「進行中」注記を追加。 |
| `docs/refactor/2026-06-11/PLAN.md` / `LEDGER.md` | T4–T8 完了後に status / commit を更新。 |

**受け入れ条件**:
- 各ドキュメントが実コードと矛盾していないこと。
- `make lint` clean。

---

### T7 — W3.8c: `office/*` 互換 window 削除

**着手条件**:
- T4 完了後、全 edge デバイスの実機 flash 完了。
- 旧 topic `office/#` への受信が 7 日間ゼロ。

**変更内容**:
1. `services/brain/src/world_model/mqtt_router.py`: `office/#` subscribe を削除。
2. `infra/mosquitto/acl.txt` / `aclfile`: `office/#` 関連 ACL を削除。
3. `docs/IMPLEMENTATION_MAP.md` §4 / `CLAUDE.md` / `docs/CLAUDE-bridges.md`: `office/*` 互換記述を削除。
4. `edge/` 内の `topic_prefix` override ドキュメントを更新。

**受け入れ条件**:
- `grep -R "office/" services/brain/src/world_model infra/mosquitto docs/` で意図しない残存がないこと。
- `make test-quick` pass。

---

### T8 — テスト追加: tool handlers / device_registry / mcp_bridge

**対象**:
- `services/brain/src/tool_handlers_*.py`
- `services/brain/src/device_registry.py`
- `services/brain/src/mcp_bridge.py`

**方針**:
- tool handlers: 各 handler の「成功パス」と「外部 bridge 404 エラーパス」を最低 1 ケースずつ追加。
- `device_registry.py`: `update_from_heartbeat` / `get_device` / TTL 切れの smoke test。
- `mcp_bridge.py`: MCP 接続・切断・メッセージ受信の smoke test(可能な範囲)。

**受け入れ条件**:
- 新規テストが `make test-quick` に含まれ pass すること。
- カバレッジが対象モジュールで 10% 以上向上すること。

**検証**:
```bash
source .venv/bin/activate
python -m pytest tests/test_tool_handlers_*.py tests/test_device_registry.py tests/test_mcp_bridge.py -v
```

## 6. 実行順序と依存関係

```
T1, T2, T3  ─┬─> T4 ──> T7
             │
             ├─> T5 ──> T6
             │
             └─> T8
```

- T1–T3 は独立して並行可。
- T4 は T1–T3 完了後(品質警告を先に解消しておく)。
- T5 は T1–T3 完了後。T4 と並行可。
- T6 は T4/T5 と並行可。
- T7 は T4 完了 + 実機移行 + 7 日間ゼロ待ち。
- T8 は T2/T3 完了後(テスト基盤を安定させてから)。

## 7. 検証ゲート(全タスク共通)

各タスク完了時に以下を実行:

```bash
source .venv/bin/activate
make lint
cd services/frontend && pnpm test
source .venv/bin/activate && make test-quick
```

baseline: lint clean / Python 2108 passed / frontend 48 passed。

## 8. リスク

| リスク | 影響 | 対策 |
|---|---|---|
| W4.5' (将来)既存 SQLite ユーザーが migrate 手順を踏まずにデータ消失 | 高 | 移行スクリプトを充実させ、README に明記。default 切替時に大きな CHANGELOG エントリを残す。現時点ではスクリプト検証を徹底。 |
| W3.8b の edge ファーム変更で実機 flash 漏れ | 中 | 変更箇所を grep リスト化。flash 完了チェックリストを作成。 |
| W3.8c の旧 topic 削除で未移行デバイスが黙って停止 | 中 | 7 日間ゼロ条件を厳守。mosquitto log で確認。 |
| `_ha_rainbow` 修正で fire-and-forget 動作が変わる | 低 | 既存 4 つの rainbow test をすべて pass させる。 |
| `test_backend_timeseries_router.py` 修正で他テストに影響 | 低 | 影響範囲を絞った fixture 変更にする。 |

## 9. 次セッション用 /goal プロンプト

```text
/goal Execute docs/refactor/2026-06-11/FOLLOW_UP_PLAN.md. Start with T1 (frontend MSW power-mode handler) and T2/T3 (quality warnings), then proceed to T4 (W3.8b edge topic migration) and T5 (W4.5' PostgreSQL migration script verification + docs update). Update PLAN.md / LEDGER.md / IMPLEMENTATION_MAP.md / CLAUDE.md as each task completes. Run make lint, make test-quick, and pnpm test after every task. Stop and report immediately if any test regresses.
```

## 10. 実行進捗

| # | タスク | 状態 |
|---|---|---|
| T1 | frontend MSW `/api/brain/power-mode` handler 追加 | ✅ done |
| T2 | `HAParser._ha_rainbow` 未 await 警告解消 | ✅ done |
| T3 | `test_backend_timeseries_router.py` aiosqlite イベントループ警告解消 | ✅ done |
| T4 | W3.8b `edge/` topic `hems/sensors/*` 移行 | ✅ done(コード; 実機 flash は未実施) |
| T5 | W4.5' PostgreSQL 移行スクリプト検証 + docs 整備 | ✅ done(既定切替は Phase 1 後) |

## 11. 補足: 事前に確認すべき外部依存

- W4.5' 実施前に `distribution.md` Phase 計画と整合性を再確認すること。
- W3.8b 実施前に、対象 edge デバイスの config.json に `topic_prefix` override がないか確認すること。
- 全タスク完了後、`docs/refactor/2026-06-11/META_REVIEW_REPORT.md` の Follow-up 欄を更新すること。
