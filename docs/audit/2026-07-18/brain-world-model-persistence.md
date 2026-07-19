# Brain world model / MQTT / persistence 分割レビュー — 2026-07-18

対象リビジョン: `3a91dac` (`main`)

Status as of 2026-07-19: biometric P0/P1.1でBrain cycle writeは`biometric_latest`専用となり、Backendに
stable ID/source metadata付き`biometric_observations`を追加した。Brainはcanonical historyを作らない。
P1.2a/bでbridge受理・delivery実行まで実装したが、mobile callerとBrain side-effect dedupは未配線である。
P1.3a/bでBackend mobile durable ingress/deliveryを配線したがBrain reducerは未配線で、state反映欠落は継続する。

## 1. 対象と検証方法

対象:

- `services/brain/src/brain_mqtt.py`
- `services/brain/src/world_model/`
- `services/brain/src/event_store/`
- `services/brain/src/brain_cognitive.py`
- `dashboard_client.py` / `dashboard_transport.py` / `dashboard_mappers.py`
- feedback、timeline、rule / automationへのMQTT feed
- 関連test、`services/brain/CLAUDE.md`、`docs/IMPLEMENTATION_MAP.md`

静的に MQTT subscribe -> router -> reducer -> side effect -> persistence を追跡し、固定長event buffer、
cycle snapshot、Backend DBとの所有権、source timestamp / idempotency / retentionを対照した。
Android / Backend監査のP0-1、P0-2も実consumerまで再検証した。コード変更とDB migrationは行っていない。

## 2. 現在の実効アーキテクチャ

Brain内には同じ観測の異なる表現が複数存在する。

| 層 | 役割 | 実装 | 永続性 |
|---|---|---|---|
| MQTT intake | 外部event受信 | `brain_mqtt.py` | なし |
| WorldModel latest state | ReAct context用の現在値 | domain dataclass | process-local |
| WorldModel short history | event ring / biometric deque / fusion counter | domainごとに個別実装 | process-local |
| Brain event_store | sensor、decision、learning用data mart | `events` schema / SQLite | DB。ただしwriter bufferはprocess-local |
| Backend latest projection | Frontend read model | cycleごとのHTTP snapshot | 多くはprocess-local dict |
| Backend observation history | timeseries / biometric | Backend DB | biometricはP1.1でimmutable storeへ分離済み。timeseriesのcycle snapshot insertは継続 |

この多層化自体は妥当になり得る。しかし「runtime cache」「latest projection」「canonical observation」
「learning mart」の境界がcontractやdocに明記されず、同じ値の多重登録と欠落が同時に起きている。

`_process_mqtt()` の実行順は明示されており、world model更新後にautomation、timeline、event_store、
registry、cycle triggerへfeedする。characterization testも通常系の順序を固定している。この部分は良い。

### 2.1 Topic -> reducer -> feed -> store -> snapshot

```text
MQTT on_message / BrainMqttMixin._process_mqtt
  -> WorldModel.update_from_mqtt
     -> MqttRouterMixin._route_mqtt_topic
     -> PhysicalUpdatesMixin / UserUpdatesMixin / domain updater
  -> motion / shopping / timeline / intervention / schedule / wake feed
  -> BrainMqttMixin._record_to_event_store
     -> EventWriter.record_sensor | record_world_event
  -> device registry / BrainMqttMixin._maybe_trigger_cycle
  -> BrainCognitiveMixin cognitive cycle
  -> DashboardClient + dashboard_mappers
  -> DashboardTransport.post_snapshot
  -> Backend latest projection / timeseries / biometric DB
```

主要な証拠symbol:

