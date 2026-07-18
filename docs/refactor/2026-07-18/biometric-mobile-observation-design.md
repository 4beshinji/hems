# Biometric / Mobile Observation P0 Design — 2026-07-18

Status: proposed。入力は同日4監査。過剰設計を避け、既存FastAPI / SQLite / MQTT / PostgreSQLを維持する。

## 1. 決定

1. 正規化ownerは`biometric-bridge`一か所とする。BrainとBackend mobileにprovider parserを増やさない。
2. immutable observationの永続SoTはBackend DB、bridge SQLiteはdelivery用inbox/outbox、Brainはruntime latest cacheとする。
3. Frontend向けlatest projectionとimmutable observation historyを別contract・別保存責務にする。
4. Phase 0でP0-2（nested/flat不一致とcycle insert）を止血し、Phase 1でP0-1（mobile silent drop）とdeliveryを解決する。
5. Kafka、FHIR server、全面event sourcing、新DB serviceは導入しない。

## 2. 現行契約 → 正本契約

| 境界 | 現行 | 正本 |
|---|---|---|
| standalone Android → bridge | flat body、legacy HMAC | `BiometricObservationIn`、段階的strict HMAC |
| mobile Android → Backend | `MobileStateWebhookPayload.biometrics` | 同bodyを受理後、metric単位observationへ変換してprivate ingest |
| Backend → Brain | `hems/personal/mobile/biometrics`、silent drop | Backend outbox → bridge `/api/biometric/ingest` |
| bridge normalization | Gadgetbridge parserを全sourceで流用 | typed observation validation + source adapter |
| bridge → MQTT | metric値のみ、retained | 同topicにmetadata付きenvelope、legacy keyも維持 |
| Brain → Backend | nested cycle snapshot | 型付き`BiometricSnapshotIn`、latest projection専用 |
| Backend history | cycleごとにinsert | observation IDごとに一度だけinsert |

Canonical flow:

```text
external/mobile ingress -> bridge durable inbox -> normalize
 -> outbox(MQTT metric projection + Backend observation)
 -> Brain latest/rules                 -> Backend immutable history
 -> Brain cycle -> Backend latest projection only
```

## 3. Phase 0 — P0-2の安全な止血

互換性を壊さず、DB migrationなしで先に実施する。

1. Backendへ`BiometricSnapshotIn`を定義し、`POST /biometric/snapshot`の`dict`を置換する。
2. nested fieldを既存flat列へ明示mapする。dictをInteger列へ代入しない。
3. endpointは新rowを毎cycle追加せず、最新の一rowをupdateする。rowがなければ一度だけinsertする。
4. Brain mapperとBackend schemaで同じgolden JSON fixtureを使う。
5. transportはnon-2xxをwarning/metricへ出し、silent failureを止める。

これは暫定措置であり、既存`biometric_readings`をlatestとhistoryの両方に使い続ける設計ではない。
Phase 1後、snapshotは専用latest tableへupsertする。

Phase 0 acceptance:

- nested HR / SpO2をPOSTして200、DB型errorなし。
- 同じsnapshotを100 cycle POSTしてrow数が増えない。
- `/biometric/`は更新値を返す。
- flat legacy payloadは移行期間だけ受理しdeprecation logを出す。

## 4. Phase 1 — P0-1 / durable delivery

1. bridgeにinternal-token必須`POST /api/biometric/ingest`を追加する。
2. public webhookとprivate ingestは同じvalidation/normalization関数へ合流する。
3. Backend mobile webhookはdevice HMAC検証とmobile受理transactionを完了し、biometric deliveryをBackend outboxへ記録する。
4. workerがprivate ingestへretryする。直接同期HTTPしてmobile transactionを巻き戻さない。
5. bridgeはSQLite transactionで`inbox(observation_id UNIQUE)`と宛先別outboxを同時commitしてから2xxを返す。
6. bridge outbox workerがMQTTとBackend observation APIへretryする。
7. Backendは`observation_id UNIQUE`でhistoryを冪等insertする。
8. Brainはmetadataを保持し、同一IDのrule / wake / learner side effectを一度だけ実行する。

standalone Health Connectの複合batchは、HR sample、daily steps、sleep sessionなど時間意味が違うためadapterで複数observationへ分割する。

## 5. 最小schema

```text
BiometricObservationIn
  schema_version: Literal[1]
  observation_id: str                 # retryで不変
  provider: str                       # healthconnect|gadgetbridge|huami
  device_id: str | null
  source_ts: UTC datetime
  interval_start: UTC datetime | null
  interval_end: UTC datetime | null
  aggregation: sample|interval_sum|daily_total|session
  metrics: BiometricMetrics           # 1つ以上

BiometricMetrics
  heart_rate, resting_heart_rate, spo2, steps, calories,
  active_minutes, stress_level, sleep_duration_minutes,
  sleep_quality_score, hrv_ms, body_temperature, respiratory_rate

BiometricSnapshotIn
  schema_version: Literal[1]
  generated_at: UTC datetime
  provider: str
  bridge_connected: bool
  heart_rate, spo2, sleep, activity, stress, fatigue,
  hrv, body_temperature, respiratory_rate  # nested latest objects
```

