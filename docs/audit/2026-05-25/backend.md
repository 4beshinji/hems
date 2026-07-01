# 監査: backend — 2026-05-25

## スコープ
- 対象 path(`services/backend/`):
  `main.py`(174)・`models.py`(357, 23 ORM モデル)・`database.py`・`schemas.py`(761)・
  `auth.py`(81)・`hmac_util.py`(32)・`routers/`(28 ルーター, ~5,100 LOC)
- entry point: `main.py`(FastAPI app + lifespan + router 登録)
- **監査深度**: core(main/models/auth/hmac)は精読、chat/shopping/tasks/devices/mobile の主張は grep 検証、
  残り 23 ルーターは構造スキャン(bare except / raw SQL / session)止まり。行レベル全精査は後続。
- 参照 canonical doc: `services/backend/CLAUDE.md`、`docs/IMPLEMENTATION_MAP.md` §8

## doc 乖離(本パスで修正適用済)

| # | doc claim | code reality (file:line) | 修正先 doc | 状態 |
|---|---|---|---|---|
| 1 | §8 が `/api/notes/tags`・`/api/perception/cameras`・`/api/perception/vlm/status`・`/api/knowledge/recent` を「✗ ツール化されていない」と記載 | unit 4 で判明の 4 ツールが実際に叩く: `list_note_tags`(external:73)・`list_cameras`(perception:138)・`get_vlm_status`(perception:153)・`get_recent_knowledge_changes`(external:298) | IMPLEMENTATION_MAP §8 | ✅ ✓ + tool 名に修正 |
| 2 | backend/CLAUDE.md「World model: `ShoppingState` in Digital Space (due items, pending count)」 | unit 2 と同根: world_model 上 ShoppingState は **未populate**。backend DB が SoT | services/backend/CLAUDE.md Shopping 節 | ✅ 修正 |

検証 OK(乖離なし):
- backend/CLAUDE.md chat 主張「sliding window 20 / auto-TTS <100字」→ `routers/chat.py:27-28,89`(SLIDING_WINDOW=20 / TTS_MAX_LENGTH=100)と一致。
- Device Registry の Safety 主張(pulse ≤600s / brightness 0-255 / color_temp 153-500)→ sanitizer(unit 1)と一致。

未修正(SUMMARY 向け finding):
- root `CLAUDE.md` の "Database" 節が backend モデルを 6 件(Task/User/VoiceEvent/SystemStats/ShoppingItem/PurchaseHistory)のみ列挙だが、実際は **23 モデル**(Device/Scene/AutomationRule/Conversation/Message/MobileDevice/VoiceCapsule/BridgeStatusLog/DeviceActionLog/...)。高レベル overview のため SUMMARY で要否判断。

## 命名所見(refactor-ready)

| 優先度 | current → proposed | file:line | 理由 |
|---|---|---|---|
| P2 | ~~`verify_api_key` → `lan_trusted_noop`(または明示 deprecate)~~ → **実装済み** | auth.py:38 | 元の no-op 状態は解消。`verify_api_key` は `Authorization: Bearer <BACKEND_API_KEY>` を検証するよう実装済み |

## スコープ所見(refactor-ready)

| 優先度 | 問題 | file:line | 推奨 |
|---|---|---|---|
| P1(security) | ~~`verify_api_key` が `return None` の **no-op**~~ → **実装済み**。`auth.py:38` で `Authorization: Bearer <BACKEND_API_KEY>` を検証。mobile ルートは `verify_mobile_device` で実認証済(問題なし) | auth.py:38 / main.py:257 (`_require_api_key`) | — |
| P2 | lifespan で手製 `ALTER TABLE ADD COLUMN` マイグレーション(voice_events/tasks/shopping_items/devices)。全例外 `except Exception: pass` で握り潰し、versioning 無し・型変更/削除不可 | main.py:27-78 | Alembic 等の migration framework 導入 |
| P2 | ~~`routers/chat.py` のみ raw `text()` SQL を使用(他は ORM)~~ → **実装済み**。`routers/chat.py:5` に「All DB access goes through the SQLAlchemy ORM (no raw `text()` SQL)」と明記 | routers/chat.py | — |

## 可読性所見(refactor-ready)

| 優先度 | 問題 | file:line | 推奨 |
|---|---|---|---|
| P2 | 23 ルーターで `except Exception` が散在(HTTP ハンドラとして許容範囲だが、エラー詳細を握り潰す箇所あり) | routers/*.py | 例外種別の絞り込み + ログ |
| P2 | `import models` の関数内ローカル import(循環回避)が複数箇所 | auth.py:62 ほか | 構造見直しで module-level 化の余地 |

## 後続リファクタ推奨(優先度順サマリ)

- **P1(security)**: `verify_api_key` no-op の扱いを明確化。LAN-trusted を正式 doc 化するか、実認証を導入。`_auth` 装飾の誤認を解消。
- **P2**:
  - 手製 ALTER TABLE マイグレーションを Alembic へ。例外握り潰しを排除。
  - chat.py の raw SQL を ORM 化。
  - root CLAUDE.md の Database モデル列挙を補完(SUMMARY)。
- **P0**: 挙動ブロッカー無し。models / auth(mobile)/ hmac は堅牢。

## 確認できた canonical の正確性(乖離なし)
- backend/CLAUDE.md の Device Registry / Shopping(MQTT topic)/ Chat(window 20・TTS 100字)主張は実装一致。
- HMAC(`hmac_util.py`)は `compare_digest` でタイミング攻撃耐性あり、mobile device key は SHA-256 hash 保存で適切。