| 論点 | Symbol |
|---|---|
| subscribe / intake | `BrainMqttMixin.on_connect`, `BrainMqttMixin.on_message` |
| pipeline順序 | `BrainMqttMixin._process_mqtt` |
| personal routing | `MqttRouterMixin._route_mqtt_topic`, `UserUpdatesMixin._update_personal` |
| event store選別 | `BrainMqttMixin._record_to_event_store` |
| cycle trigger | `BrainMqttMixin._maybe_trigger_cycle`, domain `add_event` methods |
| raw/world writer | `EventWriter.record_sensor`, `EventWriter.record_world_event`, `EventWriter._flush_loop` |
| retention | `HourlyAggregator._run_retention`, `RAW_RETENTION_DAYS`, `DECISION_RETENTION_DAYS` |
| snapshot mapping | `map_biometric_payload`, `map_zone_timeseries_points`, `map_home_timeseries_points` |
| feedback複製 | `BrainMqttMixin._collect_feedback`, `FeedbackCollector.collect` |
| trajectory owner | `TrajectoryRecorder.record` |

## 3. Findings

### P0-1（再確認）— Mobile observationはBrain reducerに到達してもsilent drop

Backend `routers/mobile.py` は `hems/personal/mobile/<subtopic>` をpublishする。Brainは`hems/#`をsubscribeし、
`world_model/mqtt_router.py`も`hems/personal/*`を`_update_personal()`へ渡す。しかし
`world_model/user_updates.py`が認識するcategoryは`notes`、`knowledge`、`biometrics`だけで、`mobile`は何もせず戻る。

したがってBackend responseの`published_topics`はbrokerへの送信を示すだけで、WorldModel反映を保証しない。
このP0はAndroid / Backend監査と同じ根因であり、Brain側まで追跡して確定した。

最小修正境界:

1. Backend mobile webhookを外部ingress SoTとし、`observation_id`とsource timestampを受ける。
2. location / activity / batteryだけを型付きmobile eventとしてpublishし、Brainに専用reducerを追加する。
3. biometricはmobile reducerへ二重実装せず、biometric-bridge private ingestを経由して既存canonical
   `hems/personal/biometrics/{provider}/{metric}`へ合流させる。
4. DB commit後のdeliveryをdurable outboxで再送可能にし、consumer側もevent IDで冪等化する。

単に`mobile`分岐を追加するだけでは、Backend受理後・MQTT publish前のlossとbiometric正規化の重複を解消しない。

### P0-2（再確認）— Biometric cycle snapshotのproducer / consumer contractが不一致

> **2026-07-18 実装済み (P0.2a/b)** — typed nested→flat mappingとlatest updateを導入。多重history insertは停止し、canonical observationはPhase 1対象。

`dashboard_mappers.map_biometric_payload()`は`heart_rate={bpm,...}`、`spo2={percent}`、`sleep`、`activity`等の
nested objectを返す。一方Backendはflat scalarを`BiometricReading`列へ代入する。producer testはnested payload、
Backend testは手書きflat payloadを別々に検証するため、結合不整合を検出しない。

Brain event_storeはbiometric MQTTをraw eventとして保存しておらず、event ID / provider / source timestampを備えた
canonical biometric storeでもない。このため「既存event_storeへ切り替える」だけではP0-2を直せない。

最小修正境界:

- Backendに型付き`BiometricSnapshotIn`を置き、producerとconsumerで同じgolden JSON fixtureを使う。
- nested latest stateからflat read modelへのmappingを一か所に明示する。
- cycle snapshotはlatest projectionのupsertだけにし、観測historyへのunconditional insertを止める。
- biometric observationはcanonical ingressでsource eventごとに一度だけ永続化する。

### P1-1 — 固定長event ringが満杯になると即時cycle triggerが停止

`_maybe_trigger_cycle()`は各domainの`len(events)`だけを前回値と比較する。一方、各`add_event()`はappend後に
20 / 30 / 50件へtrimする。ringが上限に達した後は新eventで内容が変わっても長さが変わらず、
`_cycle_triggered`がsetされない。

