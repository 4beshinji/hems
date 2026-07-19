# Android 生体・モバイル収集系 分割レビュー — 2026-07-18

対象リビジョン: `6310df0` (`main`)

Status as of 2026-07-19: P0 snapshot contractとP1.1 Backend storeは実装済み。Brain cycle snapshotは
`biometric_latest`だけを更新し、immutable historyは`biometric_observations`とinternal-token endpointに分離した。
P1.2a/bでbridge private ingest、durable inbox/outbox、lease/retry/dead-letter delivery workerまで実装した。
mobile/Android callerは未配線で、この監査のP0-1とclient durability/replay指摘は継続する。

対象コンポーネント:

- `services/mobile-android/` — HEMS Mobile Companion
- `apps/healthconnect-companion/` — 単機能 Health Connect Companion
- `services/backend/routers/mobile.py` / `routers/biometric.py`
- `services/biometric-bridge/`
- `services/brain/src/world_model/user_updates.py` / `dashboard_mappers.py`
- 関連する MQTT、DB、認証、運用ドキュメント

## 1. 結論

この領域は、今回の分割レビューの最初の対象として妥当である。2026-06-11 監査では Android が明示的にスコープ外であり、その後、二つの Android APK が同じ Health Connect 収集責務を別々に実装した。一方で、サーバー側まで含む実データパスには二つの契約破綻がある。

1. Mobile Backend が publish する `hems/personal/mobile/*` は Brain が購読するものの reducer がなく、状態・ルール・DBへ到達しない。
2. Brain が Backend `/biometric/snapshot` へ送る payload は nested object、Backend DB writer は flat scalar を期待しており、実 payload を永続化できない。

したがって「APK が存在する」「単体テストが通る」ことと「生体・モバイルデータが HEMS で利用できる」ことが一致していない。加えて replay 防御はサーバー側だけ実装され、二つの Android client は legacy HMAC のままである。

緊急のコード変更は本レビューでは行わない。最初に canonical 経路と payload contract を固定し、その contract を跨ぐ統合テストを追加してから修正すべきである。

## 2. 現在のデータ経路

### 2.1 単機能 Health Connect Companion

```text
Health Connect
  -> apps/healthconnect-companion/HealthConnectReader
  -> Room pending_readings
  -> HemsBridgeClient
  -> POST biometric-bridge /api/biometric/webhook
  -> GadgetbridgeProvider.process_webhook / DataProcessor
  -> hems/personal/biometrics/{provider}/{metric}
  -> Brain UserUpdatesMixin._update_biometric_state
  -> Brain world model / rules
  -> Brain dashboard snapshot
  -> Backend biometric_readings
```

bridge までの経路は実装されており、Room によるオフライン queue もある。ただし末尾の Brain -> Backend snapshot contract が破綻している。

### 2.2 HEMS Mobile Companion

```text
Health Connect / location / activity / battery
  -> services/mobile-android SensorBuffer (memory only)
  -> SyncRepository
  -> POST Backend /mobile/state/webhook
  -> hems/personal/mobile/{location,activity,biometrics,battery}
  -> Brain subscribes hems/#
  -> UserUpdatesMixin._update_personal ignores category "mobile"
  -> discarded
```

Backend は `MobileDevice.last_seen_at` だけを更新し、payload 自体は永続化しない。よって MQTT publish 成功が API response に出ても、HEMS の world model、ルール、biometric DB には反映されない。

## 3. Findings

### P0-1 — Mobile state MQTT は dead data path

**証拠**:

- `services/backend/routers/mobile.py:_publish_mobile_event()` は `hems/personal/mobile/<subtopic>` を publishする。
- `state_webhook()` は location / activity / biometrics / battery をこの helper に渡すが、DB には payload を保存せず `MobileDevice.last_seen_at` のみ更新する。
- Brain は `services/brain/src/brain_mqtt.py:_setup_mqtt()` で `hems/#` を購読する。
- `services/brain/src/world_model/mqtt_router.py:update_from_mqtt()` は `hems/personal/*` を `_update_personal()` へ渡す。
- `services/brain/src/world_model/user_updates.py:UserUpdatesMixin._update_personal()` が処理する category は `notes` / `knowledge` / `biometrics` のみで、`mobile` 分岐がない。

**影響**:

