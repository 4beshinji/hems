# メタレビュー報告書: 2026-05-25 / 2026-06-11 監査・リファクタリングの妥当性評価

## 結論

2026-05-25 監査・リファクタリングと 2026-06-11 後続対応は、**実装上ほぼ完了しており、品質ゲートも通過している**。`make lint` / `make test-quick` / frontend vitest はすべて PASS（Python 2108 passed / frontend 48 passed）。

ただし、**計画書・監査サマリ・実装マップが実態から大きく遅れており、読者が現状を誤解するリスクが残っている**。2026-06-11 PLAN.md は実施済み項目を未着手のまま列挙し、audit/2026-06-11/SUMMARY.md も「frontend テストゼロ」「healthcheck 欠落」など陳腐化した記述を含む。また、2026-05-25 META_AUDIT_REPORT.md では A1/A2/A3 follow-up のコミット帰属が不正確。

未実装は **W3.8b(edge ファーム topic 変更)・W3.8c(office/* 互換 window 削除)・W4.5' PostgreSQL 既定化・W1.4 REST 経路 params 検証・W1.7 セキュリティテスト追加拡充** に限られ、いずれも計画的な残タスクとして妥当。

## 監査対象と範囲

- 2026-05-25 サービス単位実装監査: `docs/audit/2026-05-25/`
- 2026-05-25 リファクタリング: `docs/refactor/2026-05-25/PLAN.md` / `LEDGER.md` / `META_AUDIT_REPORT.md`
- 2026-06-11 技術的負債・設計監査: `docs/audit/2026-06-11/SUMMARY.md`
- 2026-06-11 リファクタリング計画: `docs/refactor/2026-06-11/PLAN.md`
- 該当する実コード commit: 2026-05-25 系 33 done + meta-audit follow-up、2026-06-11 系 W1〜W5 実装 commit
- 検証: `make lint` / `make test-quick` / frontend `pnpm test`

対象外: `feat/distribution` 本体、Android アプリの詳細実装レビュー、外部リポジトリ `localcraw`。

## 評価軸

1. **監査所見の妥当性**: P0/P1/P2 分類は影響度に見合っているか
2. **実装の計画適合性**: PLAN.md の受け入れ条件を満たしているか
3. **テスト・品質**: 回帰テストは追加され、CI は通過しているか
4. **ドキュメント整合性**: 実装が IMPLEMENTATION_MAP / CLAUDE.md / README / env.example に反映されているか
5. **残リスク管理**: deferred / 未実施項目が適切に文書化されているか

## Findings

### A0 — 完了判定を撤回すべき重大欠陥

- **該当なし**。
  - 全テストが PASS し、P0 相当の挙動ブロッカーは確認されなかった。
  - 2026-05-25 META_AUDIT の A1（BACKEND_API_KEY 配線漏れ）は後続 commit で修正済み。

### A1 — 運用・認知上不具合につながる文書・実態の不整合

- **2026-06-11 PLAN.md が大幅に陳腐化**。
  - W1/W2/W3/W4/W5 の多くが実装済みだが、未着手のまま記載されている。
  - 例: W1.1 HEMS_INTERNAL_TOKEN、W3.1 hems_common、W3.4 device_dispatcher 分割、W5.1〜W5.5 frontend 品質改善など。
  - 影響: 読者が現状を誤解し、重複実装や優先度錯誤を招く。
  - 推奨 follow-up: PLAN.md を実態に合わせて更新し、`LEDGER.md` を新設して 1 row = 1 commit の追跡性を復元する。

- **2026-05-25 META_AUDIT_REPORT.md の A1/A2/A3 コミット帰属が不正確**。
  - 報告書は `3636e18` / `f3d02e7` / `878ed3a` で A1/A2/A3 を是正したと記述しているが、実際の A1/A2 コード・test 修正は `7e77409`、A3（LEDGER 再構成）は `8740fd5` で行われた。
  - `3636e18` は主要 helper 配線を追加したが、A1 で指摘された `task_reminder.py` / `tool_handlers_core.py` / `voice_capsule/persist.py` などの direct call-site は含まれていない。
  - 影響: 後続の監査者や開発者が修正履歴を追跡する際に誤導される。
  - 推奨 follow-up: META_AUDIT_REPORT.md の follow-up 欄を訂正し、実際の修正 commit SHA を明記する。

- **docs/audit/2026-06-11/SUMMARY.md が実態と不一致**。
  - 「frontend テストゼロ」「healthcheck 欠落 / resource limits ゼロ / YAML anchor 不使用」「env.example 乖離 ~30 変数」など、W4/W5 実装後に陳腐化した記述が残っている。
  - 影響: 監査サマリとして信頼性を損なう。
  - 推奨 follow-up: SUMMARY.md に「本報告は 2026-06-11 時点のものであり、後続コミットで解消済み」という注記を追加し、解消済み項目を明確にする。

- **services/backend/CLAUDE.md が W1.4 の未実装を隠蔽**。
  - 「action params validation via shared validator」と記述されているが、W1.4（REST 経路への sanitizer 検証適用）は未実装。
  - 影響: 開発者が REST 経路でも params 検証が働いていると誤認する。
  - 推奨 follow-up: W1.4 未実装を明記するか、実装を完了させる。

### A2 — 検証不足・テストギャップ・回帰検知の弱さ

- **brain tool handlers / device registry / MCP bridge のカバレッジが極めて低い**。
  - `tool_handlers_device.py` 15.6%、`tool_handlers_world.py` 9.5%、`device_registry.py` 0%、`mcp_bridge.py` 0% など。
  - 影響: LLM → 実デバイス操作の重要経路が回帰検知できていない。
  - 推奨 follow-up: 最小限の成否パターン単体テストを追加する。

- **frontend 主要コンポーネントが未テスト**。
  - hooks / lib / context はカバーされているが、`dashboard/` / `devices/` / `scenes/` / `tasks/` などユーザーが触れる主要 UI は未テスト。
  - 影響: UI 回帲が目視に依存する。
  - 推奨 follow-up: `ErrorBoundary` と主要表示コンポーネントから smoke test を追加する。

- **テスト実行時に品質警告が残っている**。
  - `test_backend_timeseries_router.py` で `PytestUnhandledThreadExceptionWarning`（aiosqlite / 閉じられたイベントループ）。
  - `HAParser._ha_rainbow` の未 await `RuntimeWarning`。
  - frontend `PowerContext` テストで MSW 未ハンドル警告（`/api/brain/power-mode`）。
  - 影響: テストは pass するが、非同期リソース管理や coroutine 呼び出しに潜在的な不具合の可能性。
  - 推奨 follow-up: 警告の根本原因を調査し、fixture のクリーンアップ / await / MSW handler 追加を行う。

- **`docs/IMPLEMENTATION_MAP.md` が実装に追従していない**。
  - `DeviceDispatcher` → `devices/` パッケージ、`DashboardClient` → split ファイル、`hems_common` 追加、W2.1 閾値一本化、W3.3 bridge status 発行状況、W4.5'-mig スクリプトなどが未反映。
  - 影響: コード ↔ ドキュメントの canonical SoT として機能しなくなる。
  - 推奨 follow-up: IMPLEMENTATION_MAP.md §2.1 / §4 / §6 / §9 を更新する。

### A3 — 軽微な記述の食い違い

- **W2.2 / W2.3 の計画記述と実装範囲に齟齬**。
  - PLAN.md では「stdlib・logger は直接 import」「`_rule_engine.datetime` 等の排除」とあるが、実装は閾値 facade 撤廃に留まり、`_world_model.time.time()` / `_rule_engine.datetime.now()` 等は残存。
  - 影響: 計画と実装の境界が不明瞭。
  - 推奨 follow-up: PLAN.md の W2.2/W2.3 記述を「閾値 facade 撤廃」に修正し、残った stdlib/logger facade 参照を別 row または TODO として追加する。

- **README.md の小さな不整合**。
  - キャラクターテンプレート数が 5 と記載（実際は 6）。
  - TTS バックエンドが 4 つと記載（`style-bert-vits2` / `aivoice` 漏れ）。
  - Optional Profiles に `mock` / `tapo` / `zigbee` / `stt` が欠落。
  - Brain ツール数が 46 と記載（実際は 58）。
  - 影響: 新規参入者の誤認。
  - 推奨 follow-up: README.md の数値・プロファイル一覧を更新する。

- **`infra/scripts/check_env_compose.py` が `VITE_BACKEND_URL` を WARN**。
  - frontend runtime 変数のため compose 未参照は正しいが、誤検知として検出されている。
  - 影響: CI ログに不要な警告。
  - 推奨 follow-up: `ENV_ONLY_OK` に `VITE_BACKEND_URL` を追加する。

## 妥当と判断した範囲

- **2026-05-25 非 deferred 33 row**: PLAN.md と概ね一致し、回帰テスト・test count も整合する。
- **メタ監査 A1/A2/A3 の修正**: 実際の修正 commit（`7e77409` / `8740fd5`）により、BACKEND_API_KEY 配線漏れは解消、test は 1283 passed で完走。
- **2026-06-11 W1 セキュリティ**: HEMS_INTERNAL_TOKEN 認証、device_id 検証、webhook replay 防御、chat rate limit、CSP ヘッダが実装済み。
- **2026-06-11 W2 構造改革**: `RuleEngine.evaluate` / `cognitive_cycle` / `_process_mqtt` / `_get_physical_context` / `_update_biometric_state` の分割と unit test 追加が完了。
- **2026-06-11 W3 ブリッジ基盤**: `hems_common` 新設、9 ブリッジ移行、status topic 統一、`device_dispatcher` パッケージ化、`dashboard_client` 分割が完了。
- **2026-06-11 W4 インフラ**: env 同期、YAML anchor / healthcheck / resource limits、CI 突合、孤児整理が完了。PostgreSQL 移行スクリプトも実装済み。
- **2026-06-11 W5 frontend**: vitest + MSW 基盤、queryKey 共有 hook、VRM リソース解放、Context 分割、env var 統一が完了。

## 未実施項目

| 項目 | 状態 | 備考 |
|---|---|---|
| W1.4 REST 経路 params 検証 | 未実施 | sanitizer 検証を backend `/devices/{id}/control` に適用 |
| W1.7 セキュリティテスト拡充 | 未実施 | MQTT ACL 拒否 poc 復元、無認証アクセス網羅、injection test |
| W3.8b edge ファーム topic 変更 | 未実施 | `office/*` → `hems/sensors/*`、実機 flash が必要 |
| W3.8c office/* 互換 window 削除 | 未実施 | W3.8b 完了 + 旧 topic 受信 7 日間ゼロ後に着手 |
| W4.5' PostgreSQL 既定化 | 部分実施 | 移行スクリプトは完成、compose/env/default DB 切替は未実施 |

## 検証

- `make lint`: PASS（ruff check / format check ともに clean）
- `make test-quick`: PASS（2108 passed / 2 skipped / 44 deselected / 41.70s）
- `cd services/frontend && pnpm test`: PASS（48 passed / 7 test files / 1.55s、MSW unhandled request 警告あり）
- カバレッジ測定: 総合 65.7%（13612 statements / 4668 missed）

## Follow-up

### 即座に対応推奨（A1）

1. `docs/refactor/2026-06-11/PLAN.md` を実態に合わせ更新し、`LEDGER.md` を新設する。
2. `docs/refactor/2026-05-25/META_AUDIT_REPORT.md` の A1/A2/A3 follow-up コミット帰属を訂正する。
3. `docs/audit/2026-06-11/SUMMARY.md` に「2026-06-11 時点の報告であり、後続で解消済み」の注記を追加する。
4. `services/backend/CLAUDE.md` の W1.4 記述を未実装に合わせ修正または TODO 注記にする。

### 短期対応推奨（A2）

5. `docs/IMPLEMENTATION_MAP.md` §2.1 / §4 / §6 / §9 を最新の実装構造に更新する。
6. `services/brain/CLAUDE.md` の `device_dispatcher.py` / `_ALLOWED_ACTIONS` / `dashboard_client.py` 記述を `devices/` パッケージ / `DEVICE_ALLOWED_ACTIONS` / split ファイルに修正する。
7. README.md の数値・プロファイル・ツール数を更新する。
8. `infra/scripts/check_env_compose.py` の `ENV_ONLY_OK` に `VITE_BACKEND_URL` を追加する。

### 中長期対応推奨（テスト・品質）

9. brain tool handlers 群・`device_registry.py`・`mcp_bridge.py` に最小限の単体テストを追加する。
10. frontend 主要コンポーネントの smoke test を追加する。
11. aiosqlite イベントループ警告と `HAParser._ha_rainbow` 未 await 警告を解消する。
12. W1.4 / W1.7 / W3.8b / W3.8c / W4.5' を計画的に完了させる。

---

*本報告は 2026-06-16 時点のコードベースに対するメタレビュー結果である。*
