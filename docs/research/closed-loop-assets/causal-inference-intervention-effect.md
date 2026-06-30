# Causal Inference & Intervention Effect — HEMS 調査レポート

## 概要

**Causal Inference & Intervention Effect（因果推論と介入効果）** は、HEMS の閉 loop

```
観測 → 意思決定 → 実行 → 結果観測 → 学習 → 次の意思決定
```

を「ただ予測する」システムから「**自分の行動が環境に与えた影響を定量化する**」システムへ引き上げるための概念群・手法群である。本トピックが解くべき核心問題は以下の通り。

1. **相関と因果の分離**: 室温が上がっているからエアコンを入れる、ではなく「エアコンを入れたことで、どれだけ快適帯に近づいたか」を測る。
2. **反実仮想の推定**: 実際には行わなかった行動（例：加湿器を出さなかった場合の湿度）をデータから補完し、比較対照とする。
3. **異質性の活用**: 同じ介入でも、在室/不在、睡眠中/作業中、季節、生体状態によって効果が変わる。誰に・いつ介入すべきかを個別に推定する（CATE / Uplift）。
4. **オフライン方策評価・学習**: 新しい自動化ルールや LLM 方策を、実際にデプロイする前に過去ログから安全に評価し、改善する（OPE / Policy Learning）。
5. **閾値・ルールの因果的再較正**: 介入効果の測定結果を `RuleThresholds` や `AutomationRule` にフィードバックし、閾値・クールダウン・持続時間を自動調整する。

HEMS はすでに `intervention_efficacy` テーブル（`services/brain/src/event_store/database.py`）と `efficacy.py` で「介入前後のメトリクス比較（baseline → post）」を行っている。しかしこれは相関的な before-after に留まり、交絡変数の統制、反実仮想の推定、 heterogeneous treatment effect、方策レベルの評価には未対応である。本レポートでは、これらを埋めるための概念、論文、ツール、アーキテクチャ変更案を網羅的にまとめる。

## 核心概念

### 1. Potential Outcomes / Rubin Causal Model

各「介入」`T`（例: エアコンの ON/OFF、加湿器の ON/OFF）に対し、個体（ここでは「時刻 t の部屋・住人」）の潜在的結果を

- `Y(1)`: 介入した場合の結果
- `Y(0)`: 介入しなかった場合の結果

とする。観測される結果は `Y = T·Y(1) + (1-T)·Y(0)` の一方のみ。因果効果は個体レベル（ITE）では `Y(1) - Y(0)`、集団レベル（ATE）では `E[Y(1) - Y(0)]`、条件付き（CATE）では `E[Y(1)-Y(0) | X=x]` となる。

HEMS では `X` に時刻、在室、外気温、室内温度、湿度、CO₂、生体情報、前回のデバイス状態などが入る。

### 2. Structural Causal Model（SCM）と do-calculus

Pearl の枠組みでは変数間の因果構造を有向非巡回グラフ（DAG）で表し、介入を `do(T=t)` と表現する。観測分布 `P(Y | T=t)` と介入分布 `P(Y | do(T=t))` は一般には一致しない。識別可能な場合、do-calculus や back-door criterion を用いて `P(Y | do(T=t))` を観測データから計算する。

HEMS における DAG の例:

```
外気温 → 室温 → エアコンON → 室温'
在室 → 室温, CO₂
睡眠中 → 心率, 室温感覚
エアコンON ← ルール/LLM ← 室温, CO₂
```

### 3. 識別のための主要仮定

| 仮定 | 内容 | HEMS での課題 |
|------|------|---------------|
| **Unconfoundedness** | 処置と結果に同時に影響する未観測交絡 `U` がない | ユーザーの意図・天気・在室の一部は観測できるが、疲労・気分などは未観測になりがち |
| **Positivity / Overlap** | あらゆる文脈で各処置を受ける確率が 0 でない | 危険な状態ではルールが必ず介入するため、propensity score が 0 近傍になりやすい |
| **Consistency** | 処置の定義が明確で、異なる形の同じ介入が混在しない | 「エアコンつけて」が温度設定 26℃ と 28℃ で異なる処置として記録される必要がある |
| **No interference** | ある時刻の介入が他の時刻/部屋に影響しない | 同じエアコンが複数部屋に影響、または連続処置の持続効果があり、違反しやすい |

### 4. 効果推定の代表的手法

