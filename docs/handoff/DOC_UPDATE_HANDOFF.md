# ドキュメント更新作業 — マルチワーカー引き継ぎ

**作成日**: 2026-02-13
**作業状態**: 中断 (Task 1 途中、Task 2/3 未着手)

---

## 1. 作業の目的

広報用データを現在の実装に合わせて更新する。手順:

1. **技術ドキュメントを正確にする** (本作業)
2. 技術ドキュメントをベースに **広報資料を更新する** (後続作業)

---

## 2. 完了した分析

実装全体を「技術レイヤ」と「思想レイヤ」で分析し、全ドキュメントとの乖離を15項目特定済み。分析結果の全文はこのセッションの会話履歴にあるが、以下に要点を再掲する。

### 技術レイヤの主要乖離 (A系)

| ID | 内容 | 重要度 |
|----|------|--------|
| A-1 | LLMモデル: 設計書は Qwen2.5-32B + vLLM、実装は 14b + Ollama (Q4_K_M) | 高 |
| A-2 | DB: 広報は SQLite のみ記載、実装は Dashboard=SQLite / Wallet=PostgreSQL | 高 |
| A-3 | Frontend: 設計書は React 18 + WebSocket、実装は React 19 + ポーリング | 中 |
| A-4 | GPU: 広報に「32GB VRAM」記載あるが RX 9700 は 16GB | 中 |
| A-5 | Wallet: 設計書の「シンプルスコア」→ 実装は複式簿記。ただしXP付与未接続、インフラ報酬未実装 | 高 |
| A-6 | Data Lake / Data Mart: 広報で「50,000:1圧縮」を主張するがパイプライン自体が未実装 | 高 |
| A-7 | Voice: SYSTEM_OVERVIEW に rejection stock 未記載 | 低 |
| A-8 | SensorSwarm BLE: 4トランスポート記載だが BLE はスタブのみ | 低 |
| A-9 | Edge: 「PlatformIO C++」記載だが実態は Arduino IDE スケッチ | 低 |

### 思想レイヤの主要乖離 (B系)

| ID | 内容 | 重要度 |
|----|------|--------|
| B-1 | 「Honor System (認証なし・スコアは一日限り)」 vs 実装の User テーブル + 永続 Wallet | 高 |
| B-2 | 「Constitutional AI のみで制御」→ 実際は Sanitizer にハードコード安全弁が存在 | 中 |
| B-3 | 「嵐プロトコル」シナリオ: 天気API・窓アクチュエータ・気圧ハンドラいずれも未実装 | 高 |
| B-4 | 「センサーでタスク完了検証」→ PUT /complete のみ、ビジョン検証なし | 中 |
| B-5 | 「72時間ネットワーク切断耐性」→ Data Lake なしでは検証不可能 | 中 |
| B-6 | 「エラー率 0% (12リクエスト)」→ サンプル数が統計的に不十分 | 低 |

---

## 3. タスク定義 (3タスク)

### Task 1: SYSTEM_OVERVIEW.md 更新 ← **進行中・途中**

**ファイル**: `docs/SYSTEM_OVERVIEW.md`

**完了済みの編集**:
- [x] セクション 2.2: Constitutional AI → 「Constitutional AI + Safety Guard Rails」に修正。Sanitizer のハードコード制約を明記
- [x] セクション 6.1: デバイス種類に unified-node + SensorSwarm (Hub+Leaf) を追加
- [x] セクション 7.2: Dashboard Backend — タスクライフサイクル (Pending→Accepted→Completed)、Wallet 統合、2段階重複検知
- [x] セクション 7.3: Voice — 9エンドポイント表、rejection ストック、場面別音声フロー、正常時 speak 禁止
- [x] セクション 7.4: **新規追加** — Wallet 経済システム (複式簿記、XP乗数、実装状況)
- [x] セクション 11: 技術スタック表 — DB (PostgreSQL+SQLite)、GPU (RX 9700 RDNA4)、LLM (14b Q4_K_M)
- [x] セクション 12: ディレクトリ構成 — wallet/, swarm/, unified-node, voice 詳細、docs/ 整理
- [x] セクション 13: サービスポート表に Wallet (8003) と PostgreSQL (5432) 追加、VRAM 記述修正

**未完了の編集**:
- [ ] セクション 2.1: 有機体メタファー表に Wallet (経済) 行を追加、LLM を "Qwen2.5:14b" に修正
- [ ] セクション 6.3: 診断ツール — SensorSwarm 用ツールの追記 (もしあれば)
- [ ] セクション 9.1: 安全機構の多層防御図 — 既に正確だが「Sanitizer はハードコード」と明記済みか再確認
- [ ] セクション 10: データフロー — 受諾/完了/無視の音声フローを追記するか検討
- [ ] 補遺: 設計文書索引に CURRENCY_SYSTEM.md、CITY_SCALE_VISION.md を追加
- [ ] 全文レビュー: 「32GB VRAM」「32B」への残留参照がないか確認

