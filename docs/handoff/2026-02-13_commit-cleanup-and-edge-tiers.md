# コミット整理 + エッジ柔軟構成 — 作業引き継ぎ

**作業者**: ワーカー B (Claude Code Opus 4.6)
**日時**: 2026-02-13 19:15 JST
**ステータス**: 中断 — コミット 5/8 完了、3件残り

---

## 1. 作業概要

2つの作業を並行して実施していた:

1. **エッジデバイス柔軟構成 (Tier 1-4)** — config.json 駆動の unified-node ファームウェア実装
2. **未コミット変更の整理・コミット** — 20ファイルの変更を論理単位でコミット分割

### エッジ Tier 実装 (完了・コミット済み)

別ワーカーが先にコミット (`ae87d6b`) していたため、本ワーカーの Write は上書きとなり差分なし。以下が成果物:

| ファイル | 内容 |
|---------|------|
| `edge/lib/board_pins.py` | 5ボード (DevKitC, XIAO C6/S3/C3, ESP32-CAM) のピンマッピング |
| `edge/lib/drivers/` | 6ドライバ: bme680, mhz19, dht_wrapper, pir, bh1750, sht3x |
| `edge/lib/sensor_registry.py` | I2C 遅延初期化、アドレス自動検出、UART プローブ、エラー隔離 |
| `edge/lib/soms_mcp.py` | `self.config = cfg` 1行追加 (raw config 保持) |
| `edge/office/unified-node/main.py` | config 駆動ファームウェア本体 |
| `edge/office/unified-node/config.json` | テンプレート |
| `edge/office/unified-node/config_examples/` | 5構成例 (tier1×2, tier2×2, tier3×1) |
| `docs/architecture/detailed_design/05_edge_tiers.md` | ティア定義・決定マトリクス・アップグレードパス |
| `docs/architecture/detailed_design/05_edge_bom_tiered.md` | ティアごとの BOM |
| `docs/architecture/detailed_design/05_edge_wiring_tiered.md` | ティア×ボード配線図 (Mermaid) |
| `docs/architecture/detailed_design/05_edge_config_reference.md` | config.json スキーマリファレンス |
| `services/brain/src/world_model/data_classes.py` | pressure/gas_resistance フィールド追加 |
| `services/brain/src/world_model/world_model.py` | pressure/gas_resistance チャンネル処理 + LLMコンテキスト表示 |

---

## 2. コミット整理の状態

### 完了したコミット (5件、origin 未 push)

```
bef6b8a feat: add MQTT authentication to edge clients and test scripts
5abaa10 fix: docker-compose cleanup — remove wallet port exposure and unused volume
246ffc6 fix: voice service dependency alignment and LLM timeout
b975d0e docs: rewrite architecture docs to match current implementation
0821921 fix: dashboard migrate function sync and App.tsx useRef for initialLoadDone
```

別ワーカーによる追加コミット:
```
1927d19 fix: wallet UI reactivity, integration test, and docs sync
```

### 残りの未コミット変更

**注意**: 別ワーカー (`1927d19`) が一部をコミットした可能性がある。以下は中断時点の認識。`git status` で最新状態を確認すること。

#### 中断時点の git status:
```
Untracked:
  docs/handoff/2026-02-13_fix-dashboard-wallet-integration.md  (ワーカー A の引き継ぎ)
  docs/work/DOC_UPDATE_HANDOFF.md  (ドキュメント更新ワーカーの引き継ぎ)
```

#### 中断時点でステージング済みだったが拒否されたコミット:
```
docs/SYSTEM_OVERVIEW.md                — ディレクトリツリー更新
services/dashboard/frontend/src/components/WalletBadge.tsx  — useEffect→render-time sync
services/dashboard/frontend/src/components/WalletPanel.tsx  — useCallback + deps 修正
```

→ このコミットは拒否 (ユーザーが作業中断を指示) したため、ステージング状態が維持されているか `git status` で要確認。別ワーカー (`1927d19`) がコミットしている可能性あり。

---

## 3. 再開時の手順

```bash
# 1. 現在の状態確認
git status -u
git log --oneline -3

# 2. 残り変更があれば確認
git diff --stat
git diff --cached --stat

# 3. 残りをコミット (あれば)
# メッセージ案:
#   "fix: wallet component React patterns and SYSTEM_OVERVIEW directory tree"
#   "docs: rewrite kick-off with current hardware and service stack"
#   "add: wallet integration test and frontend .dockerignore"

# 4. push
git push origin main
```

---

## 4. ISSUES.md の対応状況

本セッション全体 (全ワーカー合計) での進捗:

| ID | 問題 | 状態 | コミット |
|----|------|------|---------|
| C-1 | App.tsx マージコンフリクト | ✅ 解消 | `85df548` |
| C-2 | Task モデル assigned_to/accepted_at | ✅ 修正 | `a8179b4` |
| C-3 | env.example DATABASE_URL | ✅ 修正 | `eeb5f31` |
| C-4 | env.example LLM_MODEL | ✅ 修正 | `eeb5f31` |
| H-1 | Occupancy payload key 不一致 | ✅ 修正 | `a8179b4` |
| H-3 | DashboardClient voice null チェック | ✅ 修正 | `85df548` |
| H-6 | App.tsx useEffect setState | ✅ useRef 化 | `0821921` |
| H-7 | useEffect 依存配列 | ✅ 修正 | `0821921` |
| M-6 | パッケージバージョン統一 | ✅ voice 側 | `246ffc6` |
| M-8 | 未使用ボリューム | ✅ 削除 | `5abaa10` |
| M-9 | Wallet ポート不要公開 | ✅ 削除 | `5abaa10` |
| M-11 | edge-mock ネットワーク定義 | ✅ 追加 | `5abaa10` |
| H-2 | Perception MQTT トピック統一 | ❌ 未対応 | |
| H-4 | MCPBridge request_id | ❌ 未対応 | |
| H-5 | Sanitizer レート制限 | ❌ 未対応 | |
| M-1 | PostgreSQL ポート制限 | ❌ 未対応 | |
| M-3 | RejectionStock race | ❌ 未対応 | |

---

## 5. 並行作業で競合しやすいファイル

| ファイル | 理由 |
|---------|------|
| `infra/docker-compose.yml` | 複数タスクが同時変更 |
| `HANDOFF.md` | 全ワーカーが更新する |
| `services/dashboard/frontend/src/App.tsx` | 過去に何度もコンフリクト |
| `services/brain/src/world_model/world_model.py` | 複数機能が触る |