| 手法 | 概要 | HEMS への適合性 |
|------|------|-----------------|
| **S-Learner / T-Learner / X-Learner** | 結果予測モデルを条件付きで学習し、処置有無の予測値差を効果とするメタ学習器 | 実装が容易。EconML / CausalML に実装あり。単一介入を想定する場合に有効 |
| **R-Learner (DML)** | 処置予測・結果予測の 2 つの残差を用いて効果モデルを推定。高次元共変量に強い | センサー数が多い HEMS に適する。EconML の `NonParamDML` など |
| **Doubly Robust (AIPW)** | 傾向スコアと結果モデルの両方を組み合わせ、片方が正しければ不偏 | 安全性が高い。DoWhy / EconML で利用可能 |
| **Causal Forests** | 効果 heterogeneity を木アンサンブルで推定し、信頼区間も出力 | 在室/時間帯ごとの効果差を自動発見。EconML `CausalForestDML` |
| **Difference-in-Differences (DiD)** | 介入群と対照群の時間方向の変化差分を効果とする | HEMS の before-after 評価を正当化する最も身近な拡張。季節調整と組み合わせる |
| **Synthetic Control** | 介入対象の偽の対照系列を複数未介入系列で合成 | 1 住戸しかない HEMS では外部データ（気象データなど）を使う簡易版が使える |
| **G-computation / Marginal Structural Model** | 時系列処置系列の累積効果を推定 | 連続するエアコン/照明制御の長期効果を評価したい場合に有効 |

### 5. Off-Policy Evaluation（OPE）と Contextual Bandits

HEMS は毎サイクル（30 秒）に文脈 `X_t` を観測し、行動 `A_t`（介入の有無・強度）を選択し、報酬 `R_t`（快適性 + エネルギー効率など）を得る。これは Contextual Bandit としてモデル化できる。

- **Logging policy**: 現在のルール / LLM が実際に選択した行動の確率 `π_b(a|x)`（propensity）。
- **Target policy**: 評価したい新しい方策 `π_e(a|x)`。
- **IPS**: `E[R · π_e(A|X)/π_b(A|X)]` で期待報酬を推定。
- **SNIPS**: IPS を正規化して分散を抑制。
- **DR**: 結果モデルをコントロール変数に加えた推定量。

OPE により、新しい自動化ルールを安全に A/B テスト前に評価できる。

### 6. Causal Reinforcement Learning

通常の RL は「報酬が最大になる行動系列」を学習するが、因果 RL は SCM や do-calculus を組み込み、未観測交絡への頑健性、方策変更時の外挿、反実仮想シミュレーションを可能にする。HEMS では「エアコン → 室温」などの部分的な因果知識を環境モデルに組み込むことで、サンプル効率と安全性を高められる。

### 7. Uplift Modeling / Heterogeneous Treatment Effect

広告・医療で発展した Uplift Modeling は、介入しなければ起きなかった結果と介入した結果の差（uplift）を個体ごとに推定する。HEMS では

- Persuadables: 介入しないと不快なままで、介入すると快適になる状態
- Sure things: どちらにしろ快適になる状態
- Lost causes: どちらにしろ不快なままの状態
- Sleeping dogs: 介入すると逆に不快になる状態

を区別し、無駄な介入や逆効果な介入を避ける。

### 8. Counterfactual Explanation

「エアコンをつけたから室温が 2℃ 下がった」ではなく「エアコンをつけなかった反実仮想では、室温は 0.5℃ しか下がらなかった」という説明を生成することで、ユーザーの信頼と介入の正当事化を高める。

## 論文・先行研究

### 基礎・サーベイ論文

