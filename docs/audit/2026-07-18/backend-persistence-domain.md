# Backend persistence / domain ownership 分割レビュー — 2026-07-18

対象リビジョン: `6310df0` (`main`)

Status as of 2026-07-19: biometric P0/P1.1でcycle latestを`biometric_latest`、canonical source historyを
`biometric_observations`、既存rowをlegacy `biometric_readings`に分離した。stable ID/source metadata/payload hashの
internal-token endpointは実装済みだが、mobile/bridge outboxとproducer配線は未実装である。

## 1. 対象と検証方法

対象:

- `services/backend/{models.py,database.py,schemas.py,main.py}`
- `services/backend/routers/` 全般。特に mobile / biometric / devices / timeseries / tasks / shopping / feedback / chat
- Brain の Backend HTTP caller: `dashboard_client.py` / `dashboard_transport.py` / `dashboard_mappers.py`、task・shopping・approval caller
- Bridge / Android から Backend または biometric-bridge に入る経路
- Backend DB、Brain event_store、MQTT mirror の所有権
- 関連 tests と `services/backend/CLAUDE.md` / `docs/IMPLEMENTATION_MAP.md` / `docs/db-improvement-plan.md`

検証方法:

- router ごとの DB mutation と MQTT publish を機械検索し、producer -> HTTP/MQTT contract -> consumer -> DB を静的追跡した。
- SQLAlchemy model の自然キー、unique constraint、JSON型、FK、retention対象を確認した。
- Brain mapper と Backend request schema / writer を対照した。
- producer test と consumer test が同じ wire payload を共有するか確認した。
- 既定 PostgreSQL と SQLite軽量モードのdialect差を確認した。
- コード変更、DB migration、commitは行っていない。

## 2. 所有権の現状

Backendは一枚岩の永続SoTではなく、実際には四種類の保存方式を混在させている。

| 種類 | 例 | 現在の保存先 | 問題 |
|---|---|---|---|
| CRUD SoT | Task, Device, ShoppingItem, Conversation | Backend DB | 概ね妥当だがidempotencyと自然キー不足 |
| latest projection | zones/weather/news/home/pc等 | router module-global dict | process-local、restart消失、stale判定なし |
| observation history | TimeSeriesPoint, BiometricObservation (`BiometricReading`はlegacy) | Backend DB | biometricはP1.1でcanonical history/latest分離済み。timeseriesのcycle snapshot混同は継続 |
| learning/audit event | feedback, trajectory, approval audit | Backend DB + MQTT + Brain event_store | 二重所有、dedupなし、未配線・JSON mutation問題 |

この違いをAPI名が表していない。`POST /.../snapshot` が単なるcache replacementの場合とhistory insertの場合があり、呼出側は同じ `DashboardTransport.post_snapshot()` を使う。

## 3. 現行データフロー

### 3.1 Sensor / domain projection

```text
Bridge/edge MQTT
 -> Brain world model (runtime SoT)
 -> cognitive cycle _push_all_snapshots()
 -> Backend /zones|weather|news|home|pc|.../snapshot
 -> module-global dict
 -> Frontend GET
```

Backendはこの領域ではSoTではなく、Brain projectionのprocess-local read modelである。

### 3.2 Time-series

```text
Brain current world-model snapshot
 -> map_zone_timeseries_points / map_home_timeseries_points
 -> POST /timeseries/ingest each cognitive cycle
 -> unconditional INSERT, recorded_at=Backend receive time
```

新規センサ観測ではなく、同じ現在値がcycleごとに再登録される。

### 3.3 Biometrics

```text
biometric-bridge MQTT -> Brain BiometricState
 -> map_biometric_payload (nested domain object)
 -> Backend /biometric/snapshot
 -> flat scalar BiometricReading columns
```

wire contractが不一致で、history以前に永続化が壊れている。

### 3.4 Feedback / trajectory

```text
Frontend POST /feedback
 -> Backend agent_feedback INSERT
 -> MQTT hems/feedback/{type}/{id}
 -> Brain FeedbackCollector
 -> Brain event_store.agent_feedback INSERT
```

