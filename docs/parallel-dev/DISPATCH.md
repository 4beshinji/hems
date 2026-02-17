# Worker Dispatch — Session K タスク発行

全ワーカーは作業開始前にこのファイルと [WORKER_GUIDE.md](./WORKER_GUIDE.md) を読むこと。

## ✅ Worktree 導入済み

| レーン | worktree パス | ブランチ |
|-------|--------------|---------|
| Main | `/home/sin/code/Office_as_AI_ToyBox` | `main` |
| L3 | `/home/sin/code/soms-worktrees/L3` | `lane/L3-*` |
| L4 | `/home/sin/code/soms-worktrees/L4` | `lane/L4-*` |
| L5 | `/home/sin/code/soms-worktrees/L5` | `lane/L5-*` |
| L6 | `/home/sin/code/soms-worktrees/L6` | `lane/L6-*` |
| L7 | `/home/sin/code/soms-worktrees/L7` | `lane/L7-*` |
| L9 | `/home/sin/code/soms-worktrees/L9` | `lane/L9-*` |

**ルール**: メインディレクトリで `git checkout` 禁止。各自の worktree パスで作業すること。

## main HEAD: `c689908`

Session J の全タスク完了・テスト検証済み。**マージ未実施** — 全修正はブランチ上のみ。

---

## 監視 #7 — Session K 分析 (テスト実行による検証)

### ブランチ状態

| レーン | HEAD | ブランチ | Session J 後の追加 | 状態 |
|-------|------|---------|-------------------|------|
| L3 | `bd98359` | `lane/L3-voice-model-and-fixes` | なし | クリーン |
| L4 | `ca3460b` | `lane/L4-error-boundary-and-users` | なし | クリーン |
| L5 | `266298d` | `lane/L5-session-j-fixes` | +1 (unit tests 58 assertions) | クリーン |
| L6 | `4f24921` | `lane/L6-session-j-hardening` | +2 (acceptance + session J tests) | クリーン |
| L7 | `cdd1717` | `lane/L7-session-j-infra` | なし | クリーン |
| L9 | `b12deae` | `lane/L9-wallet-app` | +3 (vitest 57 tests) | クリーン |

### テスト実行結果

| テスト | 結果 |
|-------|------|
| L4 frontend build | ✅ PASS (338KB) |
| L7 compose config (main + edge-mock) | ✅ PASS |
| L9 vitest (57 tests) | ✅ PASS |
| L9 build | ✅ PASS (264KB + sw.js) |
| タスク作成→受諾→完了 | ✅ ライフサイクル全通過 |
| Voice synthesize | ✅ 4.31s 音声生成 |
| Voice announce (LLM→VOICEVOX) | ✅ 7.1s |
| Voice announce_with_completion (dual) | ✅ announce 8.7s + complete 5.1s |
| Wallet task-reward (複式記帳) | ✅ DEBIT/CREDIT ペア |
| Wallet P2P 5% burn | ✅ fee=100 on 2000 transfer |
| Wallet 残高不足チェック | ✅ REJECTED (既実装) |
| Dashboard→Wallet 自動報酬連携 | ✅ bounty=500 → 残高+500 |
| 拒否音声ストック | ✅ 80/100 stock |
| Brain ReAct ループ (30s) | ✅ 稼働中 |
| Perception (3カメラ監視) | ✅ 稼働中 |
| nginx 全ルート | ✅ 6/7 (voice root 404 は仕様) |

### 新規発見 (Session K テスト)

| ID | 重要度 | 内容 | 担当 |
|----|--------|------|------|
| **H-10** | **CRITICAL** | Virtual Edge が MQTT 認証失敗 ("Not authorized") | L7 |
| **H-11** | **HIGH** | タスク完了時に QR コードが表示されない — ダッシュボードとウォレットアプリの報酬受取フロー未接続 | L4 + L9 |
| M-10 | MEDIUM | main にマージされていないため、稼働中サービスは Session J 修正なし (bounty=0 受け入れ等) | 全体 |
| L-9 | LOW | Brain が rate limit で毎サイクル同じタスク作成を試行し続けている | L6 |