| タイトル | 著者 | 年 | 要点 | HEMS 応用可能性 | 情報源 |
|----------|------|-----|------|-----------------|--------|
| **Causal Inference in Statistics: A Primer** | Pearl, Glymour, Jewell | 2016 | do-calculus、因果グラフ、back-door criterion、counterfactual の入門書 | HEMS 全体の因果モデリングの共通言語 | 書籍 |
| **Causality: Models, Reasoning, and Inference** (2nd ed.) | Judea Pearl | 2009 | SCM、do-calculus、識別理論の決定版 | システム設計の理論的基盤 | 書籍 |
| **Causal Inference: What If** | Hernán, Robins | 2020 | 潜在結果モデル、G-computation、 Marginal Structural Models、観察研究の実践的指針 | 時系列介入効果の推定と実装指針 | 書籍 |
| **Estimating Causal Effects of Treatments in Randomized and Nonrandomized Studies** | Donald B. Rubin | 1974 | 潜在結果モデルの原典 | HEMS における counterfactual 比較の基礎 | J. Educ. Psychol. 66(5) |
| **Causal Machine Learning: A Survey and Open Problems** | Kaddour, Lynch, Liu, Kusner, Silva | 2022 | Causal supervised learning、generative modeling、explainability、fairness、causal RL の包括サーベイ | 技術選定のマップ | arXiv:2206.15475 |
| **Towards Causal Representation Learning** | Schölkopf, Locatello, Bauer, Ke, Kalchbrenner, Goyal, Bengio | 2021 | 高次の因果変数を低次観測から学ぶ問題設定 | 生体・環境センサーから「快適度」などの潜在変数を学ぶ視点 | arXiv:2102.11107 |
| **A Unified Survey of Heterogeneous Treatment Effect Estimation and Uplift Modeling** | Zhang, Li, Liu | 2021/2022 | HTE と Uplift Modeling を potential outcome 枠組みで統一 | HEMS の個別介入効果推定の手法選定 | arXiv:2007.12769、ACM Computing Surveys 54(8) |
| **A Survey on Causal Inference** | Yao, Chu, Li, Li, Gao, Zhang | 2021 | 因果推論全体のサーベイ | 全体俯瞰 | ACM TKDD 15(5):74 |
| **Causal Reinforcement Learning: A Survey** | Deng, Jiang, Long, Zhang | 2023 | 因果性を RL に組み込むアプローチを分類・整理 | HEMS の sequential decision 強化の方向性 | arXiv:2307.01452 |

### 効果推定手法

| タイトル | 著者 | 年 | 要点 | HEMS 応用可能性 | 情報源 |
|----------|------|-----|------|-----------------|--------|
| **Metalearners for Estimating Heterogeneous Treatment Effects Using Machine Learning** | Künzel, Sekhon, Bickel, Yu | 2019 | S/T/X-Learner を体系化 | 実装の第一選択 | PNAS 116(10) |
| **Quasi-Oracle Estimation of Heterogeneous Treatment Effects** | Nie, Wager | 2021 | R-Learner を提案。高次元共変量で優位 | センサー特徴量が多い HEMS に適する | Biometrika 108(2) |
| **Estimation and Inference of Heterogeneous Treatment Effects Using Random Forests** | Wager, Athey | 2018 | Causal Forest で CATE と信頼区間を同時推定 | 在室/時間帯ごとの効果 heterogeneity を発見 | JASA 113(523) |
| **Recursive Partitioning for Heterogeneous Causal Effects** | Athey, Imbens | 2016 | 介入効果 heterogeneity を再帰的分割 | ルール条件の自動発見 | PNAS 113(27) |
| **Optimal Doubly Robust Estimation of Heterogeneous Causal Effects** | Edward H. Kennedy | 2020 | 最適な二重ロバスト推定 | 頑健な効果推定 | arXiv:2004.14497 |

### 観察データ・推薦系・時系列介入

| タイトル | 著者 | 年 | 要点 | HEMS 応用可能性 | 情報源 |
|----------|------|-----|------|-----------------|--------|
| **Estimating the Causal Impact of Recommendation Systems from Observational Data** | Sharma, Hofman, Watts | 2015 | 観察ログから推薦システムの因果効果を楽器変数で推定 | HEMS の「提案/アナウンス」がユーザー行動に与えた効果の測定 | ACM EC 2015 / arXiv:1510.05569 |
| **Robust Nonparametric Difference-in-Differences Estimation** | Lu, Nie, Wager | 2019 | 非パラメトリック DiD | 介入前後のセンサー変化を季節対照と比較 | arXiv:1905.11622 |
| **Machine Learning and Causal Inference for Policy Evaluation** | Susan Athey | 2015 | 政策評価のための ML × 因果推論 | 方策評価の基礎 | KDD 2015 Tutorial |

### スマートホーム・BEMS・RL 応用

