# AUDIT.md (jisei-roku) フォローアップ — 2026-05-16

> リポジトリ root の `AUDIT.md` は `~/code/claude/jisei-roku` 由来の
> cross-workspace meta レビュー。本 doc は **現 hardening 作業との関係**
> を明文化し、両 branch 間の責務を分離する。

## 関連 branch / doc

| 軸 | branch | 一次 doc | 状況 |
|---|---|---|---|
| **進行中**: 実運用ハーデニング | `hardening/p0-impl` (本 branch) | `docs/hardening-audit-2026-04.md` | P0 (MQTT ACL / pickle / port 縛り等) 実装中 |
| **後追い**: AUDIT.md hygiene 対応 | `chore/audit-p0-hygiene` | `AUDIT.md` + 個別 commit | 2026-05-16 切り出し済 (commit `286b99d`)、P0 のみ実施済 |
| **詳細プラン** (local-only) | — | `~/.claude/plans/audit-md-valiant-breeze.md` | P0–P3 を ROI 順で整理、本 session 内で承認済 |

## 重複しない分担

| AUDIT.md 指摘 | hardening doc 守備範囲か | どこで対処するか |
|---|---|---|
| MQTT 匿名許可 (ACL) | ✅ hardening P0-1 | `hardening/p0-impl` (済 / 進行中) |
| pickle RCE (knowledge-bridge) | ✅ hardening P0-2 | `hardening/p0-impl` |
| ポート 0.0.0.0 → localhost | ✅ hardening P0-3 | `hardening/p0-impl` |
| HMAC replay 防御 | ✅ hardening P1 帯 | `hardening/p0-impl` |
| `config/zigbee2mqtt/secret.yaml` "ペアリング鍵漏洩" | ❌ AUDIT 独自 (誤判定) | `chore/audit-p0-hygiene` 済 |
| `os.getenv` 散在 / `pydantic-settings` 未採用 | ❌ AUDIT 独自 | 別 branch (P1, 未着手) |
| Alembic 未採用 / `ALTER TABLE` f-string | ❌ AUDIT 独自 (一部 hardening P3-1 と接点) | 別 branch (P2, 未着手) |
| ADR 不在 | ❌ AUDIT 独自 | 別 branch (P2, Opus 手作業) |
| ライセンス境界 | ❌ AUDIT 独自 | 別 branch (P3) |
| loguru 統一 | ❌ AUDIT 独自 | 別 branch (P3) |

## secret.yaml の "誤判定" について

詳細は `docs/security/secret-yaml-clarification.md` (chore/audit-p0-hygiene 上)。
要約: ファイル中身は `mqtt_password: ""` の deprecated stub で実害なし。
gitignore + `.example` 化のみ実施、`git filter-repo` での履歴書き換えは
public remote の force-push コスト > 得られる清浄性のため見送り。

## 推奨マージ順序

1. `hardening/p0-impl` を main にマージ (進行中作業を仕上げる)
2. `chore/audit-p0-hygiene` を main の最新にリベースしてマージ
   - 2 つの branch は触るファイルが重ならないため conflict は出ない見込み
   - `.gitignore` のみ両方が触っているが、AUDIT 側は zigbee/env-bak/tmp_recovery セクションを追加するだけなので textually 隣接しない
3. AUDIT P1 以降 (pydantic-settings、Alembic、ADR) は別 branch で順次

## 非スコープの再確認

- 本 hardening branch で AUDIT 系の追加コミットを混ぜない (P0 hygiene は分離済、P1 以降は別 branch)
- 進行中 hardening の review 粒度を保つために AUDIT 系の commit は混入させない
