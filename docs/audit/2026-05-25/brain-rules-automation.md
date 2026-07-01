# 監査: brain-rules-automation — 2026-05-25

## スコープ
- 対象 path(すべて `services/brain/src/`):
  - `rules/`: `config.py`(111)・`biometric.py`(348)・`gas.py`(402)・`home.py`(214)・`perception.py`(165)・
    `services.py`(119)・`shopping.py`(47)・`weather.py`(84)・`zigbee.py`(231)
  - `rule_engine.py`(846, facade)・`automation_engine.py`(379)・`event_automation.py`(518)・`scene_executor.py`(98)
  - 計 ~3,560 LOC
- **境界**: `device_dispatcher.py`(896)は計画 unit 4 が明示所有のため本 unit から除外(unit 3「scene/dispatch」は
  `scene_executor.py` までをカバー、vendor dispatch 本体は unit 4)。
- entry point: `RuleEngine.evaluate()` / `.evaluate_critical()`、`AutomationEngine.tick()`、`EventAutomation.trigger()`
- 参照 canonical doc: `services/brain/CLAUDE.md`、`docs/IMPLEMENTATION_MAP.md` §6 / §7

## doc 乖離(本パスで修正適用済)

| # | doc claim | code reality (file:line) | 修正先 doc | 状態 |
|---|---|---|---|---|
| 1 | §7.3 実装済 Action に `weather_alert_announce` が無い | `event_automation.py:43,180,447` に実装、`DEFAULT_AUTOMATIONS`(L30)では wake_up 先頭 action | IMPLEMENTATION_MAP §7.3 | ✅ 追記 |
| 2 | §6「`rule_engine.py` ベース」のみで rules/ 分割に言及なし | rule は `rule_engine.evaluate`(環境/PC/ライト inline)+ `rules/` の 8 ドメインミキシン。閾値も world_model 定数 + `rules/config.py` の二系統 | IMPLEMENTATION_MAP §6 intro | ✅ 注記追加 |
| 3 | §6.6 Verification が `rule_engine.py` のみ grep | ドメイン rule は `rules/*.py` の `_evaluate_*_rules` | IMPLEMENTATION_MAP §6.6 | ✅ rules/ grep 追加 |

## 命名所見(refactor-ready)

| 優先度 | current → proposed | file:line | 理由 |
|---|---|---|---|
| P2 | ~~`split_for_speak as _split_for_speak` → alias 撤去~~ → **実装済み** | event_automation.py:16 | `from brain_utils import SPEAK_CHUNK_LIMIT, split_for_speak` と直接 import |
| P2 | ~~`_dt = _rule_engine.datetime` → 直接 `from datetime import datetime`~~ → **実装済み**。rules ミキシンは `_rule_engine` facade 経由参照を解消 | rules/*.py | stdlib/`logger`/閾値は各 mixin で直接 import |
| P2 | ~~`morning_greeting` 切詰 `[:67]` の magic~~ → **実装済み**。全 speak 切詰を `SPEAK_CHUNK_LIMIT` に統一 | event_automation.py:192,303,403,421,456,457 | — |

## スコープ所見(refactor-ready)

| 優先度 | 問題 | file:line | 推奨 |
|---|---|---|---|
| P1 | ~~**namespace 結合 / 準循環 import**~~ → **実装済み**。rules 8 ミキシンの `_rule_engine.datetime`/`logger` 参照を解消し、各 mixin が直接 import。facade 経由の準循環を断つ | rules/*.py | — |
| P1 | ~~`RuleEngine.evaluate` が ~490 行の god-method~~ → **実装済み**。`evaluate`/`evaluate_critical` は各ドメインミキシンの `_evaluate_*_rules` を呼び出す thin orchestrator に | rule_engine.py | `rules/environment.py` / `rules/pc.py` ミキシンへ抽出済み |
| P1 | `AutomationEngine._llm_review` が `llm_client.chat()` の戻りを **str 扱い**(`(response or "").strip()` / `.splitlines()`)。他箇所(brain_cognitive / event_automation)は `response.content` / `.error` のオブジェクト。LLMResponse は str ではないため llm_review パスが破綻の可能性 | automation_engine.py:293-294 | `llm_client.chat` の戻り型に合わせ `response.content` を使う(**unit 4 で llm_client.chat 署名と要 cross-check**) |
| P2 | 閾値表現が 3 段(env → `RuleThresholds` dataclass → `rule_engine` モジュール UPPERCASE 定数 → `_rule_engine.X` 参照)で間接が深い。さらに world_model 定数(CO2_HIGH 等)と RuleThresholds の二重ソース | rule_engine.py:17-(world_model import) / rules/config.py | 閾値ソースを `RuleThresholds` 一本に集約 |
| P2 | ~~`scene_executor._fetch_all` が呼び出し毎に新規 `aiohttp.ClientSession`~~ → **実装済み**。`scene_executor.py:48` で `self.dashboard.session.get(...)` を使用 | scene_executor.py:42-57 | — |

## 可読性所見(refactor-ready)

| 優先度 | 問題 | file:line | 推奨 |
|---|---|---|---|
| P1 | ~~`evaluate` god-method~~ → **実装済み**(上記スコープ参照) | rule_engine.py | — |
| P2 | `_check_schedule` の cron は "M H * * *" のみ対応でワイルドカード不可。MVP コメントあるが doc(§7.1 "cron")は full cron を示唆 | automation_engine.py:194-211 | doc に「分・時のみ対応」を明記 or cron lib 採用 |
| P2 | `scene_executor.dashboard` は session 用途では使われず None-gate のみ(コメントは "future" stat bump) | scene_executor.py:23,27,36 | 用途整理 |
| P2 | EventAutomation の各 `_action_*` が speak 引数 dict を個別に組み立て(zone="home"/tone 固定が反復) | event_automation.py:256-518 | speak helper で重複削減 |

## 後続リファクタ推奨(優先度順サマリ)

- **P1**:
  1. ~~namespace 結合解消(unit 2 と共通): rules ミキシンの `_rule_engine.X` 参照を直接 import / 閾値注入へ。準循環 import を断つ~~ → **実装済み**。
  2. ~~`RuleEngine.evaluate` の inline 環境/PC rule を `rules/environment.py`・`rules/pc.py` へ抽出し god-method を解消~~ → **実装済み**。
  3. ~~`AutomationEngine._llm_review` の戻り値型バグ疑い(str vs LLMResponse)を unit 4 の llm_client 署名と照合して是正~~ → **実装済み**(`automation_engine.py:296` `response.content`)。
- **P2**:
  - 閾値ソースを `RuleThresholds` 一本化(world_model 定数との二重を解消)。
  - ~~scene_executor の共有 session 利用~~ → **実装済み**(`scene_executor.py:48`); cron 制約の doc 明記・speak helper 抽出は未対応。
- **P0**: `_llm_review` 戻り値型は llm_review モード使用時のみ影響。デフォルト mode=direct のため常時破綻ではないが、要確認 P1。
