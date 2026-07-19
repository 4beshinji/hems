# biometric-bridge / external health sources 分割レビュー — 2026-07-18

対象リビジョン: `3a91dac` (`main`)

Status as of 2026-07-19: P1.1 Backend側にtyped observation envelope、`biometric_observations`、
`HEMS_INTERNAL_TOKEN`保護の`POST /internal/biometric/observations`を実装した。同一ID/同一payloadは2xx、
同一ID/異なるpayloadは409。P1.2aでbridge private ingest、versioned `observation_inbox` / `delivery_outbox`、
metric envelope mapperまで実装した。workerによるMQTT/Backend deliveryとmobile callerは未実装である。

## 1. 対象と方法

対象:

- `services/biometric-bridge/`全体
- `infra/docker-compose.yml`、`env.example`
- standalone `apps/healthconnect-companion/`
- HEMS companion `services/mobile-android/`のHealth Connect / mobile webhook経路
- Brain biometric reducer、rule / presence / wake feed
- Backend mobile ingress / biometric persistence
- 関連test、README、`docs/IMPLEMENTATION_MAP.md`、旧監査

外部source -> HTTP/poll -> provider parser -> `DataProcessor` -> MQTT / send queue -> Brain reducer/feed ->
Backend snapshot DBを静的に追跡した。auth、source identity、timestamp、retry/restart、provider実装有無、composeでの
設定到達性を対照した。コード変更は行っていない。

## 2. 実データ経路

### 2.1 Standalone Health Connect（現在動く主経路）

```text
Health Connect (Mi Fitness等がwrite)
 -> HealthConnectReader.readLatest
 -> Room PendingReadingEntity
 -> HemsBridgeClient.postReading
 -> POST biometric-bridge /api/biometric/webhook
 -> GadgetbridgeProvider.process_webhook
 -> DataProcessor.process / _publish_reading
 -> retained MQTT hems/personal/biometrics/{provider}/{metric}
 -> Brain UserUpdatesMixin._update_biometric_state
 -> rule / presence / wake / schedule learner
 -> cognitive cycle map_biometric_payload
 -> Backend POST /biometric/snapshot
 -> BiometricReading DB
```

端末Room queueとbridge SQLite send queueがありoffline耐性への意図は良い。ただし両queueを跨ぐglobal observation IDがない。

主要な証拠symbol:

| 境界 | Symbol |
|---|---|
| public webhook / HMAC | `receive_webhook`, `_verify_webhook_signature`, `_check_nonce` |
| webhook normalization | `GadgetbridgeProvider.process_webhook`, `DataProcessor.process` |
| value-window dedup | `DataProcessor.is_duplicate`, `_reading_keys`, `record_published` |
| MQTT projection | `_publish_reading`, `_mqtt_publish` |
| durable retry | `SendQueue.enqueue`, `SendQueue.flush`, `_flush_queue_loop` |
| cloud polling | `HuamiProvider.poll`, `_last_hr_ts`, `ZeppProvider.poll` |
| standalone producer | `HealthConnectReader.readLatest`, `DataSyncWorker.doWork`, `HemsBridgeClient.postReading` |
| mobile producer | `HealthConnectWorker.doWork`, `SensorBuffer.drainLatest`, `SyncRepository.submit` |
| Brain consumer | `UserUpdatesMixin._update_personal`, `_update_biometric_state` |
| Backend history | `routers.biometric.update_biometric`, `map_biometric_payload` |

### 2.2 HEMS mobile companion（現在dead end）

```text
HealthConnectWorker
 -> SensorBuffer (process memory)
 -> SyncRepository
 -> Backend /mobile/state/webhook
 -> hems/personal/mobile/biometrics
 -> Brain personal router
 -> silent drop (`mobile` categoryなし)
```

同じ端末へstandalone appとHEMS companionを入れると、同じHealth Connect dataを二経路で読む。後者は現状Brainへ
反映されず、前者だけが実経路である。HEMS companionのbufferはRoomではなくmemoryで、drain後HTTP失敗時の復元境界も弱い。

### 2.3 Cloud / Gadgetbridge

- Gadgetbridge: bridge webhookへTasker / Automate等でflat JSONを送るadapter。実装あり。
- Huami: `HuamiProvider.poll()`が非公式cloud endpointをpollする実装あり。
- Zepp: `ZeppProvider.poll()`が常に`None`を返す明示的placeholder。

## 3. Findings

### P0-1（再確認）— HEMS mobile biometricはcanonical pathへ入らない

