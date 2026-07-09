# メタ監査計画: 2026-05-25 リファクタ AUDIT-AUDIT

> **この doc の役割**: 直近リファクタリングの「監査文書 → refactor plan/ledger → 実コード commit →
> 後続補修」までを逆照合する `/goal` 自走メタ監査の in-repo SoT。
> 実コードは変更しない。成果物は findings-first の監査レポートのみ。

## Context

直近のサービス単位監査は [`docs/audit/2026-05-25/`](../../audit/2026-05-25/SUMMARY.md) に記録され、
その所見の実コード反映は [`PLAN.md`](PLAN.md) と [`LEDGER.md`](LEDGER.md) に沿って実施された。

本メタ監査は、元監査や refactor 実行の品質をもう一段上から監査する。目的は「リファクタが正しかったか」
だけではなく、「監査所見が過不足なかったか」「ledger と commit の主張が実コードと一致しているか」
「後続補修まで含めてリスクが閉じているか」を確認すること。

## Scope

対象:

- 監査文書: `docs/audit/2026-05-25/` の全 unit doc と `SUMMARY.md`
- 実行計画: `docs/refactor/2026-05-25/PLAN.md`
- 進捗記録: `docs/refactor/2026-05-25/LEDGER.md`
- 実装 commit: `LEDGER.md` の非 deferred `done` 行 33 件
- 後続補修: R7.1 shared-key auth 後に追加された `BACKEND_API_KEY` 配線 commit
  - `3636e18 feat(brain): BACKEND_API_KEY を全 brain→backend 呼び出しへ配線`
  - `f3d02e7 feat(infra): BACKEND_API_KEY を frontend nginx + compose env へ配線`
  - `878ed3a docs: BACKEND_API_KEY 配線完了を反映`

対象外:

- `deferred` 行そのものの実装着手
- 高 blast-radius tail の解消実装(R3.6 / W5 / W6)
- frontend/mobile の独立監査
- `feat/distribution` の配布ロードマップ本体。ただし refactor 完了状態への言及があれば整合性のみ確認する。

## Audit Axes

1. **元監査の妥当性**
   - P0=0 の主張が、後続実装や補修 commit と矛盾していないか。
   - P1/P2 の分類が影響度に対して過小/過大ではないか。
   - doc 乖離是正のみの監査 pass と、後続実コード refactor pass の境界が守られているか。

2. **ledger と commit の対応**
   - `LEDGER.md` の `done <sha>` と実 commit が対応しているか。
   - 1 row = 1 coherent change の原則が実質的に守られているか。
   - docs-only progress commit と実装 commit の順序・記述が追跡可能か。

3. **実コード反映の正確性**
   - 出所 audit doc の所見が、実装 commit で過不足なく反映されているか。
   - public API / env / runtime behavior の変更が、呼び出し側と docs に伝播しているか。
   - 旧名・旧契約・旧コメントが残っていないか。

4. **検証主張の妥当性**
   - baseline `1257 passed` から `1269 passed` への増分が、追加リスクに対応しているか。
   - auth / reducer / automation / provider hook など、挙動変更箇所に focused test があるか。
   - `make lint` / `make test-quick` の記録が、監査対象時点のコードに対して信頼できるか。

5. **deferred 判断の妥当性**
   - R3.6 / W5 / W6 を tail として deferred にした理由が、依存関係・blast radius から妥当か。
   - deferred によって残るリスクが docs に明示されているか。
   - deferred を除いて「非 deferred 全行完了」と呼んでよい状態か。

## Severity

- **A0**: 元監査または refactor 完了判定が破綻する誤り。完了扱いを撤回すべきもの。
- **A1**: doc-code 不整合、実装漏れ、呼び出し側未配線など、運用上の不具合につながるもの。
- **A2**: 検証不足、テスト不足、review boundary 不明瞭など、すぐ壊れてはいないが回帰検知が弱いもの。
- **A3**: 記述ノイズ、追跡性の悪さ、軽微な doc 表現のズレ。

各 finding は以下を必ず含める:

- severity
- 根拠となる doc path / commit / 実コード path
- 何が矛盾または不足しているか
- 影響
- 推奨 follow-up

## Execution Protocol

1. 現在地点を確認する。
   - `git status --short`
   - `git log --oneline --decorate --max-count=80`

2. 参照 doc を読む。
   - `docs/audit/2026-05-25/SUMMARY.md`
   - `docs/refactor/2026-05-25/PLAN.md`
   - `docs/refactor/2026-05-25/LEDGER.md`
   - 必要に応じて各 unit doc

