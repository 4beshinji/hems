# Session H ハンドオフ — ウォレット分離設計

**日時**: 2026-02-13
**ブランチ**: main
**HEAD**: `b1be95b`
**作業者**: Claude Opus 4.6 (Session H)

---

## 1. セッション概要

当初「決闘 (賭け) システム」の実装に着手したが、ユーザーと方向性を議論した結果、**ダッシュボードとウォレットアプリの完全分離**という根本的なアーキテクチャ変更を決定。決闘コードは全てrevert し、設計整理とダッシュボード簡素化を実施。

### 意思決定の経緯

1. 決闘バックエンド (models, service, router) を実装完了
2. フロントエンド着手直前にユーザーが方針転換を提案
3. 合意: ダッシュボードはキオスク、ウォレットはスマホアプリに分離
4. 決闘コードは全revert、設計ドキュメント作成、ダッシュボード簡素化

---

## 2. 変更ファイル (未コミット)

### 変更したファイル (今セッション)

| ファイル | 変更内容 |
|---------|---------|
| `services/dashboard/frontend/src/App.tsx` | UserSelector, WalletBadge, WalletPanel を除去。供給量バッジ追加。タスク受諾を匿名化 |
| `docs/architecture/wallet-separation.md` | **新規**: 分離アーキテクチャ設計ドキュメント |

### 前セッションからの未コミット (変更なし、そのまま残存)

| ファイル | 内容 |
|---------|------|
| `services/wallet/src/main.py` | demurrage ループ、monetary_policy import 追加 |
| `services/wallet/src/routers/transactions.py` | P2P送金、手数料burn、fee preview 追加 |
| `services/wallet/src/schemas.py` | TransferFeeInfo, P2PTransferRequest/Response 追加 |
| `services/wallet/src/services/ledger.py` | burn() 関数、_update_supply() 追加 |
| `services/wallet/src/services/demurrage.py` | **新規**: デマレッジ (滞留税) 適用ロジック |
| `services/wallet/src/services/monetary_policy.py` | **新規**: 手数料率、最低送金額、デマレッジ率 |
| `services/dashboard/frontend/src/components/WalletPanel.tsx` | P2P送金UI、fee preview (※ 分離後は不要になる可能性) |

---

## 3. 新アーキテクチャの要点

**詳細**: `docs/architecture/wallet-separation.md`

| 責務 | ダッシュボード (壁掛キオスク) | モバイルウォレット (スマホ) |
|------|---------------------------|-------------------------|
| アカウント | なし | 個人ウォレット管理 |
| タスク | 表示・受諾・完了 | 関与しない |
| 報酬受取 | QR コード表示 | QR スキャン → 入金 |
| 残高 | 流通量のみ表示 | 個人残高表示 |
| 送金 | なし | P2P 送金 |
| 決闘 | なし | NFC/BLE で P2P |

### 報酬フローの変更

```
Before: 完了ボタン → Backend → Wallet に直接 task-reward (user_id 必須)
After:  完了ボタン → Backend → RewardClaim トークン発行 → QR 表示 → スマホスキャン
```

---

## 4. 次セッションへの推奨作業

### Phase 1: 報酬請求トークン (最優先)

| タスク | ファイル | 詳細 |
|--------|---------|------|
| RewardClaim モデル追加 | `services/wallet/src/models.py` | token, task_id, amount, expires_at, claimed_by |
| Claim エンドポイント | `services/wallet/src/routers/claims.py` | `POST /claim/{token}`, `GET /claim/{token}/info` |
| トークン発行ロジック | `services/dashboard/backend/routers/tasks.py` | タスク完了時に Wallet Service へトークン発行リクエスト |
| QR 表示 UI | `services/dashboard/frontend/src/components/TaskCard.tsx` | 完了後に QR コードを表示 |

### 判断が必要な事項

| 項目 | 選択肢 |
|------|--------|
| 未コミットの P2P/デマレッジコード | コミットするか、分離設計に合わせてリファクタするか |
| WalletPanel.tsx / WalletBadge.tsx / UserSelector.tsx | App.tsx から除去済みだが、ファイル自体を削除するか残すか |
| モバイルアプリの技術選択 | React Native / PWA / Flutter |
| 認証方式 | デバイスバインド / PIN / QR ペアリング |

---

## 5. 注意事項

- `App.tsx` の handleAccept は現在 `body: JSON.stringify({})` (空) で `/accept` を呼んでいる。Backend 側が `user_id` を optional にしていない場合は 400 エラーになる可能性がある → 確認が必要
- 前セッション群の未コミット wallet コード (ledger.burn, P2P transfer, demurrage, monetary_policy) は全て残存。これらは Wallet Service 内で閉じているため他サービスに影響なし
- `docs/CURRENCY_SYSTEM.md` のセクション8 (フロントエンドUI) は古い情報。分離後に更新が必要