| タイトル | 著者 | 年 | 要点 | HEMS 応用可能性 | 情報源 |
|----------|------|-----|------|-----------------|--------|
| **Deep Reinforcement Learning for Building HVAC Control: A Survey** | Dong, Li, Rahman | 2023 | HVAC 制御への DRL の包括レビュー | HEMS の HVAC/照明統合制御の設計指針 | Building Simulation 16(2):193-211 |
| **Exploring Deep Reinforcement Learning for Holistic Smart Building Control** | (OCTOPUS) | 2024 | HVAC・照明・ブラインド・窓を統合した DRL 制御 | HEMS の複数デバイス同時制御の先行例 | ACM e-Energy 2024 / doi:10.1145/3656043 |
| **Interpretable Fuzzy Control for Energy Management in Smart Buildings Using JFML-IoT and IEEE Std 1855-2016** | Martínez-Rojas et al. | 2025 | ESP32 + MQTT + ファジー推論で省エネ制御 | HEMS edge 層との親和性が高い | MDPI Appl. Sci. 15(15):8208 |
| **Integration of IoT in Smart Building Systems** | Lepcha et al. | 2025 | MQTT + Python + NodeRED + 時系列 DB で 90 日間の建物運用データを収集・制御 | HEMS の基盤アーキテクチャと類似 | Archives for Technical Sciences 34(3):850-860 |
| **Reinforcement Learning Approaches for Intelligent Control of Smart Building Energy Systems with Real-Time Adaptation to Occupant Behavior and Weather Conditions** | Qiu et al. | 2025 | DQN + attention で居住者行動・天気に適応し、平均 27.3% 省エネを報告 | HEMS の「観測→学習→制御」閉 loop の強化例 | JCEIM 2025, doi:10.54097/hr81cg02 |
| **Deep Reinforcement Learning for Smart Building Energy Management** | Yu et al. | 2020 | スマートビルエネルギー管理の DRL サーベイ | 基礎用語と代表的アルゴリズム（DQN/DDPG/PPO 等）の整理 | arXiv:2008.05074 |

## OSS・商用ツール・フレームワーク

### Python 因果推論ライブラリ

| 名前 | URL | 特徴 | HEMS への流用可否 |
|------|-----|------|-------------------|
| **DoWhy (PyWhy)** | https://py-why.github.io/dowhy/ | 因果モデル構築 → 識別 → 推定 → 仮説反駁（refutation）の一連を統合。GCM（Graphical Causal Models）もサポート。EconML/CausalML/scikit-learn と連携 | **最も推奨**。介入効果の信頼性検証（placebo test、unobserved confounder sensitivity）を自動化できる |
| **EconML** | https://github.com/py-why/EconML | Microsoft Research 発。DML（R-Learner）、Causal Forest、Orthogonal Random Forest、Meta-learners、IV、Dynamic DML、policy interpreter などを実装。信頼区間付き | CATE 推定の主力。`CausalForestDML` や `LinearDML` を HEMS の特徴量に適用 |
| **CausalML** | https://github.com/uber/causalml | Uber 発。Uplift Tree / Random Forest、meta-learners、neural-based CATE、multiple treatments、cost optimization | 複数デバイス候補から最も効果の高い介入を選ぶ「uplift」用途に最適 |
| **causal-learn** | https://github.com/py-why/causal-learn | 因果発見（PC, GES, FCI, NOTEARS, Lingam 等）を実装 | センサー・天気・デバイス状態から因果 DAG を学習し、do-calculus の入力に使う |
| **pgmpy** | https://github.com/pgmpy/pgmpy | ベイジアンネットワーク・SCM・do-calculus・シミュレーション | 学習した DAG に対する介入シミュレーションと反実仮想生成に使える |
| **statsmodels / scikit-learn** | https://www.statsmodels.org / https://scikit-learn.org | 傾向スコア、回帰不連続、DiD、重回帰 | ベースライン実装に最適。依存が軽い |

### 方策学習・オンライン学習

| 名前 | URL | 特徴 | HEMS への流用可否 |
|------|-----|------|-------------------|
| **Vowpal Wabbit** | https://vowpalwabbit.org/ | Microsoft Research 発の高速オンライン学習ライブラリ。Contextual Bandits、対照実験、OPE をネイティブサポート | 30 秒サイクルでのオンライン方策更新や ε-greedy 探索に流用可能。C++ 実装で軽量 |
| **Ray RLlib / Stable-Baselines3** | https://docs.ray.io/en/latest/rllib/ / https://stable-baselines3.readthedocs.io | DQN/DDPG/PPO などの RL フレームワーク | HVAC/照明の連続制御をシミュレーションで学習する場合に検討。本番投入は重い |
| **River** | https://riverml.xyz/ | オンライン学習・ドリフト検知 | HEMS における特徴量分布の変化を監視し、因果モデルの再学習トリガーに使える |

### 商用・実世界先例

