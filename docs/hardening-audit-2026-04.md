# HEMS 実運用ハーデニング監査 — 2026-04-17

> **HISTORICAL / SUPERSEDED** — 本監査は 2026-04-17 のスナップショットです。P0/P1 は [`../refactor/2026-06-11/PLAN.md`](../refactor/2026-06-11/PLAN.md) Wave 1 で実装済み。最新の監査・計画は [`../audit/2026-06-11/SUMMARY.md`](../audit/2026-06-11/SUMMARY.md) / [`../refactor/2026-06-11/`](../refactor/2026-06-11/) を参照してください。
>
> **注**: 既存の `SECURITY_AUDIT.md` (2026-03-07) は `openclaw-bridge` / MQTT ACL 等、
> その後の構成変更で陳腐化した記述を含む。本書はそれ以後の現状を基にした再監査。

## Context

HEMS は `BACKEND_API_KEY` / `HEMS_INTERNAL_TOKEN` による内部認証を再導入済み。
実運用投入 (常時稼働 + 将来の外出先参照 + 複数ブリッジ統合) に向けて、
backend/frontend / brain+bridges / infra+ops の 3 領域を並列監査し、
重要 claim は一次ソースで検証した。

本書は**監査結果 + 優先度付き修正ロードマップ**。修正着手は別途計画する。

> **進捗(2026-06-11 付記)**: P0 群(MQTT 認証/ACL、port 127.0.0.1 バインド、シークレット排除)および backend shared-key 認証(BACKEND_API_KEY、commit `e5de771` + 全配線 `3636e18`)は実装済み。残存する P1 群(brain chat server 認証・webhook replay 防御・control params 検証・rate limit・CSP)は `docs/refactor/2026-06-11/PLAN.md` Wave 1 で追跡。最新の検証結果は `docs/audit/2026-06-11/SUMMARY.md` §2。

---

## 検証サマリ (一次ソース確認済み)

| 主張 | 一次ソース | 判定 |
|---|---|---|
| MQTT 匿名許可 | `infra/mosquitto/mosquitto.conf:5` `allow_anonymous true` | **CONFIRMED** |
| backend `verify_api_key` は no-op | `services/backend/auth.py:30-31` | CONFIRMED (LAN-trusted 前提で意図的) |
| STT `_check_auth` は no-op | `services/stt/src/main.py:54` | **CONFIRMED** (ドキュメント無し) |
| Knowledge bridge が pickle 使用 | `services/knowledge-bridge/src/embedding.py:176,190` | **CONFIRMED** |
| Biometric webhook HMAC あり/replay 防御なし | `services/biometric-bridge/src/main.py:58-85` | CONFIRMED (timestamp/nonce なし) |
| Mobile HMAC 実装 | `services/backend/hmac_util.py` | CONFIRMED (compare_digest 使用、replay 防御なし) |
| CORS 制限あり | `services/backend/main.py:88-97` | CONFIRMED (whitelist、OK) |
| ALTER TABLE f-string | `services/backend/main.py:33,52,62,73` | CONFIRMED (値はハードコード → SQL injection ではなく**マイグレーション戦略の不都合**) |

---

## 優先度別の修正ロードマップ

### P0 — 実運用投入前に**必須**

#### P0-1. MQTT 認証/ACL を有効化 [CRITICAL]
- **箇所**: `infra/mosquitto/mosquitto.conf`
- **問題**: `allow_anonymous true` により LAN 内の任意プロセスが (a) 全センサーデータを購読 (b) `hems/brain/reload-character` や `hems/tapo/*` 等に publish してデバイス制御を強制起動できる。`hems/personal/biometrics/*` は健康データ直読み。
- **修正**:
  - `allow_anonymous false` + `password_file` + `acl_file`
  - ブリッジごとの最小権限 (brain: read `office/#` + `hems/#`, write `hems/brain/*`; biometric-bridge: write `hems/personal/biometrics/#` のみ、など)
  - docker-compose の env に各サービスの credentials を注入
- **参考**: `tests/security/poc_mqtt_acl.sh` が既存

#### P0-2. Knowledge bridge の pickle 廃止 [HIGH]
- **箇所**: `services/knowledge-bridge/src/embedding.py:176,190`
- **問題**: embedding cache を pickle でロード。キャッシュファイルに書き込めれば任意コード実行。`hems_knowledge_data` volume に置かれており、別コンテナの compromise から RCE への足掛かりになる。
- **修正**: `json` または `msgpack` に置換。embedding vector は `np.save` + メタデータ JSON が典型的。