### Task 2: CITY_SCALE_VISION.md 更新 ← **未着手**

**ファイル**: `docs/CITY_SCALE_VISION.md`

**必要な編集**:
- [ ] セクション 4.2 (Core Hub ハードウェア): 最小構成を「16GB VRAM (RX 9700 実績)」に修正、32GB は推奨構成として残す
- [ ] セクション 6 Phase 0 達成状況チェックリスト:
  - 追加: `[x] SensorSwarm Hub+Leaf 2階層ネットワーク`
  - 追加: `[x] Wallet 複式簿記 (タスク報酬支払い動作)`
  - 追加: `[x] Voice rejection ストック (事前生成100)`
  - 追加: `[x] Mock LLM ツール有無分岐`
  - 追加: `[x] E2E 統合テスト (7シナリオ PASS)`
  - 修正: `[ ] 本番 LLM 稼働検証` → `[x] 本番 LLM (Ollama qwen2.5:14b, ~51 tok/s)`
  - 追加: `[ ] Wallet XP 付与統合 (xp_scorer 未接続)`
  - 追加: `[ ] インフラ稼働報酬スケジューラ`
- [ ] セクション 7.1 (追加が必要なコンポーネント): 現状列を更新
  - Event Store: 「なし」のまま (正確)
  - Data Lake: 「なし」のまま (正確)
  - OTA 更新: 「なし」のまま (正確)
- [ ] Phase 2 の「72時間自律動作」: 注記追加 — Phase 2 の目標であり現在の能力ではない
- [ ] 「Docker 起動・統合テスト完了」→ チェック済みに変更 (E2E テスト PASS)

### Task 3: 設計ドキュメントに歴史的注記を追加 ← **未着手**

**対象ファイル**:
- `docs/architecture/kick-off.md`
- `docs/architecture/detailed_design/01_central_intelligence.md`
- `docs/architecture/detailed_design/04_economy_dashboard.md`

**作業内容**: 各ファイルの先頭に以下の形式で注記を追加:

```markdown
> **注**: 本文書は設計初期段階 (2026-01) の技術検討記録です。
> 現在の実装状況は [`docs/SYSTEM_OVERVIEW.md`](../SYSTEM_OVERVIEW.md) を参照してください。
> 主な変更点: [ファイル固有の変更点をここに記載]
```

ファイル固有の変更点:
- **kick-off.md**: Qwen2.5-32B → 14b、vLLM → Ollama、構造化出力 (outlines) → 不使用
- **01_central_intelligence.md**: 同上 + W7800/W6800 → RX 9700 (RDNA4)
- **04_economy_dashboard.md**: React 18 → 19、WebSocket → REST ポーリング、シンプルスコア → 複式簿記 Wallet

---

## 4. 後続作業 (広報資料更新)

Task 1-3 完了後、以下の広報資料を技術ドキュメントに基づいて更新する:

| ファイル | 主な修正点 |
|---------|----------|
| `docs/promo/article.md` | 嵐プロトコルを「デモ可能なシナリオ」に差替え or 注記、VRAM 修正、DB 修正 |
| `docs/promo/slides_tech.md` | 同上 + パフォーマンス数値の文脈追加、BLE スタブ明記 |
| `docs/promo/slides_pitch.md` | 「32GB VRAM」→修正、Data Lake/Mart の表現を「Phase 0 完了条件」として記載 |
| `docs/promo/figma_assets.md` | 技術スタック表の整合性確認 |
| `README.md` | 4層→記述の整合性、SensorSwarm・Wallet の言及追加 |

---

## 5. 並列作業の分担案

| ワーカー | タスク | 依存関係 |
|---------|--------|---------|
| Worker A | Task 1 (SYSTEM_OVERVIEW.md 残り) | なし — 即座に着手可能 |
| Worker B | Task 2 (CITY_SCALE_VISION.md) | なし — 即座に着手可能 |
| Worker C | Task 3 (設計ドキュメント注記) | なし — 即座に着手可能 |

3タスクは **互いに異なるファイルを編集するため完全に並列実行可能**。

Task 1 の未完了項目は全てセクション番号で特定済みなので、SYSTEM_OVERVIEW.md を読めば即座に着手できる。

---

## 6. 参照すべきソース

作業に必要な実装の真実は以下から取得できる:

| 情報 | ソース |
|------|--------|
| Brain 実装詳細 | `services/brain/src/` (特に main.py, tool_registry.py, system_prompt.py) |
| Voice エンドポイント | `services/voice/src/main.py` |
| Wallet モデル/API | `services/wallet/src/models.py`, `routers/` |
| Dashboard モデル | `services/dashboard/backend/models.py` |
| SensorSwarm プロトコル | `edge/lib/swarm/message.py` |
| Docker 構成 | `infra/docker-compose.yml` |
| GPU デバイス | `infra/docker-compose.yml` の ollama/perception セクション |
| LLM 設定 | `.env` + `env.example` |