### H-10 詳細: Virtual Edge MQTT 認証
```
mosquitto.conf: allow_anonymous false, password_file /mosquitto/config/passwd
virtual-edge env: MQTT_BROKER=mosquitto, MQTT_PORT=1883 (MQTT_USER/MQTT_PASS 未設定)
結果: "Connected to MQTT Broker with result code Not authorized" → センサーデータ送信不可
```
Brain は認証済みで正常接続。Virtual Edge のみ認証情報がない。

### H-11 詳細: QR 報酬フローの断絶

**現在の動作** (サーバー間通信):
```
Dashboard frontend → PUT /tasks/{id}/complete
  → Dashboard backend → POST wallet:8000/transactions/task-reward (fire-and-forget)
    → Wallet がシステムウォレットから報酬を付与
```
ユーザーがダッシュボードでタスクを完了するとサーバー間で自動的に報酬が付与される。

**不足している部分**:
1. ダッシュボードにタスク完了後の QR コードが表示されない
2. ウォレットアプリの Scan ページは `soms://reward?task_id=X&amount=Y` を解析する準備ができているが、QR を生成する側がない
3. ダッシュボードの UI テキストに「QR コードを読み取ってください」とあるが QR は未実装

**提案フロー**:
```
Dashboard: タスク完了 → 完了カードに QR ボタン表示
  → タップで画面中央に大きな QR コード表示
    (内容: soms://reward?task_id={id}&amount={bounty_gold})
  → ユーザーがスマホのウォレットアプリで QR スキャン
    → Wallet App Scan ページが自動的に claimTaskReward() を呼び出し
    → ウォレット残高に報酬追加
```

---

## レーン別タスク (Session K)

**最優先はマージ + H-10/H-11 の修正。**

---

### L3 — Voice Service

**worktree**: `/home/sin/code/soms-worktrees/L3`
**現状**: Session J 完了、テスト追加なし。マージ待ち。

| # | 優先度 | タスク | 詳細 |
|---|--------|--------|------|
| 1 | **HIGH** | main へ rebase | `git rebase main` で最新化。コンフリクトがあれば解決 |
| 2 | MEDIUM | rejection_stock ディスククリーンアップ | `MAX_STOCK=100` 超過時にディスク上の古い mp3 も削除 |
| 3 | MEDIUM | /health に LLM 接続チェック追加 | VOICEVOX だけでなく LLM (mock-llm) への接続も /health で確認 |
| 4 | LOW | テスト追加 | 他レーン (L5, L6, L9) がテスト整備済み。voice service にも基本テスト追加 |

---

### L4 — Dashboard (Backend + Frontend)

**worktree**: `/home/sin/code/soms-worktrees/L4`
**現状**: Session J 完了。**H-11 (QR 報酬フロー) の対応が必要**。

| # | 優先度 | タスク | 詳細 |
|---|--------|--------|------|
| 1 | **HIGH** | main へ rebase | `git rebase main` で最新化 |
| 2 | **HIGH** | タスク完了時の QR コード表示 | TaskCard の完了状態に「QR で報酬を受け取る」ボタン追加。タップで画面中央にモーダルで大きな QR コードを表示。QR 内容: `soms://reward?task_id={id}&amount={bounty_gold}`。ライブラリ: `qrcode.react` (React コンポーネント) |
| 3 | HIGH | bounty 表示を TaskCard に追加 | bounty_gold の値を TaskCard UI に表示 (例: 🪙1000)。報酬が見えないと受諾判断ができない |
| 4 | MEDIUM | 供給量統計の自動更新 | SupplyBadge を 60 秒ごとに自動 refresh |
| 5 | LOW | タスク一覧の空状態 UI | タスクが 0 件のときの empty state メッセージ |

