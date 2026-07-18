# HEMS 分割レビュー — 2026-07-18

対象リビジョン: `6310df0` (`main`)

## 目的

各コンポーネントを次の観点で、実際の producer から consumer / DB まで追跡して再監査する。

1. code / canonical doc / setup doc の鮮度と重複
2. DRY、二重計上、責務・デバイス・domain state の重複
3. 未配線、mock-only、stub、契約破綻、技術選定と Coding Agent 由来の負債
4. security、運用性、障害時のデータ保持、test seam

過去の監査結果は結論として再利用せず、現行 code で再検証する。単体テストの green ではなく、境界を跨ぐ実データパスを完了条件とする。

## 判定基準

| 等級 | 基準 |
|---|---|
| P0 | 正常応答に見えて主要データが消える、実データ契約が常時破綻する、または重大な安全性問題 |
| P1 | 二重計上、認証を有効化できない、障害時データ喪失、主要機能の通常利用不能 |
| P2 | 文書陳腐化、test / CI gap、保守性・技術選定負債 |
| P3 | 軽微な重複、命名、局所的 cleanup |

## 進捗

| # | 対象 | 状態 | 主要理由 | 報告書 |
|---|---|---|---|---|
| 1 | Android 生体・モバイル収集系 | Reviewed / fix design pending | 未監査、Health Connect 二重実装、silent drop、biometric contract mismatch | [android-biometric-mobile.md](android-biometric-mobile.md) |
| 2 | Backend persistence / domain ownership | Reviewed / P0-3 fixed, other urgent fixes pending | 複数 ingress、snapshot と observation の混在、PostgreSQL互換、非冪等更新 | [backend-persistence-domain.md](backend-persistence-domain.md) |
| 3 | Brain world model / MQTT / persistence | Next | reducer 到達性、同一 state の複数表現、cycle 起因の重複書込み | — |
| 4 | Biometric bridge / external health sources | Queued | Android 統合、dedup identity、provider placeholder | — |
| 5 | Edge / SensorSwarm / virtual edge | Queued | 未実装 transport、実機経路と mock/simulator の乖離 | — |
| 6 | STT / Voice | Queued | 旧監査で STT 対象外、provider fallback と実運用経路 | — |
| 7 | Frontend | Queued | server contract の重複表現、mock data panel、主要 UI test gap | — |
| 8 | Bridge 群 | Queued | 共通化後の責務重複、実データ源、HTTP/MQTT 二経路 | — |
| 9 | Infra / security / observability | Queued | config SoT、healthcheck の意味、実行時 secret / ACL / retention | — |
| 10 | data-bridge / orphan / research assets | Queued | 実装決定後も scaffold、予約 interface と実装進捗の整合 | — |

順序は重大所見の依存で変更する。Android / Backend の P0 は Brain / biometric-bridge の境界にも跨るため、次は Brain world model / MQTT / persistence を調査し、修正対象と既存 event store の再利用可否を確定する。

Backendレビューでは追加で、PostgreSQL既定構成に対するSQLite専用task stats SQL、既存PostgreSQL schemaを安全に更新できないstartup migrationをP0と判定した。これらはdomain設計を待たず独立修正できるが、PostgreSQLでの回帰testを先に追加する。

task stats SQLは2026-07-18に緊急修正済み。UTC awareなPython cutoff bindへ変更し、PostgreSQL dialectでSQLite固有`datetime()`が生成されないfocused testを追加した。startup migration（P0-4）を含む他所見は未修正。

## 第1レビューの扱い

Android 系では P0 2件、P1 5件を確認した。場当たり的な topic alias や nested object の文字列保存は行わない。次の順で修正する。

1. `MobileObservation` / `BiometricObservation` の wire contract、source timestamp、observation identity、canonical owner を設計する。
2. Brain producer の実 payload を Backend consumer へ通す contract test を追加する。
3. mobile MQTT の publish から Brain state / persistence までを通す integration test を追加する。
4. P0 修正後に Android HMAC、durable outbox、permission lifecycle、二つの APK の統合へ進む。

既存の 2026-06-11 監査・計画文書にある「replay 防御実装済み」「全 row 完了」は server-side の完了記録として保持し、end-to-end の未完事項は今回の報告書を正本として追跡する。実装修正時に旧文書へ status addendum を同期する。

## 共通検証ゲート

変更内容に応じて次を実行する。

```bash
make lint
make test-quick
cd services/frontend && pnpm test && pnpm build
cd services/mobile-android && ./gradlew test assembleDebug
cd apps/healthconnect-companion && ./gradlew test assembleDebug
```

Android は現時点で root CI 対象外かつ自動テスト未整備である。Gradle build 成功だけを contract 検証として扱わない。
