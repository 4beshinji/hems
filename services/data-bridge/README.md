# data-bridge — Phase 2 Placeholder

このディレクトリは将来の **Strava / Fitbit / Garmin / Intervals.icu / Mi Band Cloud / Google Fit** 等
SaaS データ取込用に確保されている scaffold です。`src/bridges/` は意図的に空です。

## 現在の代替

当初想定していた取込対象は、ほぼ別ブリッジで代替済みです。新規の SaaS 連携が必要になるまで、
この placeholder のままにしておきます (削除しない理由は同じ scaffold を後で再利用するため)。

| 当初想定の取込対象 | 現在の代替 |
|--------------------|-----------|
| Mi Band / Amazfit / CMF Watch (Huami cloud) | `services/biometric-bridge/` (Health Connect / Gadgetbridge webhook) |
| Strava / Garmin / Fitbit (運動・睡眠) | biometric-bridge (Health Connect 経由でほぼ網羅) |
| Google Calendar / Tasks / Gmail | `services/gas-bridge/` (Apps Script Web App proxy) |
| Intervals.icu (トレーニング負荷) | 未代替。再開時はここに実装する候補 |

## 関連 MQTT トピック (未配信)

CLAUDE.md / IMPLEMENTATION_MAP に記載されている下記トピックは、本ブリッジ未稼働により
現在 **published されていません** 。実装再開する際の予約名前空間として残してあります。

- `hems/personal/calendar/{id}/events`
- `hems/personal/training/fitness`
- `hems/system/gpu/utilization`

## env.example の Phase 2 セクション

`env.example` 内の "Phase 2: data-bridge" コメントブロックは未稼働のまま残してあります。
実装再開時にコメントアウトを外してください。

## 削除しない理由

- compose 統合・依存追加・MQTT トピック予約をまとめて再現する手間を避けるため
- biometric-bridge / gas-bridge で代替できない SaaS (Strava・Intervals.icu の運動負荷推定など)
  を後で取り込む可能性があるため
