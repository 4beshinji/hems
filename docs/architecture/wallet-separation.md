# ウォレット分離アーキテクチャ — ダッシュボード × モバイルウォレット

**作成日**: 2026-02-13
**ステータス**: 設計案 (未実装)

---

## 1. 設計原則

| 原則 | 理由 |
|------|------|
| ダッシュボードにアカウントを持たない | キオスク型表示装置。誰でも見られる、誰のものでもない |
| 通貨操作はモバイルアプリに集約 | 残高確認・送金・決闘はすべてスマホで完結 |
| 報酬受取は物理行為 (QR スキャン) | 現場にいる人だけが報酬を得られる。不正防止 |
| 決闘は P2P 対面通信 | NFC / Nearby / BLE で相手と直接やりとり |
| DB が消えても痛くない | カジノチップ。実経済とは切り離す |

---

## 2. システム構成図

```
┌─────────────────────────────────────────────────────────────┐
│                       オフィス内                               │
│                                                             │
│  ┌──────────────────────┐    ┌──────────────────────────┐  │
│  │   ダッシュボード (壁掛)  │    │    モバイルウォレットアプリ   │  │
│  │   Kiosk モード         │    │    (スマートフォン)          │  │
│  │                      │    │                          │  │
│  │  ・タスク一覧表示      │    │  ・残高表示               │  │
│  │  ・供給量統計          │    │  ・QR スキャン → 報酬受取   │  │
│  │  ・受諾/完了ボタン     │    │  ・P2P 送金              │  │
│  │  ・完了時 QR コード表示 │    │  ・決闘 (NFC/Nearby)     │  │
│  │  ・音声フィードバック   │    │  ・取引履歴              │  │
│  └──────────┬───────────┘    └──────────┬───────────────┘  │
│             │                           │                   │
│             │ REST (task CRUD)          │ REST (wallet API) │
│             ▼                           ▼                   │
│  ┌──────────────────┐     ┌──────────────────────┐         │
│  │ Dashboard Backend │     │   Wallet Service     │         │
│  │ (tasks, voice)   │     │   (ledger, supply)   │         │
│  │ :8000             │     │   :8003              │         │
│  └──────────────────┘     └──────────────────────┘         │
│             │                           │                   │
│             ▼                           ▼                   │
│  ┌──────────────────────────────────────────────┐          │
│  │              PostgreSQL                       │          │
│  │   public スキーマ (tasks)                     │          │
│  │   wallet スキーマ (wallets, ledger_entries)    │          │
│  └──────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. タスク報酬フロー (変更後)

### Before (現行)
```
ダッシュボードで完了ボタン → Backend → Wallet Service に直接 task-reward
  → user_id でウォレットに入金 (ダッシュボードがユーザーを知っている前提)
```

### After (新設計)
```
1. ダッシュボードで完了ボタン → Backend がタスク完了を記録
2. Backend が「報酬請求トークン」を発行 (一意, 有効期限付き)
3. ダッシュボード画面に QR コードを表示
     QR 内容: https://soms.local/api/wallet/claim/{token}
     または: soms://claim/{token}
4. ユーザーがスマホのウォレットアプリで QR をスキャン
5. アプリ → Wallet Service POST /claim/{token}
     → token 検証 → user_id のウォレットに入金
     → token 無効化 (一度きり)
