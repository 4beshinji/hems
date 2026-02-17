# Worker Dispatch — 並行開発タスク発行

全ワーカーは作業開始前にこのファイルと [WORKER_GUIDE.md](./WORKER_GUIDE.md) を読むこと。

## main HEAD: `117969a`

前回セッション (Session K) の全タスク完了・マージ済み。ISSUES.md 全32件解決済み。

---

## Worktree 状態

現在アクティブなレーンなし。新セッション開始時に `git worktree add` で作成する。

| レーン | worktree パス | ブランチ | 状態 |
|-------|--------------|---------|------|
| Main | `/home/sin/code/Office_as_AI_ToyBox` | `main` | 監視・統合専用 |

**ルール**: メインディレクトリで `git checkout` 禁止。各自の worktree パスで作業すること。

**新しいレーンを追加する場合:**
```bash
git worktree add /home/sin/code/soms-worktrees/L{N} -b lane/L{N}-{description}
```

---

## Issue トラッカー

### 未解決

| ID | 重要度 | 内容 | 備考 |
|----|--------|------|------|
| L-9 | LOW | Brain が rate limit 後も同じタスク作成を試行し続ける | Session K で発見。active_tasks に同タイトルが存在する場合の重複防止が必要 |

### 解決済み

ISSUES.md 全32件解決済み (2026-02-16 確認)。Session K の H-10, H-11 も解決済み。
詳細は [docs/ISSUES.md](../ISSUES.md) および [docs/handoff/CURRENT_STATE.md](../handoff/CURRENT_STATE.md) を参照。

---

## レーン別タスク

次セッションで割り当てる。

| レーン | 担当領域 | タスク数 | 状態 |
|-------|---------|---------|------|
| — | — | — | 未割当 |