BackendとBrainの双方が同じfeedbackを保持するが、MQTT payloadの`feedback_id`をBrain dedup keyとして使わない。

Brainの`TrajectoryRecorder`はBrain event_storeへ直接書き、Backend `/feedback/trajectory` callerは見つからない。Backend `agent_trajectories` はAPI単体テスト/manual入力以外のデータパスがない。

## 4. Findings

### P0-1 — Mobile observationはBackend受理後にsilent drop

Android監査の根因をBackend所有権として再確認した。

**証拠**:

- `routers/mobile.py:_publish_mobile_event()` は `hems/personal/mobile/<subtopic>` をpublish。
- `state_webhook()` はpayloadをDB保存せず、`MobileDevice.last_seen_at`だけcommitする。
- Brain `UserUpdatesMixin._update_personal()` は `notes` / `knowledge` / `biometrics` だけを処理し、`mobile`を無視する。
- responseの`published_topics`はBrokerへのpublish試行しか示さず、consumer state反映を保証しない。

**最小canonical修正**:

1. `/mobile/state/webhook`を外部mobile ingress SoTとする。
2. location/activity/batteryは型付き `MobileObservation` eventとして `hems/personal/mobile/...` にpublishし、Brain reducerを追加する。
3. biometricsはBackendで再正規化せず、internal-token付きでbiometric-bridgeのprivate ingestへforwardし、既存canonical `hems/personal/biometrics/{provider}/{metric}` に合流させる。
4. requestに`observation_id`とsource timestampを必須化し、Backend outbox/inbox tableにunique constraintを置く。DB commitとMQTT/HTTP deliveryを分離し、再送可能にする。

単にBrainへ`mobile`分岐を足すだけでは、biometric normalizationの二重実装とdelivery lossを温存する。

### P0-2 — Biometric POST contract mismatch

> **2026-07-18 実装済み (P0.2a/b)** — 実mapper payloadを型検証・flat化し、cycle insertをlatest row updateへ変更。immutable observation分離はPhase 1で継続する。

**修正前の証拠**:

- Brain `dashboard_mappers.map_biometric_payload()` は `heart_rate={bpm,...}`、`spo2={percent}`、`sleep`、`activity`、`stress`、`fatigue` のnested objectを生成。
- Backend `routers/biometric.update_biometric()` は `data.get("heart_rate")`をInteger列へ直接代入し、nested keyをflattenしない。
- `tests/test_dashboard_client_biometric.py` はproducerのnested payloadをmock HTTPで検証。
- `tests/test_backend_biometric_router.py` / integration testは手書きflat payloadを直接POST。

**影響**: heart rate / SpO2はDB型エラー、その他は欠落。transportは非200をDEBUGだけで飲むため運用上silentに近い。

**最小canonical修正**:

- `BiometricSnapshotIn` Pydantic schemaをBackendに定義し、Brain mapperと共有するgolden JSON fixtureを置く。
- Backendでnested domain snapshotをflat `BiometricReading`へ明示mapする。
- ただしhistoryはchanged-only/source-event方式へ直すまで一時的にupsert latest projectionとし、cycleごとのunconditional INSERTを止める。

### P0-3 — PostgreSQL既定化とtask stats SQLが矛盾

> **2026-07-18 実装済み** — `get_task_stats()` はUTC awareなPython cutoffをbindする
> `_completed_last_hour_query()` を使用するよう変更。PostgreSQL dialectでcompileしたSQLに
> SQLite固有`datetime()`が含まれないfocused testを追加した。SQLite実行testと合わせて `2 passed`、
> 対象ruff check / format checkもpass。

`database.py`の既定はPostgreSQLだが、`routers/tasks.py:get_task_stats()` は
`Task.completed_at >= func.datetime("now", "-1 hour")` を使う。これはSQLite関数で、PostgreSQLには`datetime(text,text)`がない。