- 位置、活動、スマートフォン経由の生体情報、battery が正常受理されたように見えて全て捨てられる。
- `published_topics` は delivery / consumption を保証しないため、運用者は成功と誤認する。
- Mobile Companion の Health Connect 実装は現在の server path では利用不能である。

**必要な対応**:

- mobile topic の意味を先に決める。biometrics は後述の biometric canonical path に合流させ、location / activity / battery だけを mobile domain reducer に残すのが妥当。
- Backend publish -> Brain reducer -> state/DB の契約テストを追加する。

### P0-2 — Brain / Backend biometric snapshot schema が不一致

> **2026-07-18 実装済み (P0.2a/b)** — `BiometricSnapshotIn`でnested→flat化し、latest row updateへ変更。legacy flat payloadはwarning付きで互換受理する。

**修正前の証拠**:

- `services/brain/src/dashboard_mappers.py:map_biometric_payload()` は次の nested payload を作る。
  - `heart_rate: {bpm, zone, resting_bpm}`
  - `spo2: {percent}`
  - `sleep: {...}`
  - `activity: {...}`
  - `stress: {...}`
  - `fatigue: {...}`
- `services/backend/routers/biometric.py:update_biometric()` は `data.get("heart_rate")` 等をそのまま `Integer` / `Float` column に代入し、`sleep` / `activity` nested key 自体は読まない。
- `tests/test_dashboard_client_biometric.py` は nested producer payload だけを mock session に対して検証する。
- `tests/test_backend_biometric_router.py` と `tests/integration/test_dataflow.py` は flat scalar payload を直接 Backend に送り、実 producer を通さない。

**影響**:

- 実際の heart rate / SpO2 がある snapshot は DB commit 時に型不一致になる。
- sleep / activity / stress / fatigue は key 名の不一致により欠落する。
- producer test と consumer test が個別に green でも接続契約は broken のままになる、典型的な seam mock 漏れである。

**必要な対応**:

- POST contract を Pydantic schema として一つに固定する。
- Backend は nested domain snapshot を明示的に flat DB record へ map するか、Brain mapper を DB input schema に合わせる。Frontend 向け world-model shape と DB write DTO を混用しない。
- 実 `map_biometric_payload()` の返値を実 Backend route に投入する contract test を追加する。

### P1-1 — Health Connect 収集 APK が二重実装

**重複**:

| 責務 | `services/mobile-android` | `apps/healthconnect-companion` |
|---|---|---|
| Health Connect read | `HealthConnectWorker` | `HealthConnectReader` |
| 周期実行 | `SyncScheduler` / WorkManager | `DataSyncWorker` / WorkManager |
| HMAC HTTP | `HmacSigning` / `SyncRepository` | `HemsBridgeClient` |
| 生体 DTO | `MobileBiometrics` | ad-hoc `JSONObject` |
| local threshold | `BiometricEvaluator` | なし |
| offline queue | memory `SensorBuffer` | Room `pending_readings` |

二つは単なる「汎用 app と補助 app」ではなく、心拍・歩数・睡眠の読み取りと定期送信を重複所有している。しかも送信先と schema が異なるため、両方を同一端末で稼働させると同じ観測が二経路から入りうる。

biometric-bridge の `DataProcessor.is_duplicate()` は同値を短時間だけ抑止する in-memory dedup であり、Mobile Backend path はそこを通らない。プロセス再起動、window 超過、部分的に値が違う payload を含む二重投入に対する一意性保証にはならない。

### P1-2 — Replay 防御は client 未実装で strict 化不能

**証拠**:

- Backend と biometric-bridge は `X-Timestamp` / `X-Nonce` を含む HMAC を検証できる。
- `services/mobile-android/.../HmacSigning.kt` は body-only HMAC だけを生成し、`BackendApi.submitState()` に timestamp / nonce header がない。
- `apps/healthconnect-companion/.../HemsBridgeClient.kt` も body-only HMAC だけを送る。
- `env.example` と `docs/smartband-setup.md` はこのため `WEBHOOK_REPLAY_STRICT=false` 維持を指示する。

`docs/audit/2026-06-11/SUMMARY.md` の「webhook replay 防御は実装済み」は server capability だけを指しており、end-to-end の防御としては未完了である。W1.3 の受け入れ条件に client 更新を含めた計画記述とも不整合がある。

