# Issue Scan Session — 作業状態レポート

**作成日**: 2026-02-13
**担当**: ワーカーA (リポジトリ全体スキャン + コード修正)
**状態**: 中断 — フェーズ1〜3完了、フェーズ4未着手

---

## 1. このセッションで行ったこと

リポジトリ全体を5つの観点で並行スキャンし、問題点を洗い出してドキュメント化。
その後、依存関係の少ないものから順に修正を実施した。

### スキャン対象と成果物

| 観点 | スキャン内容 | 成果物 |
|------|-------------|--------|
| Git 状態 | マージコンフリクト、staged/unstaged差分、stash | `ISSUES.md` に統合 |
| Docker/インフラ | docker-compose、Dockerfile、nginx、env.example | `ISSUES.md` に統合 |
| Python サービス | brain/voice/dashboard/wallet/perception/mock-llm | `ISSUES.md` に統合 |
| フロントエンド | App.tsx、全コンポーネント、ビルド/lint検証 | `ISSUES.md` に統合 |
| サービス間整合性 | API契約、MQTTトピック、スキーマ、依存パッケージ | `ISSUES.md` に統合 |

**主要成果物**: `/ISSUES.md` — 32件の問題を CRITICAL/HIGH/MEDIUM/LOW に分類、フェーズ別対応計画付き

---

## 2. 修正済み項目

### フェーズ1: ブロッカー解消 (完了)

| ID | ファイル | 修正内容 | 備考 |
|----|----------|----------|------|
| C-2 | `services/dashboard/backend/models.py` | `assigned_to`/`accepted_at` カラム追加 | 他ワーカーが先に反映済み |
| C-3 | `env.example` | DATABASE_URL を PostgreSQL に更新 | 他ワーカーが先に反映済み |
| C-4 | `env.example` | `LLM_MODEL` 追加 | 他ワーカーが先に反映済み |
| H-8 | `.gitignore` | `*.tsbuildinfo` 追加 | **本ワーカーで修正** |

### フェーズ2: データフロー正常化 (完了)

| ID | ファイル | 修正内容 |
|----|----------|----------|
| H-1 | `services/perception/src/monitors/occupancy.py:42` | `"count"` → `"person_count"` (WorldModel との整合) |
| H-2 | — | 誤検知と判定。`_parse_topic` は 3パートトピック対応済み |
| H-3 | `services/brain/src/dashboard_client.py:102-103` | voice_data ログで `.get()` 使用に変更 |
| H-4 | `services/brain/src/mcp_bridge.py` | 他ワーカーが先に修正済み (`payload.get("id", parts[3])`) |
| H-5 | `services/brain/src/sanitizer.py` | 他ワーカーが先に修正済み (`record_task_created()` 分離) |

### フェーズ3: フロントエンド品質 (完了)

| ID | ファイル | 修正内容 |
|----|----------|----------|
| H-6 | `App.tsx:95-96` | `initialLoadDone` の `useRef` 参照を `.current` に修正 (コンパイルエラー) |
| H-6 | `WalletBadge.tsx` | setState-in-effect → render中 state 調整パターンに置換 |
| H-7 | `App.tsx:112` | 依存配列から `initialLoadDone` 除去、`prevTaskIds` に eslint-disable |
| — | `WalletPanel.tsx` | `fetchHistory` を `useCallback` 化、依存配列修正 |

**検証**: `npm run build` 成功、`npm run lint` エラー/警告 0件

---

## 3. 未着手項目 (ISSUES.md フェーズ4)

### フェーズ4: インフラ・セキュリティ改善

| ID | 内容 | 難易度 |
|----|------|--------|
| M-1 | PostgreSQL ポートを `127.0.0.1:5432:5432` に制限 | 低 |
| M-2 | MQTT 匿名アクセス（本番時に認証有効化） | 低 |
| M-3 | RejectionStock のレースコンディション修正 | 中 |
| M-4 | Voice Service LLM 呼び出しにタイムアウト設定 | 低 |
| M-5 | Perception の `network_mode: host` 整理 | 低 |
| M-6 | パッケージバージョン統一 (aiohttp, pydantic) | 中 |
| M-7 | Voice Service の Task モデル拡充 | 低 |
| M-8 | docker-compose の未使用ボリューム `soms_db_data` 削除 | 低 |
| M-9 | Wallet サービスのポート公開削除 | 低 |
| M-10 | frontend の `.dockerignore` 作成 | 低 |
| M-11 | docker-compose.edge-mock.yml にネットワーク定義追加 | 低 |
| M-12 | env.example に POSTGRES_USER/PASSWORD 記載 | 低 |

### LOW 優先度 (8件)

L-1〜L-8 は `ISSUES.md` セクション4 を参照。Dockerfile 最適化、未使用依存削除、ハードコード値修正など。

---

## 4. 他ワーカーとの分担状況

| 担当 | 作業内容 | 状態 |
|------|----------|------|
| 他ワーカー | Git 整理（マージコンフリクト解決、コミット分割） | 完了 |
| 他ワーカー | models.py / sanitizer.py / mcp_bridge.py / dashboard_client.py のリファクタ | 完了 |
| 本ワーカー | ISSUES.md 作成、occupancy.py/App.tsx/WalletBadge.tsx/WalletPanel.tsx 修正 | 完了（中断） |

### 並行作業時の注意点

- **`services/brain/src/dashboard_client.py`**: `_get_session()` コンテキストマネージャパターンに変更済み（他ワーカー）。共有セッション対応。
- **`services/brain/src/sanitizer.py`**: `record_task_created()` が追加済み。`tool_executor.py:77` から呼ばれる。
- **`services/dashboard/frontend/`**: ビルド・lint 全パス状態。App.tsx の `initialLoadDone` は `useRef` で、依存配列は `[tasks, isAudioEnabled, loading, enqueue]`。

---

## 5. 変更ファイル一覧（本ワーカーによる修正のみ）

```
M  .gitignore                                          # *.tsbuildinfo 追加
M  services/perception/src/monitors/occupancy.py       # count → person_count
M  services/brain/src/dashboard_client.py              # .get() ログ修正
M  services/dashboard/frontend/src/App.tsx             # useRef .current 修正、deps修正
M  services/dashboard/frontend/src/components/WalletBadge.tsx   # render中state調整
M  services/dashboard/frontend/src/components/WalletPanel.tsx   # useCallback化
```

---

## 6. 次に取り組むべきこと

1. **ISSUES.md フェーズ4 の MEDIUM 項目を消化** — 独立性が高く並行作業向き
2. **ISSUES.md の更新** — 修正済み項目のステータス反映
3. **E2E テスト実行** — 全修正が統合された状態でのリグレッション確認
4. **IMPLEMENTATION_STATUS.md / HANDOFF.md の更新** — 最新状態の反映