```

### 報酬請求トークン

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `token` | UUID | 一意識別子 |
| `task_id` | int | 対象タスク |
| `amount` | int | 報酬額 |
| `created_at` | datetime | 発行日時 |
| `expires_at` | datetime | 有効期限 (例: 24時間) |
| `claimed_by` | int? | 請求したユーザーID (NULL = 未請求) |
| `claimed_at` | datetime? | 請求日時 |

**セキュリティ**:
- トークンは一度しか使えない (claimed_by が設定されたら再利用不可)
- 有効期限あり (未請求のまま放置された報酬は消滅)
- QR はダッシュボード画面上にのみ表示 → 物理的にオフィスにいる人だけがスキャン可能

---

## 4. 決闘システム (モバイルアプリ内)

ダッシュボードとは完全に独立。モバイルアプリ同士の P2P 通信で完結。

### 4.1 通信手段

| 手段 | 用途 | 範囲 |
|------|------|------|
| **NFC** | 決闘の開始 (タッチして参加) | 数cm |
| **Nearby / BLE** | 結果の相互報告 | 数m |
| **Wallet API (フォールバック)** | サーバー経由の決闘管理 | 任意 |

### 4.2 フロー

```
┌─────────────┐                    ┌─────────────┐
│  Player A   │                    │  Player B   │
│  (提案者)    │                    │  (参加者)    │
└─────┬───────┘                    └─────┬───────┘
      │                                  │
      │  1. 決闘作成 (ステーク額, ゲーム種)  │
      │  → NFC タッチ / QR 表示            │
      │ ─────────────────────────────────►│
      │                                  │  2. NFC 読取 / QR スキャン
      │                                  │     → 参加確認
      │                                  │
      ├──── 両者: burn(stake) → escrow ───┤
      │                                  │
      │        *** オフラインゲーム ***      │
      │        (じゃんけん、カード、etc.)     │
      │                                  │
      │  3. 結果入力 (勝者を選択)           │
      │ ─────────── BLE/Nearby ──────────►│  4. 結果入力
      │                                  │
      │  5. 合意判定 (ローカル)             │
      │     一致 → settle (勝者に payout)  │
      │     不一致 → dispute (全額焼却)     │
      └──────────────────────────────────┘
```

### 4.3 エスクロー方式 (変更なし)

| ステップ | 操作 | SupplyStats 影響 |
|---------|------|-----------------|
| 参加時 | `burn(user, stake, "DUEL_ESCROW")` | burned += stake |
| 合意決着 | `transfer(system→winner, pot-fee, "DUEL_PAYOUT")` | issued += (pot-fee) |
| 紛争 | なし (既に全額 burn 済み) | 全額焼却 |
| キャンセル | `transfer(system→each, stake, "DUEL_REFUND")` | issued += stake |

---

## 5. ダッシュボードの変更点

### 削除するもの

| コンポーネント | 理由 |
|--------------|------|
| `UserSelector` | アカウント不要。ユーザー選択はモバイルアプリの責務 |
| `WalletBadge` | 残高表示はモバイルアプリの責務 |
| `WalletPanel` | 取引履歴/送金はモバイルアプリの責務 |
| `currentUser` state | ダッシュボードはユーザーを追跡しない |

### 残すもの

| コンポーネント | 理由 |
|--------------|------|
| タスク一覧 (TaskCard) | ダッシュボードの本来の役割 |
| 受諾/完了/無視ボタン | 匿名操作。報酬受取は別途 QR |
| 音声フィードバック | オフィス体験の一部 |
| システム統計 (XP, 完了数) | 全体の活動状況表示 |

### 追加するもの

| 機能 | 説明 |
|------|------|
| 供給量バッジ | `GET /api/wallet/supply` → 流通量表示 |
| 完了時 QR 表示 | タスク完了 → 報酬請求トークン → QR コード表示 |

---

## 6. モバイルウォレットアプリ (新規)

### 6.1 技術選択肢

| 選択肢 | 長所 | 短所 |
|--------|------|------|
| **React Native + Expo** | Web 技術の再利用、NFC/BLE プラグイン | ネイティブ NFC の制約 |
| **PWA (Progressive Web App)** | インストール不要、Web API で NFC | BLE/Nearby は Web API 非対応 |
| **Flutter** | NFC/BLE ネイティブサポート | 技術スタック追加 |

### 6.2 機能一覧

| 機能 | 優先度 | 依存API |
|------|--------|---------|
| ウォレット残高表示 | P0 | `GET /wallets/{user_id}` |
| QR スキャン → 報酬受取 | P0 | `POST /claim/{token}` (新規) |
| 取引履歴 | P0 | `GET /wallets/{user_id}/history` |
| P2P 送金 | P1 | `POST /transactions/p2p-transfer` |
| 決闘 (作成/参加/結果報告) | P1 | Duel API (新規) |
| NFC で決闘開始 | P2 | デバイス間通信 |
| Nearby/BLE で結果交換 | P2 | デバイス間通信 |

### 6.3 認証

ダッシュボードは認証不要 (キオスク)。モバイルアプリは個人のウォレットを管理するため、最低限の認証が必要。

| 方式 | 説明 |
|------|------|
| **デバイスバインド** | 初回起動時に user_id を生成しローカル保存。シンプルだがデバイス紛失で残高喪失 |
| **PIN / パスフレーズ** | ユーザーが設定する短い秘密。サーバー側でハッシュ保存 |
| **QR ペアリング** | 初回にダッシュボード管理画面で発行した QR を読み取ってアカウント紐付け |

---

## 7. Wallet Service API 変更

### 新規エンドポイント

| メソッド | パス | 説明 |
|---------|------|------|
| `POST` | `/claim/{token}` | 報酬請求トークンを消費して入金 |
| `GET` | `/claim/{token}/info` | トークン情報 (額面, 期限) の確認 |

### 新規モデル

```python
class RewardClaim(Base):
    __tablename__ = "reward_claims"
    __table_args__ = {"schema": "wallet"}

    id = Column(Integer, primary_key=True)
    token = Column(PG_UUID(as_uuid=True), unique=True, nullable=False, index=True)
    task_id = Column(Integer, nullable=False)
    amount = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    claimed_by = Column(Integer, nullable=True)
    claimed_at = Column(DateTime(timezone=True), nullable=True)