定期/proactive timeoutで最終的にcycleは動くため永久lossではないが、event-driven latencyとlow-power時の反応性が壊れる。
testは空bufferや通常増加だけを扱い、saturationを検証しない。

event数ではなく、WorldModel全体のmonotonic revision、または受理event sequenceをincrementし、そのrevision差でtriggerする。
少なくとも上限到達後のappend、複数domain同時更新、feature flagあり/なしをcharacterization testへ追加する。

### P1-2 — EventWriterはdurable outboxではなく、観測identityも持たない

`EventWriter`はrowをprocess memoryへbufferし、通常5秒ごとにflushする。DB failure時はrequeueするが、
Brain crash / restartでは未flush rowが失われる。`record_sensor()`は受信時刻、topic、channel、valueを保存するだけで、
source timestamp、observation ID、MQTT sequenceを持たない。redeliveryは別rowになる。

`record_world_event()`のdedupはpayload SHA-1を5分保持するprocess-local dictである。

- restartでdedup stateが消える。
- DB unique constraintがない。
- 同一内容の正当なeventを5分間抑止し得る。
- payload内timestampが変われば同じ実eventも通る。

従って現event_storeはBrain analytics / learning martには使えるが、mobile ingressのtransactional outbox、
canonical biometric history、exactly-once ledgerとしては再利用不可である。再利用にはstable `event_id`、`source_ts`、
provider/source、DB unique constraint、disk-backed producer outboxまたはinboxが先に必要になる。

### P1-3 — Cycle snapshotが同一観測をBackend historyへ多重登録

Brainはcognitive cycleごとにcurrent WorldModelをBackendへpushする。zone temperature / humidity / CO2とhome powerは
snapshotからtimeseries pointを生成し、Backend receive timeでunconditional insertする。新しいMQTT観測がなくても
同じ値が新観測として増え、件数・平均・滞在時間を歪める。biometricも同じ設計であり、P0-2修正後も放置できない。

MQTT reducerでlatest stateを更新する経路と、canonical observationを一度保存する経路を分ける。
cycleはread-model snapshotだけを更新し、history writerには接続しない。

### P1-4 — Feedback / trajectoryはBackendとBrainに二重所有され、identityを失う

BackendはfeedbackをDB保存して`feedback_id`付きMQTTを送るが、Brain `_collect_feedback()`はそのIDをcollectorへ渡さず、
Brain event_storeへ別rowを追加する。redelivery dedupができない。

trajectoryは逆にBrain `TrajectoryRecorder`がevent_storeへ直接書き、Backend `/feedback/trajectory`のproduction callerがない。
Backend DBを外部受付・監査SoT、Brain event_storeをlearning projectionとするなら、global event IDを末端まで保持して
idempotent replicationする。そうしないなら未配線Backend trajectory API/tableを削除する。

### P1-5 — Event storeのcoverageは選択的で、WorldModel historyとの責務が不透明

raw persistence対象は主に`hems/sensors/{zone}/sensor/{id}/{channel}`。world eventはshoppingの一部、GAS、
weather alert、urgent newsに限定される。biometrics、mobile、通常news、home stateなどは同じevent ledgerへ入らない。
一方WorldModelにはdomain event ring、biometric history deque、sensor fusion counterが個別に存在する。

「全MQTT監査log」ではなく選択的data martであることを命名・docで明示し、domainごとに次を一表へ固定すべきである。

- latest owner
- canonical history owner
- in-memory window / TTL
- replay可能性
- Backend projectionの用途

### P1-6 — wake / sleep learningとautomationはretained・再送eventに弱い

biometric sleep payloadで`sleep_end > 0`ならschedule learnerへ記録し、wake-up automationも発火する。
同じpayloadの再送やretained deliveryをsource event IDで抑止する局所guardはない。morning camera countも同様に
値が正なら発火候補になる。downstream cooldownが被害を緩和しても、学習sampleの二重計上は別問題である。