| 名前 | 概要 | HEMS への示唆 |
|------|------|---------------|
| **Nest Learning Thermostat / Ecobee eco+** | 在室予測・気象・生活パターンから設定温度を学習・最適化 | 家庭向けデバイスでの省エネ・快適性トレードオフの実用例 |
| **causaLens** | 企業向け Causal AI プラットフォーム（因果発見・効果推定・最適化） | 大規模商用ツールの機能マップの参考。HEMS 規模では OSS で代替 |

## HEMS への適用案

### 1. アーキテクチャ全体像

```
MQTT sensors / devices / biometrics / PC / weather / calendar
        │
        ▼
┌─────────────────────────────────────────────┐
│  services/brain/src/world_model/world_model  │
│  （現在の状態を集約）                         │
└─────────────────────────────────────────────┘
        │
   ┌────┴────┐
   ▼         ▼
RuleEngine  LLM ReAct loop
   │         │
   └────┬────┘
        ▼
  Causal Decision Layer（新規）
  - PropensityModel
  - EffectEstimator（CATE/ATE）
  - PolicyEvaluator（OPE）
  - PolicyLearner（Contextual Bandit）
        │
        ▼
  Actuator / Scene / AutomationRule
        │
        ▼
  DeviceActionLog / intervention_efficacy / causal_estimates
        │
        ▼
  Feedback → RuleThresholds / AutomationRule / RulePromoter / AckLearner
```

### 2. 既存資産との接続

HEMS はすでに以下の学習・記録機構を持つ。因果層はこれらを拡張・橋渡しする。

- `RuleThresholds`（`services/brain/src/rules/config.py`）: ルールエンジンの静的閾値セット。因果層から閾値の動的再較正を受け取る。
- `AutomationRule`（`services/backend/models.py`）: トリガー・アクション・クールダウンを保持。効果測定対象の結果変数と測定窓を追加する。
- `RulePromoter`（`services/brain/src/annotator/rule_promoter.py`）: LLM 分類キャッシュの昇格。因果層で「高い介入効果を持つルール条件」を `promoted` ルールとして昇格可能。
- `AckLearner`（`services/brain/src/voice_capsule/ack_learner.py`）: voice capsule の再生タイミング学習。同様に介入効果を考慮した最適リマインダー時刻の推定に拡張可能。
- `intervention_efficacy`（`services/brain/src/event_store/database.py`, `services/brain/src/efficacy.py`）: 環境タスクの baseline/post 判定。これを propensity-weighted / DiD / CATE に拡張する。
- `raw_events`, `llm_decisions`, `device_action_log`, `world_events`: 因果推定の訓練データ源。

### 3. 代表的ユースケース

| 介入（Treatment） | 結果（Outcome） | 交絡共変量（X/W） | 推定したい効果 |
|-------------------|---------------|-------------------|--------------|
| エアコン ON / 温度設定 | 室温の快適帯への収束度、消費電力 | 外気温、在室、時刻、日射、前回設定温度 | この状況で何度設定すれば最も省エネかつ快適か |
| 加湿器/除湿器 ON | 湿度の快適帯収束 | 外気湿度、室温、換気状態、在室 | 加湿/除湿の効果と最適運転時間 |
| 換気（窓開け/換気扇） | CO₂ 濃度低下 | 在室人数、部屋面積、外気 CO₂、風速 | 換介入の効果と必要時間 |
| カーテン/ブラインド制御 | 室温上昇抑制、照度 | 日射角、外気温、在室 | 日差し遮りの冷却効果 |
| 照明シーン変更 | 照度、快適度、消費電力 | 時刻、在室、外光 |  Circadian 照明の効果 |
| リマインダー/アナウンス | タスク完了率、ack 遅延 | 時刻、認知負荷、生体情報 | アナウンスが行動変容に与えた効果 |

### 4. 推定フロー例（エアコン介入）

1. **データマート構築**: `raw_events`（温度・湿度・CO₂・在室）、`device_action_log`（エアコン ON/OFF・設定温度）、`world_events`（天気・外気温）を時系列で結合。
2. **介入定義**: `T=1` を「エアコン ON かつ設定温度 26℃ 未満」、`T=0` を「エアコン OFF」として定義（設定温度ごとに別 treatment にして multiple treatments としてもよい）。
3. **Propensity 推定**: Gradient Boosting またはロジスティック回帰で `P(T=1 | X)` を推定。
4. **効果推定**: `CausalForestDML` または `LinearDML` で `E[Y(1)-Y(0) | X]` を推定。`Y` は「30 分後の室温と快適帯との距離」または「快適性 + 消費電力の合成報酬」。
5. **方策決定**: CATE > 0 かつ効果が統計的に有意な場合にのみ介入。CATE < 0 の状態では「 Sleeping dog 」として介入しない。
6. **効果検証**: `intervention_efficacy` において、単純な before-after に加え、傾向スコアマッチング（PSM）または DiD で counterfactual を推定。
7. **フィードバック**: 推定結果を `RuleThresholds.temp_high` や `AutomationRule.cooldown_s` に反映。