`Backend mobile.state_webhook`は`hems/personal/mobile/biometrics`をpublishするが、Brain
`UserUpdatesMixin._update_personal()`は`notes` / `knowledge` / `biometrics`だけを扱う。このためHEMS companionの
Health Connect実装は作り込まれていてもdata pathが完結しない。

Brainへmobile biometric parserを追加してはならない。standalone app、Gadgetbridge、Huamiと別のnormalizationを
増やすためである。Backendがdevice HMACを検証した後、biometric部分をbridge private ingestへforwardして
一つのnormalizerに合流させるのが最小境界である。

### P0-2（再確認）— BridgeからBackend historyまでのcontractが破断

> **2026-07-18 実装済み (P0.2a/b)** — Backendでnested snapshotを型検証・flat化しlatest row updateへ変更。observation identity/outboxはPhase 1対象。

Bridgeはmetric別MQTTをBrainへ送り、Brain `map_biometric_payload()`はnested snapshotを作る。Backend
`update_biometric()`はflat scalar列を期待する。producer / consumer testも別payloadを手書きするため不一致を隠す。

さらにcycle snapshotは観測eventではなく現在値なのに、Backendは毎cycle新しいhistory rowとしてinsertする。
contract flattenだけ直しても二重・多重計上が始まるため、latest projectionとobservation persistenceを同時に分ける必要がある。

### P1-1 — source timestampと観測identityがnormalization時に失われる

standalone Health Connectはpayloadへ`timestamp`を入れるが、`GadgetbridgeProvider.process_webhook()`は常に
`BiometricReading(timestamp=time.time())`を生成し、入力timestampを読まない。`_publish_reading()`のmetric payloadにも
timestamp、observation ID、device/source record IDを含めない。

結果:

- 端末offline queueから24時間後に届いた値も現在の観測に見える。
- Brain historyはMQTT受信時刻で並び、遅延・再送を区別できない。
- sleep endの再送がwake automation / schedule learningを再発火・二重学習し得る。
- Backendはsource時刻で一意制約を作れない。

### P1-2 — dedupは値の5分memory cacheで、観測dedupではない

`DataProcessor._recent`は`hr:value`、`steps:value`、`spo2:value`、`sleep:duration`、`stress:value`を記録し、全keyが
5分以内に一致したreadingを捨てる。

- restartで全履歴が消える。
- HRV、体温、呼吸数、activity、caloriesはkeyに含まれず、それだけのreadingはdedupされない。
- 同じHRでstepsだけ変わるreadingは全体がnon-duplicateとなりHRも再publishされる。
- sleep durationが同じ訂正readingはstart/end/stage/qualityが変わっても捨て得る。
- 同値が続く正当な別観測とredeliveryを区別できない。
- Huamiの日次summaryはpoll間隔が窓より長いため、同じ累積steps/sleepを毎poll再publishする。

`HuamiProvider._last_hr_ts`は宣言されるが利用されず、commentの「avoid re-processing」は実装されていない。

### P1-3 — HTTP 200からdurable MQTT deliveryまでcrash windowがある

`_mqtt_publish()`はbroker publish失敗時、`asyncio.create_task(send_queue.enqueue(...))`をscheduleするだけで返る。
webhook endpointはenqueue commitをawaitせずHTTP 200を返す。processがその間に落ちると、standalone appはRoom rowを
削除済みなのにbridge outboxへも残らない。

broker publish成功も複数metricをtransactionとして扱わず、途中failureでは一部だけdirect publish、残りだけqueueとなる。
send queueは良い部品だが、HTTP受理のdurability boundaryにはなっていない。

### P1-4 — reconnect時に古いretained metricをeventとして再生する

`SendQueue`は最大24時間metric別messageを保持し、復旧後に古い順で最大100件ずつpublishする。全metric topicは
`retain=True`で、payloadにsource timestampがない。Brainはそれらを現在eventとしてhistory、rule、wake/sleep feedへ渡す。

retained topicはlatest projectionには向くがevent deliveryには向かない。latest state topicとimmutable observation eventを分けるか、
少なくともobserved_at / observation_idを含めconsumerがstale event side effectを拒否する必要がある。

### P1-5 — replay strictへ移行できるclient / compose契約になっていない

Bridgeは`X-Timestamp` + `X-Nonce`を含むHMACを実装するが、standalone `HemsBridgeClient`はraw body署名だけを送り、
新headerを送らない。`WEBHOOK_REPLAY_STRICT=true`にすると主経路が401になる。

さらにnonceはHMAC検証前に`_check_nonce()`で消費される。invalid signature requestでもnonce cacheへ登録されるため、
正当requestとnonceが衝突した場合に拒否できる。nonce登録はsignature成功後に行うべきである。