```

### 決闘 API (モバイルアプリ向け、後日実装)

| メソッド | パス | 説明 |
|---------|------|------|
| `POST` | `/duels/` | 決闘作成 |
| `POST` | `/duels/{id}/join` | 参加 |
| `POST` | `/duels/{id}/result` | 結果報告 |
| `DELETE` | `/duels/{id}` | キャンセル |
| `GET` | `/duels/my` | 自分の決闘一覧 |

---

## 8. 実装ロードマップ

### Phase 0: ダッシュボード簡素化 (今セッション)
- [x] WalletBadge, WalletPanel, UserSelector を App.tsx から除去
- [x] 供給量バッジ追加
- [x] 決闘バックエンドコード revert (設計固めてから再実装)

### Phase 1: 報酬請求トークン (次セッション)
- [ ] `RewardClaim` モデル追加
- [ ] `POST /claim/{token}` エンドポイント
- [ ] Dashboard Backend: タスク完了時にトークン発行
- [ ] Dashboard Frontend: 完了時に QR コード表示

### Phase 2: モバイルウォレット MVP
- [ ] 技術選択 (React Native / PWA / Flutter)
- [ ] 残高表示 + 取引履歴
- [ ] QR スキャン → 報酬受取
- [ ] 基本認証 (デバイスバインド)

### Phase 3: P2P 送金 + 決闘
- [ ] P2P 送金 UI
- [ ] 決闘バックエンド API
- [ ] 決闘 UI (作成/参加/結果報告)
- [ ] NFC / BLE 通信

---

## 9. 移行に関する注意

### 影響を受ける既存コード

| ファイル | 変更内容 |
|---------|---------|
| `App.tsx` | UserSelector, WalletBadge, WalletPanel を除去済み |
| `dashboard/backend/routers/tasks.py` | タスク完了時に直接 wallet 呼び出し → トークン発行に変更 (Phase 1) |
| `services/wallet/src/models.py` | RewardClaim モデル追加 (Phase 1) |
| `CURRENCY_SYSTEM.md` | フロントエンド UI セクション全面書き換え |

### 削除候補のファイル (Phase 1 完了後)

| ファイル | 理由 |
|---------|------|
| `WalletBadge.tsx` | ダッシュボードから不要 |
| `WalletPanel.tsx` | ダッシュボードから不要 |
| `UserSelector.tsx` | ダッシュボードから不要 |

※ 現時点ではファイルを残す (他で import されている可能性の確認が必要)。
