# docs/audit — 監査記録インデックス

HEMS の監査パスを時系列で記録するディレクトリ。各パスは独立したサブディレクトリに per-unit/per-session の
所見(P0/P1/P2 + `file:line`)と進捗台帳を持つ。

| パス | 軸 | 範囲 | 状態 |
|---|---|---|---|
| [`2026-05-25/`](2026-05-25/README.md) | 命名 / スコープ / 可読性 / doc 乖離 | 全 Python サービス(brain 4 分割 + backend + perception + voice/stt + bridge 9)、計 16 unit + SUMMARY | 完了。doc 乖離是正済(コード無改変) |
| [`2026-05-30-review/`](2026-05-30-review/README.md) | **de-bloat 主軸**(dead-code / duplication / god-function / over-engineering / bad-knowhow)+ 従でフル監査 | 全 30 クリーンセッション(brain 8 / backend 2 / frontend 3 / service 3 / bridge 4 / boundary 5 / periphery 5)。2026-05-25 を baseline に見落とし補完 + frontend/stt/boundary/periphery を net-new | 計画策定済。kickoff prompt 30 + 進捗台帳。実行は LEDGER 順 |

## 関連

- リファクタ実行台帳: [`../refactor/2026-05-25/LEDGER.md`](../refactor/2026-05-25/LEDGER.md)
- SoT: [`../IMPLEMENTATION_MAP.md`](../IMPLEMENTATION_MAP.md) / [`../CLAUDE-bridges.md`](../CLAUDE-bridges.md)
- 技術的負債監査: [`../technical-debt-audit-2026-05-24.md`](../technical-debt-audit-2026-05-24.md) / [`../technical-debt-followups-2026-05-25.md`](../technical-debt-followups-2026-05-25.md)