Snapshotはobservation IDを持たず、historyへ書かない。各metricのsource freshnessが必要ならnested objectへ
`source_ts`を任意追加する。Observationは異なるaggregation/windowのmetricを一rowへ混ぜない。

MQTT topicは互換性のため当面変更しない:

```text
hems/personal/biometrics/{provider}/{metric}
{
  "schema_version": 1, "observation_id": "...", "provider": "...",
  "source_ts": "...Z", "aggregation": "sample", "metric": "heart_rate",
  "bpm": 72
}
```

既存`bpm` / `percent` / `count`等をtop-levelに残すので旧Brain reducerも読める。新consumerはmetadataを使う。

## 6. Failure semantics / security

- invalid schema/auth: 4xx、retryしない。DB unavailable / transient failure: 503、producerはretry。
- duplicate ID: 同じbodyなら2xx idempotent success。異なるbodyなら409。
- bridgeはinbox/outbox commit後だけ2xx。MQTT/Backend停止中もoutboxへ残す。
- outboxは指数backoff、attempt/error/next_attempt_atを保持する。24hで黙って削除せずdead-letter状態へ移す。
- MQTT retained replayはlatest更新可。ただし古い`sleep session`でwake side effectを再実行しない。
- HMAC順序はtimestamp window確認 → signature確認 → nonce atomic登録。invalid signatureでnonceを消費しない。
- `BIOMETRIC_WEBHOOK_SECRET`と`HEMS_INTERNAL_TOKEN`をproduction profileで必須化する。

Compatibility rollout:

1. Serverはlegacy body/HMACをwarning付きで受理し、新envelopeも受理する。
2. standalone Androidへobservation ID、timestamp、nonce署名をreleaseする。
3. adoption metric確認後`WEBHOOK_REPLAY_STRICT=true`をdefault化する。
4. MQTT metadata対応Brainを先にdeployし、その後bridge envelopeを有効化する。
5. legacy trafficがゼロになってからlegacy parserを削除する。

## 7. DB migration / rollback

Versioned migrationで以下を加算する。

- `biometric_readings`: `observation_id` nullable unique、`source_ts`、interval、aggregation、device_id、schema_version、received_at。
- 既存rowは`observation_id=NULL`, `aggregation=legacy_snapshot`。自動で観測へ推定変換しない。
- `biometric_latest`: singleton/profile key、typed payload JSON、generated_at、updated_at。
- Backend `biometric_delivery_outbox`: observation ID、payload、status、attempt metadata。
- bridge SQLite `inbox`とmulti-destination `outbox`。既存send queue rowはMQTT destinationとして移行する。

Rollbackは加算column/tableを残し、feature flagでlegacy snapshot/MQTTへ戻す。未送信outboxは削除しない。
`BIOMETRIC_CANONICAL_INGEST_ENABLED`と`BIOMETRIC_MQTT_ENVELOPE_ENABLED`を独立toggleにする。

## 8. 段階別acceptance tests

Phase 0:

- Brain実mapper JSON → Backend schema → PostgreSQL/SQLiteのcontract test。
- 100 cycleでrow数不変、latest値だけ更新。
- nested/flat compatibilityとdeprecation telemetry。

Phase 1A ingress:

- mobile HMAC受理 → Backend outbox → private ingest → bridge inboxまで同一ID。
- 同一ID retry/restartでinbox/history各1row。
- HTTP 2xx直後killでもoutboxが復旧するfailure injection。

Phase 1B delivery:

- MQTT/Backend outage後に再送し、source_ts/aggregationを末端まで保持。
- daily_total stepsをinterval_sumとして加算しない。
- retained/duplicate sleepでwakeとschedule learnerが一度だけ動く。
- invalid HMACはnonceを消費せず、strict Android golden requestが通る。
- rendered composeにstrict/Huami/dedup設定が渡る。

## 9. Documentation sync

実装時に次を同期する。

1. `docs/IMPLEMENTATION_MAP.md`（owner、API、topic envelope、outbox）
2. `docs/CLAUDE-bridges.md`
3. `services/brain/CLAUDE.md`、`services/backend/CLAUDE.md`
4. root `CLAUDE.md`、`env.example`
5. Android 2 appのREADMEとwire contract
6. `docs/audit/2026-07-18/{android-biometric-mobile,backend-persistence-domain,brain-world-model-persistence,biometric-bridge}.md`
7. 対応するPLAN / LEDGERへPhase 0/1 statusとtest evidenceを記録する。

Phase 0完了をPhase 1完了と表現しない。P0-2止血後もmobile silent dropとdelivery durabilityは未解決である。