`datetime.now(UTC) - timedelta(hours=1)` をbind parameterとして比較すれば両dialectで動く。既存testはSQLiteだけでこの矛盾を検出しない。

### P0-4 — 既存PostgreSQL DBのstartup migrationを保証できない

> **2026-07-19 実装済み (P0.3a/b/c)** — Backend `public` schemaを固定Alembic revisionへ移行し、
> unversioned DBを検証/reconcileするmigration-first entrypointを導入。runtime DDLを削除し、PostgreSQL 16 CI gateで
> fresh/no-op/partial legacy、Brain `events` schema非変更、migration失敗時Uvicorn未起動を検証する。

**修正前の証拠**:

- `main.py:lifespan()` が毎起動20列を `ALTER TABLE ... ADD COLUMN` する手書きmigration。
- `deadline`、`dismissed_at`、`locked_start`等に`DATETIME`を使うが、PostgreSQLの型は`TIMESTAMP [WITH TIME ZONE]`である。
- `_add_column_if_missing()` はDDL失敗をtransaction内でcatchする。PostgreSQLはstatement error後のtransactionをabortするため、context exit時commitまで安全に完了する契約ではない。
- migration version tableもAlembic revisionもなく、失敗はWARNING後に起動継続する。ORM query時にmissing columnで初めて壊れる。
- `docs/db-improvement-plan.md`はversioned migration tableを推奨するが未実装。

既定DBをPostgreSQLへ変えた時点で、migrationはoptional cleanupではなくrelease gateである。Alembicまたはdialect別revision runnerを導入し、startupはhead revision不一致/適用失敗時にfail fastすべき。

### P1-1 — Latest projectionがprocess-local dict

対象はzones, weather, news, knowledge, gas, pc, services, perception, home, brain power-mode。

- restartで消失し、Brainの次cycleまで`no_data`。
- 複数Uvicorn workerではPOSTを受けたworkerとGETを処理するworkerが異なり不整合。
- source timestamp / received_at / expires_atが統一されず、Brain停止後も一部routerは古い値を無期限に返す。
- requestがほぼ`dict`で、contract driftを検出しない。

個人向け1processならDB永続化は必須ではない。最小修正はRedis導入ではなく、単一 `LatestProjection` table（domain, payload JSON, source_ts, received_at, expires_at, version）またはBackendをprojectionから外しFrontendがBrain read APIを読む、のどちらかに統一すること。

### P1-2 — Time-seriesが同一観測をcycleごとに二重・多重登録

- `push_zone_snapshot()`はzone snapshot後、temperature/humidity/co2を毎cycle `/timeseries/ingest`。
- `push_home_snapshot()`はpositive power値を毎cycleinsert。
- mapperはworld-modelの`last_update`をTimeSeriesPointへ渡さず、Backend receive時刻を記録。
- ingestにidempotency/natural key/unique constraintがない。

同じsensor sampleが「30秒ごとの新観測」に変換され、平均・件数・滞在時間を歪める。30日retentionは重複計上を解決しない。

修正はMQTT ingest時のsource eventを一度だけ保存し、`(source, device_id, metric, source_ts or observation_id)`をuniqueにする。cycle snapshotはlatest projection専用にする。

### P1-3 — Task completionが非冪等でSystemStatsを二重計上

`tasks.complete_task()` は既に`is_completed=True`でも拒否/early returnせず、毎回:

- `completed_at`上書き
- `SystemStats.tasks_completed += 1`
- task report / lifecycle MQTT再publish

を行う。network timeout後のclient retryで統計とlearning eventが二重になる。DB由来`count(Task where completed)`とmanual counter `SystemStats.tasks_completed`という二つの集計SoTも持つ。

完了遷移はcompare-and-set (`WHERE is_completed=false`) とし、counterを廃止してquery集計、またはtransactional event/outboxから更新する。

### P1-4 — Shopping purchaseが非冪等

`shopping.purchase_item()` は既購入guardがなく、再呼出ごとに:

- `PurchaseHistory` row追加
- recurring itemの次instance追加
- purchased MQTT再publish