#### P0-3. Backend 以外の内部サービスポートを 0.0.0.0 → 127.0.0.1 に制限 [HIGH]
- **箇所**: `infra/docker-compose.yml` の `ports:` 全体
- **問題**: `voice-service:8012`, `biometric-bridge:8017`, `stt:8023`, `knowledge-bridge:8022`, `obsidian-bridge:8014`, `gas-bridge:8015`, `perception:8018`, `localcraw-bridge:8013` 等、brain/backend 以外からは Docker 内部ネットワーク経由のみで充分なサービスが全部 LAN 露出。
- **修正**: `"127.0.0.1:${HEMS_PORT_X}:PORT"` 形式に統一。外部公開は nginx(8080) と backend(8010) のみ。
- 既に OK: mosquitto (`MQTT_BIND_ADDR` デフォ 127.0.0.1), postgres (127.0.0.1:5442)

#### P0-4. STT / voice-service の `_check_auth` no-op を塞ぐ [HIGH]
- **箇所**: `services/stt/src/main.py:54`, `services/voice/src/main.py` (要確認)
- **問題**: `verify_api_key` と違い no-op であることが文書化されていない。P0-3 完了で外部攻撃は閉塞されるが、別ブリッジが compromise された場合に到達可能。
- **修正**: 内部間通信用 shared secret (`HEMS_INTERNAL_TOKEN`) を `_check_auth` で検証。

#### P0-5. PostgreSQL 空パスワードを fail-fast 化 [MEDIUM]
- **箇所**: `infra/docker-compose.yml` postgres service
- **問題**: `POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-}` で未設定だと空文字列パスワードで起動。
- **修正**: `${POSTGRES_PASSWORD:?POSTGRES_PASSWORD required}` に変更。

#### P0-6. HA/Matter privileged+host-network 運用注記 [MEDIUM]
- **箇所**: `infra/docker-compose.yml:301-310,313-323`
- **問題**: `privileged: true` + `network_mode: host` + `/run/dbus` マウント。Matter-Server 脆弱性 → ホスト侵害直結。
- **修正**: HA 要件で回避困難 → (a) `docs/ha-isolation.md` で「HA は VLAN/別ホスト推奨」を明記、(b) `ha` profile をデフォルト off、(c) HA を使わない構成への移行パス併記。

---

### P1 — 初期運用で早期投入

#### P1-1. Webhook replay 防御 (biometric + mobile)
- **箇所**: `services/biometric-bridge/src/main.py:58-85`, `services/backend/hmac_util.py` + `routers/mobile.py`
- **問題**: HMAC 検証はあるが timestamp/nonce なし。キャプチャしたペイロードは永続に有効 (例: `{"bpm":180}` を保存しておいて任意タイミングで投げて高心拍アラート捏造)。
- **修正**:
  - `X-HEMS-Timestamp` 必須化、±300 秒スキュー許容
  - HMAC 入力に timestamp を含める: `hmac(secret, timestamp + "\n" + body)`
  - (任意) `X-HEMS-Nonce` + SQLite の nonce cache で one-time 化

#### P1-2. Backend /devices/{id}/control の params 検証
- **箇所**: `services/backend/routers/devices.py` + `schemas.py` (DeviceControlRequest)
- **問題**: sanitizer で LLM 経路は守れているが、backend の HTTP 経路は `params: dict` を無検証で brain/bridge に流す。brightness 999999 や pulse duration 86400 が素通り可能。
- **修正**: backend 側で action × params の schema 検証 (brightness 0-255, color_temp 153-500, pulse 1-600s, delay_s 0-3600)。

#### P1-3. Persona rewriter 入力のサニタイズ
- **箇所**: `services/brain/src/persona_rewriter.py:54-89`
- **問題**: Stage 1 LLM 出力 (素のメッセージ) が Stage 2 prompt にそのまま埋まる。Stage 1 が `SYSTEM: ...` 等で汚染されたら Stage 2 が追従するリスク。
- **修正**: `sanitize_llm_text()` (500 字制限 + injection pattern 除去) を `message` 引数に適用してから prompt に混ぜる。

#### P1-4. Chat エンドポイントの rate limit
- **箇所**: `services/backend/routers/chat.py:31-111`
- **問題**: /chat/ が brain の ReAct loop を駆動 = LLM コスト/計算量消費。LAN 内マルウェアや誤操作スクリプトから DoS 可能。
- **修正**: slowapi 等で per-IP 10 req/min、同時進行 1 以下。