`BIOMETRIC_WEBHOOK_SECRET`が空ならpublic webhook authは完全無効だが、composeは`${...:-}`で空を許す。
LAN bindでもreverse proxyやport公開変更時のspoof riskがある。strict化はclient release -> telemetry確認 -> server enforceの順に行う。

### P1-6 — env.exampleのprovider設定がcompose containerへ届かない

`config.py`はHuami / Zepp / dedup / fatigueのenvを読むが、biometric-bridgeのcompose `environment`はそれらを渡さない。
不足例:

- `HUAMI_ENABLED`, token, user ID, region, poll interval
- `ZEPP_ENABLED`, email, password, poll interval
- `WEBHOOK_REPLAY_STRICT`
- `BIOMETRIC_DEDUP_WINDOW`
- fatigue weights

`.env`にenv.example通り設定してもCompose interpolation対象に列挙されない値はcontainer environmentへ入らない。
したがってHuami/Zeppは通常composeでは常にdisabled、strictは常にfalse、tuningもdefault固定である。

`env.example`の`BIOMETRIC_DB_PATH=/app/data/biometric.db`もcomposeの`/data/send_queue.db`と用途・pathが異なる。
このDBはbiometric cache/historyではなくMQTT outboxだけであり、commentも誤解を招く。

### P1-7 — Zeppはdocumented pathだがplaceholder / mock-only

env.exampleは「Path 3: Zepp」とcredentialを案内し、startupもpoll taskを構築する。しかし`ZeppProvider.poll()`は
「not implemented」とlogして常に`None`を返す。credentialを設定してもdataは一件も流れない。

placeholder providerと設定を削除するか、experimental / unimplementedとして起動時にfail fastする。正常稼働に見える
health responseを返すべきではない。旧監査はZeppを単なる未文書providerとしたが、実装済みではない点を見逃していた。

### P1-8 — Provider abstractionと実際のwebhook parsing責務が一致しない

すべてのwebhook（Health Connectを含む）を`GadgetbridgeProvider.process_webhook()`でparseし、その後payloadのprovider名だけ
上書きする。つまりprovider labelはsourceを示してもparser / validation schemaを示さない。`BiometricProvider` interfaceも
polling中心で、webhook parse methodを定義しない。

多数のprovider classを増やす必要はない。外部wire schemaを一つのtyped `BiometricObservationIn`に統一し、source固有adapterは
そのschemaへの変換だけを担う。Health Connect専用classを作るより、現在のflat schemaを正式化する方が小さい。

### P1-9 — 二つのAndroid Health Connect clientは意味と集計窓が異なる

standalone appはHR/SpO2/HRV直近30分、steps/calories当日累計、sleep直近24時間をbridgeへ送る。
HEMS companionはHR/steps/sleepを直近20分だけ読み、Backend mobile webhookへ送る。

同じ`steps`でも「当日累計」と「20分増分」が区別されず、source / aggregation kind / interval start/endがschemaにない。
両app併用時のdedupは値一致前提なので機能しない。正規化schemaに`aggregation`（sample / interval_sum / daily_total）と
intervalを持たせるか、最小構成ではHEMS companionを唯一のappに統合するまでstandaloneをcanonicalと明記する。

### P2-1 — latest / sleep / activity APIはprocess-local read model

`DataProcessor._latest`、`_sleep_cache`、HR historyはmemoryだけでrestart時に消える。SQLiteはsend queue専用である。
Brain toolが`/sleep`を読むため、restart直後はMQTT retained stateがBrainにあってもbridge APIは`no_data`になり得る。

全history DBをbridgeへ追加する必要はない。retained latestをstartup時にhydrateするか、小さなlatest projection tableをoutbox DBへ
追加する程度でよい。`/activity`のproduction callerは見つからず、公開contractとして残すなら用途を明記する。

### P2-2 — fatigueは異なる時間軸のlatestを混合する

`compute_fatigue()`はprocess内HR history、last sleep cache、latest readingのstress/HRVをsource timestampやstalenessなしで合成する。
restartでscoreが変わり、古いsleepと新しいHR、または別providerのlatestを混ぜ得る。臨床指標ではなくheuristicであることを
UI/docに明示し、factorごとのmax ageを設定すべきである。

## 4. 最小canonical design note入力

Kafka、FHIR server、event sourcing全面導入は不要。既存FastAPI、SQLite outbox、MQTT、Backend PostgreSQLを保ち、次の一枚だけを追加する。

### 4.1 Canonical envelope