を行う。`ShoppingItem`にも自然キー/unique constraintがなく、add時の「同名未購入」dedupはapplication-level select後insertなのでconcurrent requestでraceする。さらにnameだけでstore/unit/category違いの商品を誤mergeする。

purchase transitionをCAS化し、idempotency keyまたは`purchase_event_id` uniqueを持たせる。商品identityは少なくともnormalized name + unit/store policyを明文化する。

### P1-5 — Device identityはrow重複だけ防ぎ、物理identity重複を防がない

`Device.device_id`だけuniqueで、`vendor_ref`は非unique。heartbeatはselect-then-insertでDB upsertではない。

- concurrent unknown heartbeatはunique violation/500になりうる。
- 同じ物理deviceをZigbee、HA、vendor bridgeが別device_idで発見すると複数rowになる。
- `last_state` / `last_value`をlatest projectionとしてDevice metadata rowへ混在させている。

Backend=Device SoT / Brain=TTL cacheという二層自体は妥当。ただしSoTには`DeviceIdentity`/alias（source, external_ref -> canonical_device_id）が必要で、physical deviceとintegration entityを区別すべき。heartbeatはdialect対応upsertとする。

### P1-6 — Feedback/trajectoryに二重SoTとdead pathがある

- `AgentFeedback`はBackend DBとBrain event_storeに複製されるが、MQTT redelivery dedupがない。
- Backendが発行する`feedback_id`を`Brain._collect_feedback()`はcollectorへ渡さない。
- `AgentTrajectory` model/routerはBackendにあるが、Brain `TrajectoryRecorder`はBrain event_storeへ直接writeし、Backend callerがない。
- `services/backend/CLAUDE.md`はBrainがBackend `/feedback/trajectory`へ書くと説明する一方、`IMPLEMENTATION_MAP.md`はBrain event_storeを所有者とする。

canonical ownerをBrain event_store（learning mart）またはBackend DBのどちらか一つに決める。推奨は外部受付・監査SoT=Backend、学習projection=Brainとし、global event idを保持してidempotent replicateする。未使用Backend trajectory table/APIは配線するか削除する。

### P1-7 — Approval audit JSONのin-place mutationが永続化されない

`Approval.audit_log`はplain SQLAlchemy `JSON`。`ApprovalQueueManager`は`row.audit_log.append(...)`で変更するが、`MutableList.as_mutable(JSON)`やfield再代入を使わない。SQLAlchemyはplain JSON内のin-place mutationを通常dirtyとして追跡しない。

decide/execute/rollback/expireのstatusは保存されてもaudit eventがDBへ保存されない可能性が高い。mock/in-session object assertionでは見逃す。新sessionでreadbackするtestが必要。

さらに`mark_executed()`は`executed_at`だけを付けstatusを変更しないため反復実行可能で、status comment/rollback checkにある`executed`状態と実装が一致しない。

### P1-8 — FK / retention semanticsがdialectで分裂

SQLite connect hookはWAL/busy_timeoutだけで`PRAGMA foreign_keys=ON`を設定しない。PostgreSQLはFKを強制するが`ondelete`/relationship cascadeがない。

completed Task retentionは`ScheduledBlock.ref_task_id`と`DismissLog.task_id`を先に処理せずTaskをdeleteするため:

- SQLite: FK無効ならorphanを残す。
- PostgreSQL: 参照rowがあればdeleteを拒否しcleanup iteration全体がrollback。

retention docは「対応済み」とするがreferential cleanupまでは未完。FK policyを全dialectで有効化し、SET NULL/CASCADE/明示deleteをdomainごとに決める必要がある。

### P2-1 — JSON column policyが一貫しない

native `JSON`（Device capabilities/state, Automation config, feedback等）とJSON文字列（Task.task_type, Device.metadata_json, Message.tool_calls_json/metadata_json, DismissLog.context_json, ClassifierCache.value_json, VoiceCapsule.manifest_json）が混在する。