#### P1-5. Nginx TLS + HSTS + rate limit
- **箇所**: `services/frontend/nginx.conf`
- **問題**: 現在 80/tcp 平文。LAN 内で chat/biometric 平文通信。外部公開予定なら必須。
- **修正**: Let's Encrypt or Tailscale Funnel で TLS 終端、HSTS/CSP ヘッダ付与、`/api/mobile/register` に rate limit。

#### P1-6. Mobile HMAC secret ローテーション
- **箇所**: `services/backend/routers/mobile.py` + `auth.py`
- **問題**: secret 漏洩時のローテーション API なし。現状は device 削除 + 再登録 = 履歴ロス。
- **修正**: `POST /mobile/{device_id}/rotate-secret` (既存デバイスの hmac_secret のみ更新)。app 側は再 QR スキャンで受領。

---

### P2 — 中期ハーデニング

#### P2-1. Docker セキュリティオプション横断適用
- `infra/docker-compose.yml` に:
  ```yaml
  security_opt:
    - no-new-privileges:true
  cap_drop: [ALL]
  ```
  必要なものだけ `cap_add`。HA/Matter は例外扱いで docs に隔離指針を記載。

#### P2-2. Bridge Dockerfile の非 root 化統一
- 未対応 (要確認): `services/tapo-bridge/Dockerfile`, `services/switchbot-bridge/Dockerfile`, `services/biometric-bridge/Dockerfile`
- 既対応パターン (`services/backend/Dockerfile` 等) を踏襲して `USER appuser` を追加。

#### P2-3. event_store retention の階層化
- **箇所**: `services/brain/src/event_store/aggregator.py:28-29`
- **問題**: raw_events 730 日は生体データも含む。PII 長期保管は GDPR 的に過剰。
- **修正**: カテゴリ別リテンション (biometrics: 90d, llm_decisions: 180d, sensor raw: 365d, aggregates: 730d)。`event_type` カラムで分岐。

#### P2-4. ALTER TABLE 自動マイグレーションを Alembic 化
- **箇所**: `services/backend/main.py:30-76`
- **問題**: lifespan 内で try/except 丸呑みで ALTER TABLE 素通し。失敗が silent、ロールバック不可、列タイプ変更不能。
- **修正**: Alembic 導入、既存 try/except ブロック削除。

#### P2-5. MQTT reconnect + send_queue を全ブリッジに展開
- biometric-bridge は既に `SendQueue` で MQTT 不通時の SQLite キューあり。同じパターンを `localcraw-bridge`, `ha-bridge`, `switchbot-bridge`, `tapo-bridge` に適用。

#### P2-6. Frontend セキュリティヘッダ追加
- `services/frontend/nginx.conf` に CSP / Referrer-Policy / Permissions-Policy 追加:
  ```
  add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' ws: wss:" always;
  add_header Referrer-Policy "strict-origin-when-cross-origin" always;
  add_header Permissions-Policy "camera=(), microphone=(self), geolocation=()" always;
  ```

#### P2-7. Docker ネットワーク分離
- 現状: 全サービスが `hems-net` 1 本。
- 修正: `hems-core` (brain/backend/mqtt), `hems-bridges` (各ブリッジ + mqtt), `hems-public` (frontend + backend) で分離。

#### P2-8. run_pc_command allowlist のパスパターン絞り込み
- **箇所**: `services/brain/src/sanitizer.py:14-42`
- **問題**: `ls /path [-flags]` 系で `..` が `[\w./~-]` 文字クラスに含まれるため `ls ../../../etc` 相当が通る可能性。
- **修正**: 文字クラスから `..` を除外 + `\.\.` 明示拒否。`tests/security/poc_command_bypass.py` にテスト追加。

---

### P3 — 設計不都合 (セキュリティより設計負債)

#### P3-1. Router 内グローバル dict の async race
- **箇所**: `services/backend/routers/knowledge.py:10`, `perception.py:10`, `brain.py:21`, `pc.py:10`
- **問題**: `_knowledge_store.clear()` + `.update()` が asyncio.Lock なしで走る。同時リクエストで部分更新が見える。
- **修正**: `asyncio.Lock` で守るか、イミュータブル置換 (`_knowledge_store = new_dict`) に統一。

#### P3-2. Async 中の同期 I/O
- **箇所**: `services/backend/routers/chat.py:320-344` (TTS 合成で `subprocess.run` + `open()` を直接)
- **修正**: `await asyncio.to_thread(...)` に包む。

#### P3-3. TTS audio ディスク無制限肥大
- **箇所**: `services/backend/routers/chat.py:383-399`
- **問題**: 合成済み音声を `/app/audio` に保存しっぱなし。クリーンアップ無し。
- **修正**: N日 or N ファイル超過で古いものから削除するバックグラウンド job。