edge-trigger（状態遷移）とlevel-trigger（現在値）をtopic contractで分離し、automation / learner双方で
stable event IDまたはlast processed sequenceを持つべきである。

### P1-7 — Retentionは一部tableだけで、730日raw保持は容量設計がない

`HourlyAggregator`が削除するのは`raw_events`と`llm_decisions`だけで、既定730日。`world_events`、feedback、
trajectories、drift detections、interventions等のappend-only tableには同じcleanupがない。
高頻度sensorを2年保持する件数・index・backup・vacuum見積りもdocにない。

tableごとに法的/運用上の必要期間、集約後raw削除、partition、容量budgetを決めるべきである。
個人単一nodeのSQLiteは軽量fallbackとして妥当だが、高頻度長期martの本線は既定PostgreSQLでpartition / migrationを
管理する方が構造に合う。

### P1-8 — event_store schema管理が二重でmigration failureを隠す

`event_store/database.py`はSQLite/PostgreSQLのDDL文字列を別々に維持して単純に`;` splitする。
PostgreSQL migrationの一部は広い`except Exception: pass`で失敗を隠す。さらに`event_store/models.py`にORM modelが
重複定義されるが、aggregatorはraw SQLを使い、model import/利用経路は見つからない。

DDL / ORM / migrationの三重表現はdrift源である。Alembic等のversioned migrationをcanonicalにし、起動時は
revision不一致・migration failureをfail fastする。未使用ORM modelはqueryへ採用するか削除する。

### P2-1 — Staleness / TTL policyがdomainごとに不揃い

physical environmentは`channel_last_seen`と`ENV_STALE_SEC`を持ち、contextにもstale warningが出る。
biometricも一部freshnessを考慮する。対してweather、news、GAS、home、services等はreceived/source timestamp、
expires_at、context除外条件が統一されない。Backend projectionもBrain停止後に古い値を返し得る。

共通基底classを増やすより、各domain contractに`source_ts` / `received_at` / `expires_at`を要求し、
context builderとprojection mapperが同じfreshness判定関数を使う方が小さい。

### P2-2 — Mixin分割は行数を減らしたが、暗黙の巨大Brain protocolを作っている

MQTT、cognitive、startup、dashboard等のmixinは`self.world_model`、多数のfeature flag、optional subsystem、
loop、loggerを暗黙参照する。静的interfaceがなく、test harnessも多数の属性を手組みする。
これはCoding Agentが「大ファイルを分割した」時に生じやすい見かけ上の責務分離である。

全面DDD化は不要で、まず `MqttIngestPipeline` に明示dependencyを渡し、pure router/reducerとside-effect sinkを分ける。
domain repositoryやaggregate rootを増やすより、typed event envelopeとowner表の方がこのPJには効果が高い。

## 4. Topic / reducer到達性の結論

- `hems/#`と`zigbee2mqtt/#`のsubscribe範囲は広く、broker到達自体は概ね足りる。
- physical、home、weather、news、GAS、knowledge、shopping等の主要branchはrouterへ到達する。
- ただし「subscribe済み」は「reducer済み」ではなく、`hems/personal/mobile/*`が明確な反例である。
- event_storeは全branchを記録せず、意図的なsubsetだがdocがその境界を十分示さない。
- feature flagによりWorldModel更新後のfeedだけが無効になるbranchがあり、最新値とside effectのcoverageを分けて検証すべきである。

`docs/IMPLEMENTATION_MAP.md`のreducer/topic網羅確認はmobile実consumerを見逃しており、現状の「全到達」表現はout of dateである。

## 5. 既存event_store / outbox再利用判定

