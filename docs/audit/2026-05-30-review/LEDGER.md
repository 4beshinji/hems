# LEDGER — HEMS de-bloat レビュー 2026-05-30

進捗台帳。各セッション完了時に該当行を更新する。

- **status**: `todo` → `wip` → `reviewed`(検出のみ完)→ `slimmed`(低リスク実装 + lint/pytest 緑 + 親 git diff 検証済)
- **P0/P1/P2**: 検出件数(深刻度別)。`-` は未着手
- **削減LOC(済/提案)**: 低リスク実装で削った行 / 構造変更提案での見込み行

再入: `git log --oneline -5` で最後の commit を確認 → status `todo` 先頭を選ぶ → 対応 dir の CLAUDE.md と
`docs/audit/2026-05-25/<baseline>.md` を読む → `REVIEW_PLAN.md` の該当 kickoff を新規セッションへ paste。

| # | session_id | group | status | P0 | P1 | P2 | 削減LOC(済/提案) | notes |
|---|---|---|---|---|---|---|---|---|
| 1 | brain-core-loop | brain | todo | - | - | - | - / - | notes/REVIEW-brain-core-loop.md |
| 2 | brain-world-model | brain | todo | - | - | - | - / - | notes/REVIEW-brain-world-model.md |
| 3 | brain-rules-automation | brain | todo | - | - | - | - / - | notes/REVIEW-brain-rules-automation.md |
| 4 | brain-tool-surface | brain | todo | - | - | - | - / - | notes/REVIEW-brain-tool-surface.md |
| 5 | brain-tool-handlers-devices | brain | todo | - | - | - | - / - | notes/REVIEW-brain-tool-handlers-devices.md |
| 6 | brain-persona-voice | brain | todo | - | - | - | - / - | notes/REVIEW-brain-persona-voice.md |
| 7 | brain-event-store-data | brain | todo | - | - | - | - / - | notes/REVIEW-brain-event-store-data.md |
| 8 | brain-scheduling-power | brain | todo | - | - | - | - / - | notes/REVIEW-brain-scheduling-power.md |
| 9 | backend-routers | backend | todo | - | - | - | - / - | notes/REVIEW-backend-routers.md |
| 10 | backend-persistence | backend | todo | - | - | - | - / - | notes/REVIEW-backend-persistence.md |
| 11 | frontend-avatar | frontend | todo | - | - | - | - / - | notes/REVIEW-frontend-avatar.md |
| 12 | frontend-dashboard | frontend | todo | - | - | - | - / - | notes/REVIEW-frontend-dashboard.md |
| 13 | frontend-data-layer | frontend | todo | - | - | - | - / - | notes/REVIEW-frontend-data-layer.md |
| 14 | voice | service | todo | - | - | - | - / - | notes/REVIEW-voice.md |
| 15 | perception | service | todo | - | - | - | - / - | notes/REVIEW-perception.md |
| 16 | stt | service | todo | - | - | - | - / - | notes/REVIEW-stt.md |
| 17 | bridge-smarthome | bridge | todo | - | - | - | - / - | notes/REVIEW-bridge-smarthome.md |
| 18 | bridge-ingestion | bridge | todo | - | - | - | - / - | notes/REVIEW-bridge-ingestion.md |
| 19 | bridge-external-data | bridge | todo | - | - | - | - / - | notes/REVIEW-bridge-external-data.md |
| 20 | bridge-personal | bridge | todo | - | - | - | - / - | notes/REVIEW-bridge-personal.md |
| 21 | bnd-mqtt-contract | boundary | todo | - | - | - | - / - | notes/REVIEW-bnd-mqtt-contract.md |
| 22 | bnd-http-rest | boundary | todo | - | - | - | - / - | notes/REVIEW-bnd-http-rest.md |
| 23 | bnd-tool-integrity | boundary | todo | - | - | - | - / - | notes/REVIEW-bnd-tool-integrity.md |
| 24 | bnd-config-env | boundary | todo | - | - | - | - / - | notes/REVIEW-bnd-config-env.md |
| 25 | bnd-data-schema | boundary | todo | - | - | - | - / - | notes/REVIEW-bnd-data-schema.md |
| 26 | periphery-character-auth | periphery | todo | - | - | - | - / - | notes/REVIEW-periphery-character-auth.md |
| 27 | periphery-infra-build | periphery | todo | - | - | - | - / - | notes/REVIEW-periphery-infra-build.md |
| 28 | infra-runtime-fixtures | periphery | todo | - | - | - | - / - | notes/REVIEW-infra-runtime-fixtures.md |
| 29 | periphery-edge-firmware | periphery | todo | - | - | - | - / - | notes/REVIEW-periphery-edge-firmware.md |
| 30 | periphery-mobile-kotlin | periphery | todo | - | - | - | - / - | notes/REVIEW-periphery-mobile-kotlin.md |

## ロールアップ(全セッション完了後に記入)

- P0 合計: —
- P1 合計: —
- P2 合計: —
- 削減 LOC 合計(実装済): —
- 削減 LOC 合計(提案): —