**QR コード実装の詳細**:
```bash
# qrcode.react をインストール
cd /home/sin/code/soms-worktrees/L4/services/dashboard/frontend
npm install qrcode.react
```
```tsx
// QR モーダルコンポーネント (概要)
import { QRCodeSVG } from 'qrcode.react';

function RewardQR({ taskId, bounty }: { taskId: number; bounty: number }) {
  const value = `soms://reward?task_id=${taskId}&amount=${bounty}`;
  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
      <div className="bg-white p-8 rounded-2xl text-center">
        <QRCodeSVG value={value} size={280} />
        <p className="mt-4 text-lg font-bold">スマホで読み取ってください</p>
        <p className="text-sm text-gray-500 mt-1">{bounty} SOMS</p>
      </div>
    </div>
  );
}
```

---

### L5 — Wallet Service

**worktree**: `/home/sin/code/soms-worktrees/L5`
**現状**: Session J 完了 + unit tests (58 assertions)。

| # | 優先度 | タスク | 詳細 |
|---|--------|--------|------|
| 1 | **HIGH** | main へ rebase | `git rebase main` で最新化。`*.db` テストファイルを `.gitignore` に追加 |
| 2 | HIGH | task-reward の重複防止を QR フロー対応に | 現在 `reference_id: "task:{id}"` で重複チェック。これはサーバー間報酬付与と QR スキャン報酬が二重にならないように保護する重要な仕組み。**変更不要** だが、409 エラー時のメッセージを `"Already claimed"` に統一 |
| 3 | MEDIUM | demurrage バックグラウンドジョブ | 2%/日 のデマレッジを定期実行するスケジューラ |
| 4 | MEDIUM | supply キャッシュ整合性 | demurrage 実行後に supply キャッシュをクリア |
| 5 | LOW | テスト DB ファイルの .gitignore | `*.db`, `test_*.db` を追加 |

---

### L6 — Brain

**worktree**: `/home/sin/code/soms-worktrees/L6`
**現状**: Session J 完了 + テスト追加 (acceptance + session J tests)。

| # | 優先度 | タスク | 詳細 |
|---|--------|--------|------|
| 1 | **HIGH** | main へ rebase | `git rebase main` で最新化。テストスクリプトを整理 |
| 2 | HIGH | 既存タスク重複チェックの改善 | Brain が Rate limit に達した後も毎サイクル同じ「室温を下げてください」を試行し続けている。**active_tasks に同タイトルが存在する場合は create_task を呼ばない** ロジックを cognitive_cycle に追加 |
| 3 | MEDIUM | WorldModel イベント上限 | `zone.events` を最大 100 件に制限 |
| 4 | MEDIUM | cognitive_cycle メトリクスログ | 各サイクルの iteration 数・tool call 数・所要時間をログ出力 |
| 5 | LOW | テストスクリプトを tests/ に移動 | `infra/scripts/test_l6_*.py` → `services/brain/tests/` |

---

### L7 — Infra / Docker

**worktree**: `/home/sin/code/soms-worktrees/L7`
**現状**: Session J 完了。**H-10 (Virtual Edge MQTT 認証) の修正が必要**。

| # | 優先度 | タスク | 詳細 |
|---|--------|--------|------|
| 1 | **CRITICAL** | Virtual Edge の MQTT 認証修正 | `docker-compose.edge-mock.yml` の `virtual-edge` に `MQTT_USER=${MQTT_USER:-soms}` と `MQTT_PASS=${MQTT_PASS:-soms_dev_mqtt}` を追加。**テスト確認済み**: "Connected to MQTT Broker with result code Not authorized" がログに出続けている |
| 2 | **HIGH** | main へ rebase | `git rebase main` で最新化 |
| 3 | HIGH | docker-compose.yml に主要サービスの healthcheck 追加 | brain, backend, voice-service, wallet に healthcheck 定義追加 |
| 4 | MEDIUM | perception の network_mode ドキュメント化 | host ネットワークの理由をコメントで明記 |
| 5 | LOW | Docker イメージ軽量化 | slim ベースイメージ + `pip install --no-cache-dir` |

**H-10 修正例** (`docker-compose.edge-mock.yml`):
```yaml
virtual-edge:
  environment:
    - MQTT_BROKER=mosquitto
    - MQTT_PORT=1883
    - MQTT_USER=${MQTT_USER:-soms}      # ← 追加
    - MQTT_PASS=${MQTT_PASS:-soms_dev_mqtt}  # ← 追加