3. ledger 全体を機械照合する。
   - `done` 行の sha が `git log` に存在するか。
   - `deferred` 行が本当に commit 対象外として残っているか。
   - R7.1 後続補修 commit が R7.1 の実装漏れを閉じているか。

4. high-risk row を重点精査する。
   - R0.1: `_llm_review` の `LLMResponse.content` 化と回帰 test
   - R1.3: `ShoppingState` の dead state 除去予定から live 化への方針変更
   - R3.1: `_ALLOWED_ACTIONS` 単一 SoT
   - R3.2: provider tool-call 整形共通化
   - R4.1: 共有 `aiohttp.ClientSession`
   - R7.1: backend shared-key auth と全 caller 配線
   - R7.2: hand-rolled migration の例外処理 narrowing
   - R8.2: VoiSona health hook の provider 移設

5. 旧契約・未配線・残骸を検索する。
   - 旧関数名、旧 alias、旧 env、旧 topic/doc 表現
   - `BACKEND_API_KEY` の read/write/call-site 全面配線
   - `AUTOMATION_ENGINE_ENABLED` の docs/env 整合
   - deferred 対象が「未完了」として分かる形で残っているか

6. 可能なら検証を実行する。
   - `source .venv/bin/activate && make lint`
   - `source .venv/bin/activate && make test-quick`
   - 実行できない場合は理由を report に記録する。

7. 監査レポートを作成する。
   - 出力先: `docs/refactor/2026-05-25/META_AUDIT_REPORT.md`
   - findings-first。A0/A1/A2/A3 の各 severity で、該当なしの場合も明示する。
   - 最後に「妥当と判断した範囲」「残リスク」「推奨 follow-up」を短くまとめる。

## Suggested Commands

```bash
cd "$(git rev-parse --show-toplevel)"
git status --short
git log --oneline --decorate --max-count=80
sed -n '1,140p' docs/audit/2026-05-25/SUMMARY.md
sed -n '1,230p' docs/refactor/2026-05-25/PLAN.md
sed -n '1,140p' docs/refactor/2026-05-25/LEDGER.md
rg -n "BACKEND_API_KEY|AUTOMATION_ENGINE_ENABLED|_summarize_action|generate_for_today|split_for_speak|_ALLOWED_ACTIONS" .
source .venv/bin/activate && make lint
source .venv/bin/activate && make test-quick
```

High-risk row inspection examples:

```bash
git show --stat --oneline 2a77241
git show --stat --oneline ac35b9e
git show --stat --oneline 1dd119b
git show --stat --oneline 8a5cf71
git show --stat --oneline 83bf149
git show --stat --oneline 404c569
git show --stat --oneline 3636e18
git show --stat --oneline f3d02e7
git show --stat --oneline 878ed3a
git show --stat --oneline cd47442
git show --stat --oneline 7da0623
```

## Report Template

Use this structure for `META_AUDIT_REPORT.md`:

```markdown
# メタ監査レポート: 2026-05-25 リファクタ AUDIT-AUDIT

## 結論

短い総合判定。

## Findings

### A0

- 該当なし / finding list

### A1

- finding list

### A2

- finding list

### A3

- finding list

## 妥当と判断した範囲

- 確認済みで問題なしと判断した主要領域。

## 検証

- 実行したコマンドと結果。
- 実行できなかったコマンドと理由。

## Follow-up

- 実コード修正が必要なもの。
- docs のみで閉じるもの。
- deferred tail として扱うもの。
```

## Completion Criteria

- `META_AUDIT_REPORT.md` が作成されている。
- A0/A1/A2/A3 が findings または「該当なし」で埋まっている。
- R7.1 後続の `BACKEND_API_KEY` 配線 commit まで監査対象に含まれている。
- deferred と対象外の境界が report に明記されている。
- 実コード変更をしていない。

## /goal Prompt

```text
/goal Execute the meta-audit described in docs/refactor/2026-05-25/META_AUDIT_PLAN.md. Do not change runtime code. Read the plan, audit docs, refactor PLAN/LEDGER, and the relevant commits. Create docs/refactor/2026-05-25/META_AUDIT_REPORT.md with findings-first A0/A1/A2/A3 sections, verification results, and follow-up recommendations. Include R7.1 BACKEND_API_KEY follow-up commits 3636e18, f3d02e7, and 878ed3a in scope. Stop when the report exists and explicitly states whether each severity has findings or none.
```