### P1-3 — Mobile Companion は offline retry 時にデータを失う

**証拠**:

- `SensorBatchWorker.doWork()` は送信前に `SensorBuffer.drainLatest()` を呼ぶ。
- `drainLatest()` は deque から `pollLast()` し、battery も null に戻す。
- HTTP/network failure 後に `Result.retry()` を返しても payload を buffer に戻さず、worker input data にも保持しない。
- `SyncRepository` のコメントは WorkManager が retry を所有すると説明し、`SensorBuffer` のコメントは VPN-down 時にも bounded buffer が守ると説明するが、実装はその契約を満たさない。

単機能 companion の Room queue は「保存してから送る」ため、この点ではこちらが正しい。統合時に Room queue を Mobile Companion へ移植すべきである。

### P1-4 — Mobile Health Connect は permission / lifecycle 配線不足で silent no-op

**証拠**:

- `HealthConnectWorker` は granted permission set が空なら `Result.success()` で終了する。
- Mobile Companion の `SetupScreen` は location / background location / activity recognition / notification permission だけを要求し、Health Connect permission contract を起動しない。
- `SyncForegroundService` は location permission がなければ scheduler 起動前に停止する。`enqueueHealthConnect()` もこの location foreground service の起動後にだけ呼ばれる。

したがって Health Connect 同期は、無関係な location permission に結合され、さらに Health Connect permission を取得する UI がない。通常利用で silent no-op になりうる。

### P1-5 — 30秒 snapshot を履歴 DB に insert する設計が重複記録を生む

`Brain._push_all_snapshots()` は cognitive cycle の複数の終了経路から呼ばれ、`BIOMETRIC_ENABLED` 時に現在の world model を Backend へ送る。Backend `/biometric/snapshot` は update/upsert ではなく毎回 `BiometricReading` を insert する。

入力 event がない cycle でも同じ現在値を履歴 row として再登録するため、契約修正後は「観測履歴」ではなく「Brain cycle snapshot 履歴」になる。90日 retention は無制限増加を防ぐだけで、同一観測の二重・多重計上を防がない。

必要なのは source event timestamp / provider / external record id を持つ observation table か、少なくとも変化時のみ insert する dedup/upsert である。現在の `recorded_at=DB insert time` だけでは観測の同一性を表せない。

### P2-1 — ドキュメント鮮度が低い

`services/mobile-android/README.md` の主な誤記:

- MQTT 直接通信を記載するが、Android project に MQTT client dependency / publish 実装はない。
- `office/mobile/{device_id}/*` を記載するが、実装は Backend が `hems/personal/mobile/*` を publish する。
- voice input、shopping、task control、`/chat/mobile` を担当するとするが、現行 `BackendApi` は state webhook と voice-capsule download/ack のみ。
- `BACKEND_API_KEY` shared key 認証とするが、実装は QR 登録で得る per-device Bearer key + HMAC。
- `.env` から Android runtime 設定を読む説明だが、実装は QR payload / DataStore である。

`apps/healthconnect-companion/README.md` の主な誤記:

- Jetpack Compose と記載するが、実装は AppCompat + XML + ViewBinding。
- webhook を `/devices/heartbeat`、header を `X-Signature` と記載するが、実装は `/api/biometric/webhook` と `X-HEMS-Signature`。
- 体温・血圧を読むと記載するが、reader は SpO2 / calories / resting HR / HRV を含む一方、体温・血圧は読まない。
- 「同期済みタイムスタンプを保存」とするが、実装の重複防止は timestamp watermark ではなく、毎回 aggregate snapshot を Room queue に追加する方式である。
- `services/biometric-bridge/CLAUDE.md` へのリンクがあるが、そのファイルは存在しない。

root `CLAUDE.md` は両 Android project を「位置づけ未文書化」とする一方、各 README と `IMPLEMENTATION_MAP.md` には位置づけがある。`docs/distribution.md` は Mobile Companion を scaffold / app 未完成、`IMPLEMENTATION_MAP.md` は ALIVE とし、完成度表現も統一されていない。

### P2-2 — Android は CI と自動テストの外にある

- 両 project に `src/test` / `src/androidTest` がない。
- root CI / Makefile に Gradle build/test gate がない。
- Python tests は Android client の HMAC header、payload schema、offline queue を検証できない。