#### P3-4. LLM 呼び出しの timeout/リトライ不在
- **箇所**: `services/brain/src/llm_client.py`
- **問題**: Ollama inference ハング (VRAM swap 中など) で待ち続け、ReAct loop 全体が 30s interval を超えて累積。
- **修正**: httpx timeout (25s) + exponential backoff 2-3 回 + 最終的に rule-based fallback。

#### P3-5. 循環依存: backend → brain → backend
- **問題**: brain が task 作成で backend HTTP を叩き、backend が chat で brain HTTP を叩く。両方 busy 時にデッドロック様。
- **修正**: 非同期イベントは全て MQTT 経由に寄せて HTTP 相互呼び出しを減らす。

#### P3-6. Reactive automation path 未実装
- memory 記載: PIR → 照明 ON 即応の経路が `_process_mqtt → trigger_event` で繋がっていない。
- **既知の欠損**として P3 に残す。

#### P3-7. CHARACTER_FILE 環境変数での任意 YAML 読み出し
- **箇所**: `services/backend/routers/character.py:83-109`
- **問題**: `CHARACTER_FILE` env が設定されれば任意 YAML 読み出し可能。safe_load なのでコード実行は無いが、file existence oracle として機能。
- **修正**: 読み出し可能ディレクトリ (`/app/config/characters/`) のホワイトリスト。

---

## 既に OK な項目 (今回の audit で確認済)

- ✅ `yaml.safe_load` 採用 (`character_loader.py`)
- ✅ Obsidian `note_writer` は `resolve()` + `is_relative_to()` でトラバーサル防御
- ✅ Obsidian `write_note` は `HEMS/` 配下限定 + 10000 字制限
- ✅ Mobile device key は SHA-256 ハッシュ保管 (plaintext 保管ではない)
- ✅ CORS は明示的 origin リスト (ワイルドカード無し)
- ✅ Frontend に `dangerouslySetInnerHTML` / `innerHTML` 使用なし
- ✅ biometric-bridge / mobile に HMAC 検証 (replay 防御以外は OK)
- ✅ PostgreSQL/mosquitto/ollama の listener は 127.0.0.1 デフォ
- ✅ CI で pip-audit + hadolint 自動実行
- ✅ Git 履歴に秘密鍵混入なし

---

## 修正対象の主要ファイル (P0 のみ)

| Priority | ファイル | 変更種別 |
|---|---|---|
| P0-1 | `infra/mosquitto/mosquitto.conf` | 設定 |
| P0-1 | `infra/mosquitto/passwords.txt` + `acl.txt` | 新規 |
| P0-1 | `infra/docker-compose.yml` | 各サービスに MQTT 資格情報 env 注入 |
| P0-1 | `env.example` | `MQTT_USER_*` / `MQTT_PASSWORD_*` 追加 |
| P0-2 | `services/knowledge-bridge/src/embedding.py` | pickle → json/msgpack |
| P0-3 | `infra/docker-compose.yml` | 内部サービス port を 127.0.0.1 バインドへ |
| P0-4 | `services/stt/src/main.py` | `_check_auth` 実装 |
| P0-4 | `services/voice/src/main.py` | 同上 (要確認) |
| P0-5 | `infra/docker-compose.yml` | `POSTGRES_PASSWORD:?` 形式 |
| P0-6 | `docs/ha-isolation.md` (新規) + `README.md` | HA 運用警告 |

---

## 検証方法

1. **MQTT ACL**: `tests/security/poc_mqtt_acl.sh` が anonymous publish を拒否することを確認
2. **Knowledge pickle**: `knowledge-bridge` 再起動後、embedding cache が json で読み書きできることを確認
3. **内部ポート閉塞**: `nmap localhost` で `backend:8010` と `frontend:8080` のみ LISTEN、`stt:8023` 等は 127.0.0.1 バインドのみ
4. **STT auth**: `curl http://host:8023/api/stt/providers` が 401、`curl -H "Authorization: Bearer <token>"` が 200
5. **PoC suite**: `bash tests/security/run_all_pocs.sh` 全 PASS

---

## スコープ判断 (この監査の立ち位置)

本書は**実装プランではなく、棚卸し**。実装着手は P0 / P1 を別々にスコーピングして段階導入を想定。
特に P0-1 (MQTT ACL) は全ブリッジの config 変更が必要なため単発の大きな PR になる。
P0-3 (port bind) はホスト側運用環境で segmentation 方針が決まってからの方が変更の意図がブレにくい。