結果としてvalidation/query/index/mutation trackingがfieldごとに異なり、`_safe_json_loads()`のようなsilent fallbackがcorruptionを隠す。wire schemaが安定したdomainはJSONB/Pydantic型へ、opaque artifactだけTextへ分類すべき。

### P2-2 — Chat write transactionが途中状態を正規状態として残す

`chat.send_message()` はconversation作成、user message保存を個別commitしてからBrainをcallする。Brain timeout/502時にはuser messageだけが残る。これは監査ログとして意図するならstatus (`pending/failed`) が必要だが、現schemaは通常messageと区別しない。

assistant responseまで単一transactionにすると120秒lockになるため不適切。outbox/job statusまたはmessage delivery statusを持つsagaにするのが妥当。

### P2-3 — Snapshot transportが重大なwrite failureをDEBUGで捨てる

`DashboardTransport.post_snapshot()` は非200/exceptionをDEBUG logにしてFalseを返す。多くのcallerは返値を無視する。biometric contract error、Backend outage、schema 422がhealth/SLAに出ず、再送queueもない。

latest projectionは次cycle再送でよいが、observation/event/history writeに同helperを使ってはいけない。delivery classごとにtransportを分けるべきである。

## 5. Mock seam / test gap

1. Brain biometric mapperのnested testとBackend flat route testが別fixtureで、actual payload contract testがない。
2. Snapshot router testsはmodule-global dictを同processで直接確認し、restart/multiworker/stalenessを検証しない。
3. Time-series testsは手書き1回ingestだけで、同じworld-model sampleを複数cycle送るcaseがない。
4. Backend testsは主にSQLiteで、PostgreSQL既定の`func.datetime`、migration型、FK behaviorを検証しない。
5. task complete / shopping purchaseのretry testがない。
6. approval audit testはcommit後に新sessionでJSON readbackしない。
7. feedback testはBackend CRUDだけで、MQTT duplicate delivery -> Brain event_storeのend-to-end dedupを検証しない。
8. Backend trajectory testはAPIへ直接POSTするだけで、production caller不在を検出しない。
9. Device heartbeatにconcurrent insert / alias collision testがない。

## 6. ドキュメント不整合

- `README.md` / root docsの「Backend=永続SoT」はDevice/CRUD domainには正しいが、10前後のsnapshot domainはprocess-local cache。
- `services/backend/CLAUDE.md`はBiometricsを「受信・履歴・集計」とするが、Brain contract mismatchとcycle重複を記載しない。
- 同docはBrainがBackend `/feedback/trajectory`へ記録するとするがcaller不在。
- `docs/IMPLEMENTATION_MAP.md`はagent trajectory ownerをBrain event_storeとし、Backend CLAUDEと矛盾。
- `IMPLEMENTATION_MAP`のreducer網羅「15分岐すべて網羅」は`hems/personal/mobile/*`を見落としている。
- `docs/db-improvement-plan.md`はretentionを対応済みとするが、Task FK/orphan/PG failureとsnapshot duplicationは未解決。
- root `CLAUDE.md`のbridge status記述は未発行/履歴なしとするが、現行コードにはcanonical status publishと`BridgeStatusLog`がある箇所があり陳腐化。
- Backend CLAUDEはshopping public router未mountを既知bugとして記載するが、`main.py`では現在も未mount。計画化されず恒久化している。
- Backend CLAUDEのcontrol safetyはBackend params未検証とするが、過去PLAN/SUMMARYにはshared validator実装済みとする記述があり、canonical説明が統一されていない。

## 7. 推奨canonical architecture

### 7.1 四つの保存クラスをAPIで分離

1. **Aggregate SoT**: Task, ShoppingItem, Device, Conversation。DB transaction + version/idempotency。
2. **Observation/Event log**: immutable、source_event_id/source_ts必須、unique constraint + outbox。
3. **Latest projection**: domain/key/version/source_ts/expires_atを持つupsert。履歴ではない。
4. **Derived learning mart**: canonical event idを引継ぐidempotent projection。SoTを名乗らない。