### 5. オフライン方策評価（OPE）の導入

新しい自動化方策（例：より積極的な換介入）を導入する前に、過去のログで評価する。

- `policy_logs` テーブルに `(timestamp, context_json, action, propensity, reward, policy_id)` を保存。
- IPS / SNIPS / DR で新方策の期待報酬を推定。
- 分散が大きい場合は clipping や positivity diagnostic（propensity score の分布確認）を実施。
- 評価結果が現在方策を上回り、かつ信頼区間が正なら段階的にロールアウト（ε-greedy）。

### 6. 新しいコンポーネントの配置

`services/brain/src/causal/` 以下に配置することを推奨。

| コンポーネント | 責務 | 呼び出し元 |
|----------------|------|------------|
| `data_mart.py` | raw_events / device_action_log などから学習用パネルデータを構築 | `CausalScheduler` |
| `propensity.py` | 処置選択確率を推定 | `EffectEstimator`, `PolicyEvaluator` |
| `effect_estimator.py` | DoWhy/EconML/CausalML をラップし ATE/CATE を推定 | `CausalScheduler`, `InterventionPlanner` |
| `policy_evaluator.py` | OPE（IPS/SNIPS/DR） | `CausalScheduler` |
| `policy_learner.py` | Contextual Bandit / ε-greedy / Thompson sampling | `brain_loops.py` / `AutomationEngine` |
| `intervention_planner.py` | 現在状態に対し、介入候補と予測効果を提示 | `ReAct loop`, `AutomationEngine` |
| `causal_scheduler.py` | 日次/週次でモデル再学習、閾値更新、レポート生成 | `brain_startup.py` |
| `report_api.py`（backend） | FastAPI エンドポイントで効果レポートを提供 | `services/backend/routers/` |

## 実装に必要なアセット

### 1. データ・スキーマ変更

#### `intervention_efficacy` テーブルの拡張

現在のカラム（`task_id`, `zone`, `trigger_metric`, `baseline_value`, `created_at`, `completed_at`, `post_value`, `window_sec`, `verdict`, `evaluated_at`）に以下を追加する。

| 追加カラム | 型 | 目的 |
|-----------|-----|------|
| `action_id` | TEXT | どの device_action_log / scene 実行に紐づくか |
| `policy_id` | TEXT | どの方策で決定されたか |
| `treatment_variant` | TEXT | 処置の詳細（例: `ac_26c` / `window_open`） |
| `context_json` | TEXT/JSONB | 実行時の共変量（時刻、外気温、在室、生体値等） |
| `propensity_score` | REAL | 当該処置が選択された推定確率 |
| `counterfactual_value` | REAL | 介入しなかった場合の推定結果 |
| `estimator` | TEXT | 使用した推定器（`dml`, `causal_forest`, `did` 等） |
| `effect_estimate` | REAL | 推定された介入効果（ATE/CATE） |
| `ci_lower` / `ci_upper` | REAL | 信頼区間 |
| `n_samples` | INTEGER | 推定に使ったサンプル数 |
| `model_version` | TEXT | モデルバージョン・ハッシュ |

#### 新規テーブル

- `causal_estimates`: コンテキストごとの CATE 推定値をキャッシュ。`intervention_planner` がリアルタイムで参照。
- `policy_logs`: 方策選択ログ。OPE とオンライン学習の入力。
- `causal_graphs`: 学習した DAG または専門家定義 DAG を JSON/ドット形式で保存。

#### 既存テーブルの拡張

- `device_action_log`: `policy_id`, `exploration`（探索フラグ）, `propensity` を追加。
- `llm_decisions`: `policy_id`, `candidate_actions`, `predicted_effects` を追加。
- `AutomationRule`: `outcome_metric`, `outcome_window_s`, `target_baseline` を追加し、効果測定対象を明示。

### 2. 新規コンポーネント

