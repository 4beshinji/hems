# data-bridge — Strava / Fitbit / Garmin 連携(実装予定)

このディレクトリは **Strava / Fitbit / Garmin / Intervals.icu / Mi Band Cloud / Google Fit** 等の SaaS からの運動・トレーニングデータ取込用に確保されている scaffold です。

## 実装方針(2026-06-11 決定)

**data-bridge は存続し実装する**。[`docs/feature-proposals-2026-06-11.md`](../../docs/feature-proposals-2026-06-11.md) の **C1. Strava / Fitbit / Garmin intake** として、リファクタリング計画([`docs/refactor/2026-06-11/PLAN.md`](../../docs/refactor/2026-06-11/PLAN.md)) の **W3.1(共有ライブラリ `services/_common`)** 完了後に実装着手予定。

最初の `_common` ベース新規ブリッジとして実装することで、共通ライブラリの scaffold 検証も兼ねる。

## 現在の代替(着手まで)

当初想定していた一部取込対象は、別ブリッジで既に代替済みです。

| 当初想定の取込対象 | 現在の代替 |
|--------------------|-----------|
| Mi Band / Amazfit / CMF Watch (Huami cloud) | `services/biometric-bridge/` (Health Connect / Gadgetbridge webhook) |
| Google Calendar / Tasks / Gmail | `services/gas-bridge/` (Apps Script Web App proxy) |
| Strava / Garmin / Fitbit (運動・睡眠) | **実装予定**(biometric-bridge では心拍・睡眠・歩数のみで、ワークアウト単位データ欠落) |
| Intervals.icu (トレーニング負荷) | **実装予定** |

## 実装ロードマップ

| Phase | 内容 | 優先度 | 時期 |
|-------|------|--------|------|
| W3.1 | `services/_common` 共有ライブラリ確立(MQTTPublisher / lifespan テンプレート / Config ローダ / verify_internal_token 統一) | P1 | 2026-06–07 月 |
| W3.2 | 既存 9 ブリッジを `_common` へ段階移行(weather → tapo → … → biometric) | P1 | 2026-07 月 |
| **data-bridge 実装** | `_common` ベース新規ブリッジ 1 本目(OAuth フロー + Strava/Fitbit/Garmin webhook 統一)。`hems/personal/training/fitness` へ運動データを publish | P2 | **2026-08 月以降、W3.1/W3.2 完了後** |

### 予約 MQTT トピック

実装時に publish される予定。現在は world_model に接続されておらず、MQTT テストで受信実績もありません。

- `hems/personal/training/fitness` — workout / load_score / recovery_time
- `hems/personal/training/metrics` — VO2max / FTP などのメトリック長期値
- 補助: `hems/services/data-bridge/bridge/status` — bridge 接続状態

### env.example の Phase 2 セクション

`env.example` 内の "Phase 2: data-bridge" コメントブロックは、実装開始時に活性化予定。
現在は commented out のままです。