`POST /snapshot`をhistory insertに使わず、`PUT /projections/{domain}/{key}` と `POST /observations` を分ける。

### 7.2 Android P0の確定設計

- External client -> Backend `/mobile/state/webhook` が唯一のmobile ingress。
- Backend transactionで `mobile_observations(observation_id unique, device_id, source_ts, payload, delivery_status)` を保存。
- transaction後outbox workerがlocation/activity/batteryのcanonical eventをpublish。
- biometricsはinternal biometric-bridge ingestへforwardし、bridgeがmetric normalizationとcanonical biometric MQTTを所有。
- Brain reducerはmobile non-biometric domainだけを所有。
- Brain -> Backend biometric latest projectionは型付きupsert。履歴はbridge/mobile source observationから一度だけ作る。

この設計ならmobile retry、MQTT outage、Backend restartを吸収し、biometric normalizationとhistoryを二重所有しない。

## 8. 修正順

### 緊急

1. biometric request schema + producer/consumer contract testを追加しP0-2修正。
2. mobile observation inbox/outboxの最小tableとidempotency keyを設計し、silent dropを止める。
3. `get_task_stats()`をdialect-neutral datetime比較へ変更しPostgreSQL test追加。
4. hand-rolled migrationをfail-fast revision migrationへ置換。少なくともPG用型とtransaction behaviorを修正。

### 短期

5. task complete / shopping purchaseをCAS + idempotent化。
6. timeseriesをsource observation timestamp/idでdedupし、cycle snapshot insertを停止。
7. approval audit JSONをMutableListまたは再代入で永続化し、executed state machine修正。
8. SQLite FKを有効化しretention cascade policyを実装。
9. feedback event idをBrainまで保持しdedup。trajectory ownerを一本化。

### 中期

10. process-local snapshot dictをtyped LatestProjectionへ統合。
11. DeviceIdentity/alias tableとheartbeat upsert導入。
12. JSON/Text policy整理、Chat message delivery state追加。
13. AlembicをCI/quickstart/release gateへ統合。

## 9. Test案

- `map_biometric_payload` -> actual Backend route -> DB readback。
- 同じ`observation_id`をmobile webhookへ2回送りDB/eventが1件。
- MQTT failure後outbox再送でeventがexactly-once相当。
- PostgreSQL serviceでstartup migration from previous schema、task stats、retention FK test。
- task complete / shopping purchaseを2回callしてcounter/history/recurring rowが1件。
- same sensor source timestampを3 cycle pushしてTimeSeriesPointが1件。
- Backend restart / worker A POST -> worker B GETでlatest projection一致。
- approval decide後sessionを閉じ、新sessionでaudit_log eventを確認。
- MQTT feedback同一`feedback_id`再配信でBrain learning rowが1件。
- concurrent heartbeatとvendor alias collision。
- Chat Brain 502後にmessageが`failed`として識別可能。

## 10. 技術選定 / Agent由来負債

- SQLAlchemy採用は妥当だが、PostgreSQL既定化後もSQLite専用SQL・型・test fixtureを残したのは移行を設定変更として扱った負債。
- DDD不足ではなく、保存クラスを区別しないgeneric `snapshot` endpoint/helperが問題。repository/service層を大量追加する必要はない。
- producer/consumerを別々にmockし双方の期待payloadを各自で手書きしたため、green testがcontract破綻を隠した。
- 「全domainを一度にdashboardへpush」という便利なloopが、latest cacheとobservation historyを同じ周期処理へ巻き込み二重計上を生んだ。
- JSON field追加とstartup ALTERを繰り返す実装はfeature sliceを早く閉じるには便利だが、schema evolutionとdialect compatibilityを後回しにしている。

## 11. 検証記録

- 静的調査と既存test/doc照合のみ。
- 実装コード、DB、既存docは変更していない。
- 本監査文書のみ新規作成。
- test/buildは実行していない。所見の多くは未接続contract、dialect、idempotencyに関するため、修正時に上記cross-boundary/PostgreSQL testを先に追加する。