今回の `./gradlew test assembleDebug` 実行結果は本監査末尾に記録する。ビルド成功だけでは実機 Health Connect、background execution、permission flow、cleartext LAN 通信を保証しないため、最低でも JVM unit test と contract fixture が必要である。

### P2-3 — 技術選定・Coding Agent 由来と推定される負債

次の点は、必要性から導かれた境界というより、個別 feature slice をその都度完結させた結果に見える。

- 同一 repository 内に Health Connect reader / worker / signer を再実装し、既存 app の廃止・統合判断をしなかった。
- 2026年の client code と server contract の間に機械可読 schema / generated client / shared JSON fixture がなく、Kotlin DTO と Python Pydantic が手同期。
- producer test は mocked HTTP、consumer test は手書き flat JSON で、境界を跨ぐ一件の contract test がない。
- `0097d96` は mobile/backend/brain/frontend 等 134 files、13,602 insertions の巨大 feature commit で、責務別の動作確認と review が困難。
- コメントが「retry」「offline resilient」「5分 cadence」等の設計意図を宣言する一方、実装は drain-before-send、15分周期であり、aspirational comment が実態確認を代替している。

これは DDD を導入すべきという話ではない。むしろこの単一居住者向けシステムでは、`MobileObservation` と `BiometricObservation` の二つの wire contract、canonical topic、所有 service を小さく固定する方が適切である。

## 4. 推奨 canonical architecture

### 4.1 所有権

- **Android app の正本**: `services/mobile-android` を長期の単一 app とする。QR device credential、location/activity、voice capsule が既にあるため。
- **単機能 app**: `apps/healthconnect-companion` は移行期間だけ維持し、Mobile Companion が Room queue・permission UI・rich metrics を取り込んだ後に archive または削除する。
- **外部 mobile ingress**: Backend `/mobile/state/webhook` を正本とする。per-device revoke と QR onboarding を再利用できる。
- **biometric normalization**: biometric-bridge `DataProcessor` を正本とし、canonical MQTT は `hems/personal/biometrics/{provider}/{metric}` のまま維持する。
- **persistent source of truth**: Backend `biometric_observations`がimmutable canonical history、`biometric_latest`がcycle projection。`biometric_readings`はlegacy history互換として保持する。

### 4.2 推奨経路

```text
services/mobile-android
  -> durable Room outbox
  -> Backend /mobile/state/webhook (device Bearer + replay-safe HMAC)
     -> location/activity/battery: mobile reducer + 必要な永続化
     -> biometrics: internal authenticated biometric-bridge ingest
        -> DataProcessor
        -> canonical biometric MQTT
        -> Brain world model/rules
        -> Backend observation persistence (event/changed-only)
```

Backend で biometric topic 変換ロジックを再実装すると `DataProcessor` と責務が重複する。Backend -> biometric-bridge の private ingest、または normalization を独立した純粋関数 package に抽出して両者から利用する方がよい。

## 5. 修正順

1. **契約を固定**: biometric snapshot / mobile webhook の Pydantic schema、canonical topic、source timestamp、observation id を design note にする。
2. **P0-2 修正**: Brain mapper -> Backend route の end-to-end contract testを追加し、nested/flat mismatch を解消。
3. **P0-1 修正**: `hems/personal/mobile/*` の reducer/forwardingを実装し、publish成功だけでなく state反映を検証。
4. **client replay対応**: 両 Android signer に timestamp + cryptographic nonce を追加し、serverを strict にできる migration testを追加。
5. **Mobile outbox**: standalone app の Room queue patternを Mobile Companionへ移植。送信成功後だけ削除する。
6. **permission分離**: Health Connect permission UIとworker scheduleをlocation foreground serviceから分離。
7. **二重 app統合**: rich metric read、queue、手動sync/statusをMobile Companionへ移植し、単機能appをdeprecated化。
8. **DB semantics修正**: cognitive-cycle snapshotの無条件insertをevent/changed-only persistenceへ変更し、一意性制約またはdedup keyを追加。
9. **docs/CI同期**: README、canonical docs、Gradle test/build CIを更新。

P0-1 と P0-2 は独立して先に緊急修正できるが、場当たり的な topic alias や `dict` の文字列化ではなく、contract test を先に置くこと。