| コンポーネント | 実装概要 |
|----------------|----------|
| **Causal Data Mart** | 時系列結合、ラグ特徴量、処置系列の生成、訓練/検証分割 |
| **Propensity Model** | scikit-learn / LightGBM で `P(T=1|X)` を推定。positivity 診断付き |
| **Outcome Model** | 処置と共変量から結果を予測する回帰モデル |
| **Effect Estimator** | DoWhy 識別 + EconML/CausalML 推定。continuous/discrete treatment、multiple treatments に対応 |
| **Policy Evaluator** | IPS / SNIPS / DR による OPE。bootstrap 信頼区間 |
| **Policy Learner** | ε-greedy または Thompson sampling。探索時はユーザー承認モードと連携 |
| **Causal Graph Store** | causal-learn / pgmpy で DAG を学習・保存。do-calculus 用 |
| **Intervention Scheduler** | 日次/週次で再学習、閾値更新、Obsidian learnings note 出力 |
| **Frontend Causal Report** | 介入効果ダッシュボード（時系列、CATE ヒートマップ、方策比較） |

### 3. 外部依存

| パッケージ | 用途 | 備考 |
|-----------|------|------|
| `dowhy` | 因果モデル・識別・refutation | PyWhy 傘下。軽量 |
| `econml` | CATE / DML / Causal Forest / IV | Microsoft Research。scikit-learn 互換 |
| `causalml` | Uplift / meta-learners / multiple treatments | Uber。一部に Cython/TensorFlow オプションあり |
| `causal-learn` | 因果発見 | PyWhy 傘下 |
| `pgmpy` | ベイジアンネットワーク・SCM シミュレーション | 比較的軽量 |
| `scikit-learn`, `statsmodels` | 傾向スコア、回帰、DiD | 既存スタックと親和 |
| `vowpalwabbit` | オンライン contextual bandits | 必要に応じて。C++ 拡張 |
| `river` | オンライン学習・ドリフト検知 | 既存の adaptive threshold 調査と連携 |

### 4. 学習・推論サイクル

| 頻度 | 処理 |
|------|------|
| リアルタイム（30 秒 cycle） | コンテキスト取得 → CATE キャッシュ照会 → 方策選択 → アクション実行 → ログ書き込み |
| 毎時 | 前 1 時間のデータで propensity / outcome モデルのオンライン更新（river 等） |
| 毎日 | 前日の介入結果を用いて `intervention_efficacy` の verdict を更新（DiD/DR） |
| 毎週 | 全データで CATE モデル再学習、閾値再較正、Causal Report 生成 |
| 月次 | 因果 DAG の再学習・refutation、未観測交絡の感度分析 |

## リスク・検討事項

### 1. 未観測交絡（Unobserved Confounding）

ユーザーの気分、疲労、窓の開閉状況、部屋のドアの状態などは完全には観測できない。これにより「エアコン ON → 室温低下」の効果が過大評価・過小評価される恐れがある。

**対策**
- 代理変数（proxy variable）を活用（例：音声対話履歴から推定する活動状態）。
- DoWhy の refutation（placebo treatment、random cause、unobserved confounder）で感度分析。
- 楽器変数（IV）を利用可能な場合は EconML の IV 推定器を使用。

### 2. サンプル不足と分散

HEMS は単一住戸のため、同じ状況での介入が何度も発生しない。季節変動も大きく、統計的有意性を得るのが難しい。

**対策**
- 単純かつ解釈性の高いモデル（LinearDML、回帰不連続、DiD）を優先。
- 類似セグメント（例：同じ時間帯・同じ外気温帯）でデータをプール。
- 信頼区間を必ず報告し、広い場合は「効果不明」として扱う。

### 3. Positivity / Overlap の侵害

危険な状態（CO₂ 1500ppm 超など）ではルールが必ず介入するため、`P(T=0|X)` が 0 に近く、傾向スコアの重みが不安定になる。

**対策**
- propensity score の clipping（例：0.05〜0.95）。
- overlap 診断で common support を確認し、評価対象を制限。
- 安全性ルールは因果層を経由せず即座に実行する「hard safety layer」を残す。

### 4. 遅延効果と時系列交絡

エアコンの効果は即座ではなく、加湿器の効果も数十分続く。連続する介入は互いに影響し合う。

**対策**
- 結果変数を「介入後 n 分の平均」ではなく、複数のラグ窓で測定。
- G-computation や marginal structural model を用いて処置系列をモデル化。
- 介入間に washout period（クールダウン）を設け、効果が混在しないようにする。