```

---

### L9 — Mobile Wallet App (PWA)

**worktree**: `/home/sin/code/soms-worktrees/L9`
**現状**: Session J 完了 + vitest (57 tests)。**H-11 のアプリ側対応が必要**。

| # | 優先度 | タスク | 詳細 |
|---|--------|--------|------|
| 1 | **HIGH** | main へ rebase | `git rebase main` で最新化 |
| 2 | **HIGH** | QR スキャン→報酬受取の UX 完成 | Scan ページの `parseQR` + `claimTaskReward` は実装済み。**追加**: スキャン成功時にアニメーション (confetti / check mark)、受取金額の大きな表示、ホーム画面への自動遷移 (3秒後) |
| 3 | HIGH | Dockerfile 作成 | wallet-app 用の Dockerfile (nginx ベース) を作成。`docker-compose.yml` に追加 |
| 4 | MEDIUM | クライアントサイド API URL 設定 | プロダクション向けに `VITE_WALLET_API_URL` を fetch URL にも反映 |
| 5 | MEDIUM | ホーム画面に最近のタスク報酬表示 | transaction_type が `TASK_REWARD` の最新エントリを目立つ形で表示 |
| 6 | LOW | inputMode="numeric" 追加 | 金額入力フィールドにモバイルキーボード最適化 |

---

## ISSUE トラッカー

### 解決済み (Session I + J)
| ID | 内容 | 解決方法 |
|----|------|---------|
| H-5 | Sanitizer rate limit timing | L6 修正済み (744649e) |
| H-6 | WalletBadge render-phase setState | L4 削除で解消 |
| H-7 | bounty_gold=0 受け入れ | L4 修正済み (ca3460b) — マージ待ち |
| H-8 | XP multiplier 報酬未適用 | L5 修正済み (8f33031) — マージ待ち |
| H-9 | Brain タスク作成上限未実装 | L6 修正済み (4073733) — マージ待ち |
| M-5 | Perception network_mode:host | 問題なし (ポートマッピング経由) |
| M-7 | Voice Task model too simple | L3 修正済み (fdb905d) |
| M-8 | LLM_MODEL デフォルトなし | L7 修正済み (65fcf55) — マージ待ち |
| M-9 | QR Chrome/Edge のみ | L9 修正済み (823967b) — マージ待ち |

### 新規 (Session K)
| ID | 重要度 | 内容 | 担当 |
|----|--------|------|------|
| ~~H-10~~ | ~~CRITICAL~~ | ✅ 解決済み (Session M以前に修正マージ済み。docker-compose.edge-mock.yml に MQTT_USER/MQTT_PASS 追加 + main.py に username_pw_set() 実装済み。2026-02-17 起動テストで `result code Success` 確認) | L7 |
| ~~H-11~~ | ~~HIGH~~ | ✅ 解決済み (Session M でコード実装完了済み。フロントエンド再ビルドで `qrcode.react` バンドル + `soms-frontend`/`soms-wallet-app` コンテナ起動確認。TaskCard QR ボタン・モーダル表示、Wallet App Scan ページ稼働) | L4 + L9 |
| L-9 | LOW | Brain が rate limit 後も同じタスク作成を試行し続ける | L6 |

---

## マージ手順 (最優先)

全レーンの Session J ブランチを main にマージする。

```bash
# 1. L7 (infra) — compose 変更は他に影響するため最初
cd /home/sin/code/soms-worktrees/L7 && git rebase main

# 2. L3 (voice) — 独立性高い
cd /home/sin/code/soms-worktrees/L3 && git rebase main

# 3. L5 (wallet) — 独立性高い
cd /home/sin/code/soms-worktrees/L5 && git rebase main

# 4. L6 (brain) — voice/dashboard 依存あり
cd /home/sin/code/soms-worktrees/L6 && git rebase main

# 5. L4 (dashboard) — brain/wallet 依存あり
cd /home/sin/code/soms-worktrees/L4 && git rebase main

# 6. L9 (wallet-app) — wallet 依存あり
cd /home/sin/code/soms-worktrees/L9 && git rebase main
```

各レーンは rebase 後に main で `git merge --no-ff lane/L{N}-*` を実行。
