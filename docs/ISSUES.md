# SOMS プロジェクト 問題点一覧

**作成日**: 2026-02-13
**対象**: リポジトリ全体スキャン結果
**ブランチ**: main (HEAD: 5a8bdfc)

---

## 目次

1. [CRITICAL — 即時対応必須](#1-critical--即時対応必須)
2. [HIGH — 早期対応推奨](#2-high--早期対応推奨)
3. [MEDIUM — 改善推奨](#3-medium--改善推奨)
4. [LOW — 余裕があれば対応](#4-low--余裕があれば対応)
5. [対応優先度まとめ](#5-対応優先度まとめ)

---

## 1. CRITICAL — 即時対応必須

### C-1: App.tsx マージコンフリクト未解決 (git UU status)

| 項目 | 内容 |
|------|------|
| **ファイル** | `services/dashboard/frontend/src/App.tsx` |
| **状態** | git index で UU (unmerged) のまま放置 |
| **影響** | `git commit` 不可。全ての未コミット変更がブロックされる |
| **対応** | ファイル内容は既に統合済み。`git add services/dashboard/frontend/src/App.tsx` で解決マーク |

---

### C-2: Task モデルに assigned_to / accepted_at カラムが未定義

| 項目 | 内容 |
|------|------|
| **ファイル** | `services/dashboard/backend/models.py` |
| **参照箇所** | `schemas.py:55-56`, `routers/tasks.py:183-187`, `routers/tasks.py:212-222` |
| **影響** | タスク受諾 (`/tasks/{id}/accept`) が `AttributeError` で即座に失敗。`_task_to_response()` 経由で全 CRUD エンドポイントが壊れる |
| **対応** | models.py に以下を追加: |

```python
assigned_to = Column(Integer, nullable=True)
accepted_at = Column(DateTime(timezone=True), nullable=True)
```

---

### C-3: env.example と docker-compose.yml の DATABASE_URL 不一致

| 項目 | 内容 |
|------|------|
| **ファイル** | `env.example:20`, `infra/docker-compose.yml:67,124` |
| **状態** | env.example は `sqlite:///data/soms.db` だが、docker-compose は `postgresql+asyncpg://...` |
| **影響** | `cp env.example .env` してデプロイすると DB 接続失敗 |
| **対応** | env.example を PostgreSQL URL に更新、または両方サポートするドキュメント追加 |

---

### C-4: env.example に LLM_MODEL 変数が未定義

| 項目 | 内容 |
|------|------|
| **ファイル** | `env.example` (欠落), `infra/docker-compose.yml:31,106` |
| **影響** | brain / voice-service が空の `LLM_MODEL` で起動し、LLM API 呼び出しが失敗する可能性 |
| **対応** | env.example に `LLM_MODEL=qwen2.5:14b` を追加 |

---

## 2. HIGH — 早期対応推奨

### H-1: Occupancy Monitor のペイロードフィールド名不一致

| 項目 | 内容 |
|------|------|
| **送信側** | `services/perception/src/monitors/occupancy.py:42` → `"count": count` |
| **受信側** | `services/brain/src/world_model/world_model.py:157` → `"person_count" in payload` |
| **影響** | カメラからの人数検出データが WorldModel に取り込まれず、vision_count が常に 0 |
| **対応** | occupancy.py のフィールド名を `person_count` に変更、または WorldModel 側で `count` もフォールバック |

---

### H-2: Perception → Brain MQTT トピック形式不一致

| 項目 | 内容 |
|------|------|
| **送信側** | Perception monitors → `office/{zone}/activity`, `office/{zone}/occupancy` (3パート) |
| **受信側** | WorldModel topic parser → `office/{zone}/{device_type}/{device_id}/{channel}` (5パート想定) |
| **影響** | Perception からのトピックが WorldModel のパーサーで正しくルーティングされない |
| **対応** | Perception 側のトピックを 5パート形式に統一、または WorldModel パーサーに短縮トピック対応を追加 |

---

### H-3: DashboardClient の voice 生成失敗時の null チェック欠如

| 項目 | 内容 |
|------|------|
| **ファイル** | `services/brain/src/dashboard_client.py:19-29` |
| **影響** | voice サービスがダウン時、タスク作成時に audio URL が None になり、フロントエンドの音声再生でエラー |
| **対応** | voice 生成失敗時のフォールバック処理を追加 |

---

### H-4: MCPBridge の request_id マッチングが脆弱

| 項目 | 内容 |
|------|------|
| **ファイル** | `services/brain/src/mcp_bridge.py:49-60` |
| **影響** | レスポンスの request_id をトピックから抽出後にペイロードで上書きするロジックが脆弱。誤マッチの可能性 |
| **対応** | ペイロードの `id` フィールドを正として使い、トピック抽出はフォールバックに |

---

### H-5: Sanitizer のレート制限タイミング不正

| 項目 | 内容 |
|------|------|
| **ファイル** | `services/brain/src/sanitizer.py:52-62` |
| **影響** | バリデーション失敗したタスクもレートリミットにカウントされ、有効な作成枠が浪費される |
| **対応** | タイムスタンプ記録をバリデーション成功後に移動 |

---

### H-6: フロントエンド — setState in useEffect (React アンチパターン)

| 項目 | 内容 |
|------|------|
| **ファイル① (CRITICAL)** | `App.tsx:88` — `setInitialLoadDone(true)` が Effect 本体で直接呼ばれ、カスケードレンダリング発生 |
| **ファイル② (HIGH)** | `WalletBadge.tsx:13` — 条件分岐内の `setBalance(null)` |
| **影響** | 初回ロード時に不要な再レンダリング。パフォーマンス劣化とレース条件の潜在リスク |
| **対応** | useRef で初期化フラグを管理、または useEffect の構造をリファクタ |

---

### H-7: App.tsx useEffect の依存配列に prevTaskIds 欠落

| 項目 | 内容 |
|------|------|
| **ファイル** | `services/dashboard/frontend/src/App.tsx:104` |
| **影響** | `prevTaskIds` のクロージャが古い値を保持し、新規タスクの検出が漏れる可能性 |
| **対応** | 依存配列に `prevTaskIds` を追加 |

---

### H-8: tsconfig.app.tsbuildinfo が .gitignore に未登録

| 項目 | 内容 |
|------|------|
| **ファイル** | `services/dashboard/frontend/tsconfig.app.tsbuildinfo` (untracked) |
| **影響** | ビルドアーティファクトが誤ってコミットされる可能性 |
| **対応** | `.gitignore` に `*.tsbuildinfo` を追加 |

---

## 3. MEDIUM — 改善推奨

### M-1: PostgreSQL ポートが全インターフェースに公開

| 項目 | 内容 |
|------|------|
| **ファイル** | `infra/docker-compose.yml:48` → `"5432:5432"` |
| **リスク** | ネットワーク上の誰でもデフォルトパスワード (`soms_dev_password`) で接続可能 |
| **対応** | `"127.0.0.1:5432:5432"` に制限 |

---

### M-2: MQTT の匿名アクセスが有効

| 項目 | 内容 |
|------|------|
| **ファイル** | `infra/mosquitto/mosquitto.conf:5` → `allow_anonymous true` |
| **リスク** | 開発環境では問題ないが、本番ではセキュリティリスク |
| **対応** | 本番デプロイ時に認証を有効化 |

---

### M-3: RejectionStock のレースコンディション

| 項目 | 内容 |
|------|------|
| **ファイル** | `services/voice/src/rejection_stock.py:91-105` |
| **影響** | `get_random()` で pop 後・save 前にクラッシュするとエントリが失われるか重複する |
| **対応** | ロック内でマニフェスト保存、またはアトミック操作を使用 |

---

### M-4: Voice Service の LLM 呼び出しにタイムアウト未設定

| 項目 | 内容 |
|------|------|
| **ファイル** | `services/voice/src/speech_generator.py:223-228` |
| **影響** | LLM が遅い場合、voice リクエストが無期限にハングする可能性 |
| **対応** | aiohttp セッションに明示的タイムアウトを設定 |

---

### M-5: Perception の network_mode: host とカスタムネットワークの競合

| 項目 | 内容 |
|------|------|
| **ファイル** | `infra/docker-compose.yml:165` |
| **影響** | `network_mode: host` はカスタムネットワークを無視するため、サービスディスカバリに影響 |
| **対応** | host モード使用時はネットワーク定義を除外 |

---

### M-6: パッケージバージョンの不整合

| パッケージ | brain | voice | dashboard | wallet |
|-----------|-------|-------|-----------|--------|
| aiohttp | 3.9.1 | 3.11.0 | — | — |
| pydantic | 2.5.2 | 2.10.0 | 2.5.2 | 2.5.2 |
| paho-mqtt | >=2.0.0 | — | — | >=2.0.0 |

**対応**: 特に pydantic は voice だけ 2.10.0 で乖離。統一を推奨。

---

### M-7: Voice Service の Task モデルが簡素すぎる

| 項目 | 内容 |
|------|------|
| **ファイル** | `services/voice/src/models.py:4-11` |
| **影響** | `bounty_xp`, `task_type`, `expires_at` 等のフィールドが未定義。将来の拡張で破綻する可能性 |
| **対応** | Dashboard backend の Task スキーマと整合性を取る |

---

### M-8: docker-compose の未使用ボリューム

| 項目 | 内容 |
|------|------|
| **ファイル** | `infra/docker-compose.yml:182` → `soms_db_data:` |
| **影響** | SQLite 時代の残骸。混乱の原因 |
| **対応** | 削除 |

---

### M-9: Wallet サービスのポート不要公開

| 項目 | 内容 |
|------|------|
| **ファイル** | `infra/docker-compose.yml:119` → `"8003:8000"` |
| **影響** | nginx 経由でのみアクセスされるため、直接ポート公開は不要 |
| **対応** | ports 定義を削除 |

---

### M-10: frontend の Dockerfile に .dockerignore がない

| 項目 | 内容 |
|------|------|
| **ファイル** | `services/dashboard/frontend/Dockerfile` |
| **影響** | `COPY . .` でローカルの node_modules がコピーされ、イメージ肥大化 |
| **対応** | `.dockerignore` を作成 (`node_modules/`, `dist/`, `*.tsbuildinfo`) |

---

### M-11: docker-compose.edge-mock.yml にネットワーク定義が欠落

| 項目 | 内容 |
|------|------|
| **ファイル** | `infra/docker-compose.edge-mock.yml` |
| **影響** | `soms-net` を参照しているがネットワーク定義がなく、暗黙のデフォルトネットワークが使われる |
| **対応** | `networks: soms-net:` セクションを追加 |

---

### M-12: env.example に POSTGRES_USER/PASSWORD が未定義

| 項目 | 内容 |
|------|------|
| **ファイル** | `env.example` |
| **影響** | docker-compose.yml でデフォルト値 (`soms`/`soms_dev_password`) を使うが、明示されていない |
| **対応** | env.example にコメント付きで追加 |

---

## 4. LOW — 余裕があれば対応

### L-1: Perception Dockerfile の `rocm/pytorch:latest` タグ

浮動タグによりビルド再現性なし。バージョンピン推奨。

### L-2: 複数 Dockerfile で不要な build-essential

brain, backend, wallet の Dockerfile で `build-essential` をインストールしているが、純 Python サービスには不要。イメージサイズ +90MB。

### L-3: package.json に未使用の axios

全 API 呼び出しが `fetch()` で実装済み。`axios` は削除可能。

### L-4: 音声のサンプルレート計算がハードコード

`services/voice/src/main.py` の複数箇所で `len(audio_data) / (24000 * 2)` がハードコード。定数化推奨。

### L-5: test_discovery.py にハードコード IP

`services/perception/test_discovery.py:139` に `192.168.128.74` がハードコード。環境依存。

### L-6: タスクルーターの JSON パースエラーハンドリングが広すぎる

`services/dashboard/backend/routers/tasks.py:52-55` で `Exception` を丸呑み。`json.JSONDecodeError` に限定すべき。

### L-7: Docker サービスにヘルスチェック未定義

全 10 サービスに healthcheck がない。障害検知が困難。

### L-8: virtual_camera Dockerfile のビルドが不明確

`video.mp4` が COPY コメントアウトされており、テストパターン生成の実装が不明。

---

## 5. 対応優先度まとめ

### フェーズ 1: コミット前 (ブロッカー解消)

| ID | タスク | 工数目安 |
|----|--------|----------|
| C-1 | App.tsx の merge conflict 解決 (`git add`) | 1分 |
| C-2 | Task モデルに assigned_to / accepted_at 追加 | 5分 |
| C-3 | env.example の DATABASE_URL 更新 | 2分 |
| C-4 | env.example に LLM_MODEL 追加 | 1分 |
| H-8 | .gitignore に *.tsbuildinfo 追加 | 1分 |

### フェーズ 2: 機能修正 (データフロー正常化)

| ID | タスク | 工数目安 |
|----|--------|----------|
| H-1 | Occupancy ペイロードのフィールド名修正 | 5分 |
| H-2 | Perception MQTT トピック形式の統一 | 15分 |
| H-3 | DashboardClient voice null チェック | 5分 |
| H-4 | MCPBridge request_id ロジック修正 | 10分 |
| H-5 | Sanitizer レート制限タイミング修正 | 5分 |

### フェーズ 3: フロントエンド品質向上

| ID | タスク | 工数目安 |
|----|--------|----------|
| H-6 | useEffect 内の setState リファクタ | 15分 |
| H-7 | useEffect 依存配列の修正 | 5分 |

### フェーズ 4: インフラ・セキュリティ改善

| ID | タスク | 工数目安 |
|----|--------|----------|
| M-1 | PostgreSQL ポート制限 | 1分 |
| M-5 | Perception network_mode 整理 | 5分 |
| M-6 | パッケージバージョン統一 | 10分 |
| M-8〜12 | docker-compose クリーンアップ | 10分 |

---

**総計**: CRITICAL 4件 / HIGH 8件 / MEDIUM 12件 / LOW 8件 = **32件**