```text
BiometricObservationIn
  observation_id: string       # producer生成UUID、retryで不変
  provider: string             # healthconnect / gadgetbridge / huami
  device_id: string | null
  observed_at: UTC datetime
  interval_start/end: datetime | null
  aggregation: sample | interval_sum | daily_total | session
  metrics: typed optional fields
  schema_version: 1
```

値だけの`metric:value`ではなく`observation_id`をdedup keyにする。provider固有record IDがあればUUIDの代わりに
`provider + record_id`をnatural keyにできる。

### 4.2 Ingressと所有権

1. standalone Health Connect / Gadgetbridgeはpublic webhookへcanonical envelopeをHMAC送信する。
2. HEMS mobileはBackendでper-device HMACを検証する。
3. Backendはbiometric部分をinternal-token付きbridge `POST /api/biometric/ingest`へforwardする。
4. Bridgeは一か所でvalidate / normalizeし、SQLite inboxへ`observation_id UNIQUE`でcommitしてから200を返す。
5. 同transactionでoutbox rows（MQTT latest/event、Backend observation API）を作り、workerがretryする。
6. Backend `/internal/biometric/observations`は同じIDをuniqueにcanonical historyへ一度保存する。このstore/APIはP1.1で実装済み。
7. Brain cycle snapshotはlatest projectionだけをupsertし、historyを作らない。

既存`SendQueue`をinbox/outboxへ小さく拡張できる。新brokerや新DB serviceは不要である。

### 4.3 MQTT

- latest topicはretainedでよいがpayloadへ`observation_id`, `observed_at`, `provider`, `aggregation`を含める。
- automation / learnerはobservation IDとstalenessで一度だけside effectを実行する。
- daily total stepsを差分eventとして扱わず、WorldModel latest projectionとして扱う。
- sleep session endはsession IDでedge-triggerし、retained replayでwake eventを再発火しない。

## 5. Test / mock seam

現testはauth endpointのstatus、provider parserのfield変換、mock MQTT topic数を主に検証する。以下が不足する。

- standalone appがstrict HMAC headerを生成しbridgeが受理するgolden request test
- invalid HMACがnonceを消費しないtest
- source timestamp / observation IDがAndroid -> bridge -> MQTT -> Brain -> Backendまで保持されるcontract test
- 同一ID retry、bridge restart、MQTT redeliveryでDB / learner / automationが一度だけ動くtest
- HTTP 200直後crashでもinbox/outboxに残るfailure-injection test
- 24h queue flushで古いsleepがwake eventを発火しないtest
- compose rendered configにHuami / strict / dedup envが存在するtest
- Zepp enabled時にsilent healthyとならないtest
- daily_totalとinterval_sum stepsを混同しないtest
- Brain mapperの実payloadをBackend schemaへ通すtest

`tests/test_biometric_bridge.py`はwebhook authを意図的に無効化し、mock publisherを使うため、productionの必須secret、
strict protocol、durable deliveryを跨がない。`test_biometric_steps_dedupe.py`は一reading内の二重topicだけを検証し、
cross-provider / restart / observation identityのdedupを検証しない。

## 6. Documentation freshness

- `env.example`のHuami / Zepp / strict / dedup設定はcompose未配線。
- Zeppを利用可能なPath 3として案内するがproviderはplaceholder。
- `apps/healthconnect-companion/README.md`はwebhookを`/devices/heartbeat`と記載する箇所があり、実装の
  `/api/biometric/webhook`と不一致。
- `BIOMETRIC_DB_PATH`をlocal biometric cacheのように書くが、実体はMQTT send queue。
- `docs/IMPLEMENTATION_MAP.md`のtopic listはpayloadにsource timestamp / identityがないこと、mobile branchがdead endなことを示さない。
- 2026-05-25旧監査はZeppのplaceholder、compose設定欠落、dedup / timestamp / delivery gapを未検出で、鮮度不足。

## 7. 修正順

1. Android/Backend/Brain P0境界を固定: mobile biometricをbridge private ingestへ合流。
2. canonical envelopeとgolden contract testを追加し、input timestampを保持。
3. Bridge inbox/outboxをHTTP 200のdurability boundaryにし、observation ID unique dedupを導入。
4. MQTT/Brain/BackendへIDとsource timeを通し、cycle snapshot history insertを停止。
5. standalone clientへtimestamp/nonce HMACを実装してrelease後、strictをdefault化。
6. compose env配線を修正し、Zeppは削除またはfail-fast experimental化。
7. stale/retained sleep side effect、Huami daily summary、fatigue freshnessを整理。
8. canonical docsと旧監査にstatus noteを同期する。

最優先はprovider数を増やすことではなく、同一観測が「一つのID・一つの正規化・一度の永続化」で末端まで届くようにすることである。