## 6. テストスコープ案

### Server contract

- Mobile webhook -> MQTT capture -> Brain reducer -> world model の一連テスト。
- `map_biometric_payload(world_model)` -> actual Backend `/biometric/snapshot` -> DB readback。
- source timestamp / observation id が同じ payload の再送で row が増えないこと。
- standalone + mobile の同一観測を投入した場合の dedup。

### Android JVM tests

- replay-safe HMAC の Python fixture との golden vector。
- `SensorBuffer` / Room outbox が network failure と process restart で保持されること。
- Health Connect record -> wire DTO mapping（心拍、歩数、睡眠、SpO2、HRV）。
- permission 未許可時に UI が actionable state を表示すること。

### 実機 tests

- Android 14 / 15 で background Health Connect read。
- VPN/LAN断 -> 再接続 -> exactly-once相当のflush。
- location permissionなしでもbiometric syncが動くこと。
- 片方のAPKだけでend-to-endにBrain contextとBackend historyへ反映されること。

## 7. 更新対象ドキュメント

実装修正時には少なくとも以下を同期する。

- `docs/IMPLEMENTATION_MAP.md`: mobile topic publisher/consumer、biometric snapshot schema、二つのAndroid appの移行状態。
- `services/backend/CLAUDE.md`: mobile authをreplay-safe protocolまで明記し、mobile dataの保存/転送責務を記載。
- `services/brain/CLAUDE.md`: `hems/personal/mobile/*` reducerとbiometric persistence path。
- `docs/CLAUDE-bridges.md`: Android ingressの正本とbiometric-bridge private ingest。
- `services/mobile-android/README.md`: 実装済み機能、QR/DataStore設定、実topic、非対応機能。
- `apps/healthconnect-companion/README.md`: AppCompat/XML、正しいendpoint/header/metric、deprecated予定。
- `CLAUDE.md`: 「位置づけ未文書化」を削除しcanonical/deprecatedを明記。
- `docs/distribution.md`: scaffold/未完成という表現を具体的な既知制約へ変更。
- `docs/audit/2026-06-11/SUMMARY.md`: replay防御を「server実装済み、client/strict移行未完」に訂正。
- `docs/refactor/2026-06-11/PLAN.md` / `LEDGER.md` / `META_REVIEW_REPORT.md`: W1.3のend-to-end未完とAndroidが当時scope外だったことを追記。
- `docs/smartband-setup.md`: strict=falseの暫定条件をclient移行完了後に更新。

## 8. 既存レビューとの重複回避

- 2026-06-11 SUMMARY は Android をスコープ外と明記しており、本レビューの中心所見は既存監査の再掲ではない。
- data-bridge placeholder は既知かつ2026-08以降の計画として文書化済みのため、初手対象にしなかった。
- biometric steps二重publishやbridge内dedupは既存 wiring-gap で扱われている。本レビューはその内側ではなく、二つのAndroid producer、Mobile Backend topic、Brain reducer、Backend DBまでの未監査 seamを対象にした。

## 9. 検証記録

- 指定された2026-06-11 audit/refactor文書6件を通読し、現在のcodeをspot verificationした。
- Python/Androidコード、README、canonical docs、MQTT routing、DB schema、既存testsを静的に追跡した。
- Android build/test:
  - 両 project で `./gradlew test assembleDebug` を開始した。
  - sandbox 内の初回実行は、既定 Gradle cache (`/home/sin/.gradle`) に lock file を作成できず、build configuration 前に失敗した。これは source/build failure ではなく実行環境の書込制約である。
  - `services/mobile-android` は権限付きで再実行し、Gradle 8.11.1 distribution の download 完了と daemon 起動までは確認した。長時間調査を区切る指示に従い、compile/test 完了前に打ち切ったため **build/test result は未確定**。
  - `apps/healthconnect-companion` は権限付き再実行を行っておらず **build/test result は未確定**。
  - 両 project とも `src/test` / `src/androidTest` および test dependency が存在しないため、仮に `test` task が成功しても domain / contract の自動検証にはならない。
- Python test は今回は実行していない。既存 tests の producer/consumer fixture と mock 境界を静的に確認した。
- ファイル編集は本監査文書の新規追加のみ。実装コードの変更・commitは行っていない。