| 用途 | 現状再利用 | 理由 |
|---|---|---|
| Brainの物理sensor分析mart | 可 | 現在の主目的。loss許容度と容量を明記する必要あり |
| LLM decision / learning trajectory | 条件付き可 | Backendとのownerとglobal IDを整理する |
| Mobile durable outbox | 不可 | DB transaction連携なし、bufferがmemory、delivery stateなし |
| Canonical biometric observation store | Backendで可 | P1.1でsource ID/timestamp/provider/unique/hashを実装。producer配線は未実装 |
| 全MQTT audit log / replay log | 不可 | topic coverageが選択的で順序・offsetを保持しない |

拡張する場合も、Backendのtransactional outboxとBrain analytic event storeを同一概念にしない。
outboxはdelivery責務、event_storeは分析責務であり、共有するのはtyped event envelopeとglobal IDである。

## 6. 推奨実施順

1. **P0-1**: mobile ingress schema + durable outbox、非biometric reducer、biometric-bridgeへのcanonical合流。
2. **P0-2**: biometric wire schema golden test、latest upsertとobservation historyの分離。
3. **P1-1**: event count triggerをmonotonic revisionへ変更し、saturated ring testを追加。
4. **P1-3**: cycle snapshotからtimeseries / biometric history insertを除去。
5. **P1-4 / P1-6**: global event IDをfeedback、wake/sleep、automation、learningまで保持。
6. **P1-7 / P1-8**: versioned migration、table別retention、capacity budget。
7. owner / freshness matrixを`IMPLEMENTATION_MAP.md`へ反映し、Brain docのevent store説明を限定する。

P0修正時の重要な境界は、WorldModelを新たな永続SoTにしないこと、cycle snapshotを観測eventとして扱わないこと、
mobile biometricをBrainで再正規化しないことである。

## 7. Test gap

- fixed-size event ring saturation後もcycleが即時triggerされるtest
- Backend mobile webhookの実payloadがBrain reducerまたはbiometric canonical pathまで届くcontract test
- Brain biometric mapperの実JSONをBackend schemaへ通すgolden test
- 同一observation IDのretry / MQTT redeliveryがDB、learner、automationで一度だけ処理されるtest
- cycleを複数回回しても新MQTT観測なしではhistory rowが増えないtest
- EventWriter flush前crash、DB outage、restart後retryのfailure-injection test
- retention対象全tableとPostgreSQL migration failureのtest
- stale weather/news/home/serviceがcontext / Frontendへ無期限表示されないtest

### 7.1 Mock seamが隠している不整合

- `tests/test_dashboard_client_biometric.py`はHTTP session mockの手前でnested producer payloadだけを確認する。
- Backend biometric router testはBrain mapperを使わずflat payloadを手書きする。両testがgreenでもP0-2は残る。
- `tests/test_brain_mqtt_characterization.py`のevent writer / subsystemはmockであり、DB unique制約、flush前crash、
  downstream idempotencyを検証しない。
- cycle trigger testは`_last_event_count`をprimeした通常のlength増加だけで、固定長ringの置換を作らない。
- Backend snapshot transportはnon-2xxを呼出側へ強く伝播しないため、mock success seamがproduction silent failureを隠す。

unit mockを廃止する必要はない。producerの実payloadをconsumer schemaへ渡すcontract fixtureと、PostgreSQLを使う
少数のfailure-injection testを追加してseamを跨ぐ。

## 8. Documentation freshness

- `services/brain/CLAUDE.md`の「event-driven」は通常系では正しいが、ring saturation後のtrigger停止を反映しない。
- 同docのevent store「730d retention」は全tableへ適用されるように読めるが、実際はraw/decisionだけである。
- feedback Phase説明はBackend DBとの二重所有と`feedback_id`欠落を示さない。
- `docs/IMPLEMENTATION_MAP.md`はmobile topicをproducer側では扱う一方、Brain reducer欠落を未検出である。
- event_store ORM modelを「typed queryで利用」と説明する箇所があれば、raw SQL実装に合わせて削除または実装する必要がある。

これらはP0/P1修正と同時にcanonical docへ同期する。監査段階では事実を変えないため、本書以外のdocは編集していない。