### 5. 探索のコストと安全性

因果推論や RL では「未知の行動を試す」探索が必要だが、家庭環境では危険行動（例：真夏にエアコンを止める）を試せない。

**対策**
- 探索はシミュレーション環境または軽微な行動（設定温度 1℃ 変更）に限定。
- ユーザー承認モード（`AutomationRule.require_confirm` や `llm_review`）を活用。
- 生命・安全に関わるルールは因果層より上位の safety override で保護。

### 6. 解釈性とユーザー信頼

複雑な CATE モデルは「なぜこの介入が推奨されたか」を説明しにくい。

**対策**
- `SingleTreeCateInterpreter` や SHAP で説明可能なルールを抽出。
- counterfactual 説明（「もしエアコンを入れなければ…」）を LLM に渡し、ユーザー向けメッセージを生成。
- 効果の信頼区間とサンプル数をダッシュボードに表示。

### 7. 概念ドリフトとモデル陳腐化

季節・生活様式の変化により因果関係が変わる。学習し続けないと過去の最適方策が将来に通用しなくなる。

**対策**
- Adaptive Threshold Drift Detection（別紙）と連携し、再学習トリガーを自動化。
- モデルバージョンと性能モニタリング（予測誤差、CATE calibration）を実施。

### 8. Before-After 評価の罠

現在の `efficacy.compute_verdict` は「介入前後の変化」を見るだけで、介入しなくても自然に収束していた可能性を考慮しない。

**対策**
- 単純 before-after は「仮説生成」に留め、因果推定（DiD/DR/CATE）で「本当の効果」を検証する。
- 評価期間中に他の介入が入らないよう、介入カレンダーを管理する。

### 9. 実装・運用コスト

因果ライブラリは機械学習パイプライン、メモリ、セキュリティ面で重くなる。特に `causalml` は一部で Cython や深層学習オプションを必要とする。

**対策**
- 段階的導入：まず `statsmodels` + `scikit-learn` で傾向スコア・DiD を試し、効果を確認してから EconML/DoWhy を導入。
- Docker イメージサイズと起動時間を監視。
- `pip-audit` で因果ライブラリの依存脆弱性を確認。

## 参考リンク

- DoWhy: https://py-why.github.io/dowhy/
- EconML GitHub: https://github.com/py-why/EconML
- EconML ドキュメント: https://www.pywhy.org/EconML/
- CausalML GitHub: https://github.com/uber/causalml
- CausalML ドキュメント: https://causalml.readthedocs.io/en/latest/about.html
- causal-learn GitHub: https://github.com/py-why/causal-learn
- pgmpy GitHub: https://github.com/pgmpy/pgmpy
- PyWhy コミュニティ: https://www.pywhy.org/
- Vowpal Wabbit: https://vowpalwabbit.org/
- River（オンライン学習）: https://riverml.xyz/
- arXiv: Causal Machine Learning: A Survey and Open Problems — https://arxiv.org/abs/2206.15475
- arXiv: Towards Causal Representation Learning — https://arxiv.org/abs/2102.11107
- arXiv: A Unified Survey of Heterogeneous Treatment Effect Estimation and Uplift Modeling — https://arxiv.org/abs/2007.12769
- arXiv: Causal Reinforcement Learning: A Survey — https://arxiv.org/abs/2307.01452
- arXiv: Estimating the Causal Impact of Recommendation Systems from Observational Data — https://arxiv.org/abs/1510.05569
- arXiv: Robust Nonparametric Difference-in-Differences Estimation — https://arxiv.org/abs/1905.11622
- arXiv: Deep Reinforcement Learning for Smart Building Energy Management — https://arxiv.org/abs/2008.05074
- ACM e-Energy 2024: Exploring Deep Reinforcement Learning for Holistic Smart Building Control — https://dl.acm.org/doi/10.1145/3656043
- MDPI Appl. Sci. 2025: Interpretable Fuzzy Control for Energy Management in Smart Buildings — https://www.mdpi.com/2076-3417/15/15/8208
- Building Simulation 2023: Deep reinforcement learning for building HVAC control: A survey — https://link.springer.com/article/10.1007/s12273-023-1035-y
- Archives for Technical Sciences 2025: Integration of IoT in Smart Building Systems — https://arhivzatehnickenauke.com/article/794/pdf
- JCEIM 2025: Reinforcement Learning Approaches for Intelligent Control of Smart Building Energy Systems — https://jceim.org/index.php/ojs/article/view/99
