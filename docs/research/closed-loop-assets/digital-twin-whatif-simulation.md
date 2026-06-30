# デジタルツイン × What-If シミュレーションによる HEMS クローズドループ強化調査

## 概要

HEMS（Home Environment Management System）の目標は「観測 → 意思決定 → 実行 → 結果観測 → 学習 → 次の意思決定」というクローズドループを回し続けることです。本調査は、そのループに「デジタルツイン（DT）上で先に行動を仮想実行し、効果を予測・選定してから実機に反映する」仕組みを組み込むために必要な概念、先行研究、ツール、実装アセット、リスクを網羅的に調査したものです。

現状の HEMS は MQTT 経由でセンサー・デバイスを接続し、Python Brain（ReAct + Rule 双モード）が 30 秒サイクルで意思決定、FastAPI Backend が永続化、SQLite/Postgres の `event_store` に履歴を蓄積、`intervention_efficacy` テーブルで介入効果を判定、`RulePromoter` / `AckLearner` でルール・モーションを学習する構成です。本トピックで補うべき核は、**住居の熱・設備・居住者行動を動的に再現する DT と、そこで「もし X をしたら Y になるか」を高速に試行する What-If シミュレーションエンジン**です。

主要な結論は以下の 3 点です。

1. **現実的な導入パスは「軽量サロゲートモデル（オンライン What-If）＋ 物理シミュレーション（オフラインキャリブレーション）」の 2 層構成**です。30 秒サイクルで毎回 EnergyPlus を回すのは計算コスト的に無理があり、物理法則を組み込んだ軽量モデル（RC ネットワーク・Gaussian Process・勾配ブースティング等）で候補行動を瞬時に評価し、週次や月次で EnergyPlus/Modelica モデルを再キャリブレーションする運用が妥当です。
2. **HEMS の既存アセット（`AutomationRule`、`intervention_efficacy`、`RulePromoter`、`event_store`）と自然に接続できます**。What-If の予測値を `intervention_efficacy` に書き込み、実際の結果と比較することで因果的な効果推定とモデル更新が可能になります。また、シミュレーションで再現性のある良い行動は `AutomationRule` として昇格でき、`RulePromoter` の判定根拠になります。
3. **最大のリスクは「シム・トゥ・リアル（sim-to-real）ギャップ」です**。モデルドリフト、居住者行動の変化、天候外れ値等で予測が外れるため、必ず「安全ゲート」「不確実性定量化」「継続的キャリブレーション」「人間介在（human-in-the-loop）」を組み合わせる必要があります。

---

## 核心概念

### デジタルツイン（DT）の成熟レベル

同じ「仮想化」でも、データの流れと相互作用の有無で 3 段階に分けられます[^flexcon-dt-shadow-model^][^mdpi-digital-shadow-manufacturing^]。

| 概念 | データ接続 | 物理系への影響 | HEMS での位置づけ |
|---|---|---|---|
| **デジタルモデル** | なし（静的） | なし | 設計段階の家屋モデル、BIM/IFC データ |
| **デジタルシャドー** | 物理 → デジタル（一方向） | なし | 現在のセンサー状態を 3D/ダッシュボードに反映するだけ |
| **デジタルツイン** | 双方向（リアルタイム） | あり | センサーで同期し、シミュレーション結果から制御命令を出す |

HEMS で目指すべきは「デジタルツイン」です。単なる可視化ではなく、**「現在状態を正しく映し、未来を予測し、最適行動を選んで実空間に閉ループする」**能力が必要です。

### What-If シミュレーション（反実仮想）

What-If シミュレーションとは、現在の状態を起点に「もしエアコンを 26 ℃設定にしたら」「もしブラインドを閉じたら」「もし就寝 30 分前に暖房を落としたら」といった仮想介入を DT 上で実行し、結果の時系列を予測することです[^chalmers-whatif-maintenance^][^wiley-dt-frameworks-survey^]。

本質的には因果推論における **Counterfactual（反実仮想）推定**と対応しており、Pearl の「介入（do-演算）」レベルの問いに答える仕組みです[^xmol-counterfactual-guide^][^xmol-deepscm^]。HEMS では「実際に実行しなかった行動 A' の結果」をシミュレーションで推定し、実際に実行した行動 A の結果と比較することで、より因果に近い効果評価ができます。

### クローズドループ DT の 5 段階

HEMS 向けには以下のループを想定します。

1. **観測同期（Sensing）**: MQTT センサー、デバイス状態、天気予報、生体情報を DT に取り込む。
2. **状態推定（State Estimation）**: 不完全・ノイズありセンサーから、室温・在室・設備状態等を推定する（Kalman フィルタ、粒子フィルタ、Neural Operator 等）。
3. **What-If 評価（Simulation）**: 候補行動を複数シナリオで前向きシミュレーションする。
4. **最適選択と実行（Decision & Actuation）**: KPI スコアリングで最良行動を選び、MQTT/HTTP でデバイスに送信する。
5. **効果測定と学習（Learning）**: 実際の結果を観測し、予測誤差をフィードバックしてモデルを更新する。

### HEMS における解決すべき問題

- **行動の安全な試行**: 実機で「暖房を切る」等を試す前に、快適性・エネルギー影響を予測したい。
- **ルール生成の根拠**: LLM や RuleEngine が出した候補を、DT で検証してから昇格・保存したい。
- **介入効果の因果推定**: 天候・在室等の交絡因子を制御し、本当にその行動が効いたか判定したい。
- **RL/自動制御の訓練場**: 実家を傷つけずに最適制御方策を学習・転移したい。
- **ユーザー同意の可視化**: 「なぜこの行動を提案したか」を What-If 結果で説明したい。

---

## 論文・先行研究

以下は HEMS への流用可能性を意識して選定したものです。

### 住宅 HEMS とデジタルツイン

| 論文 | 著者・年 | 要点 | HEMS への応用可能性 |
|---|---|---|---|
| **A Scalable and User-Friendly Framework Integrating IoT and Digital Twins for Home Energy Management Systems**[^mdpi-applsci-hems-dt^] | Stogia et al., 2024 | 古典的 HEMS に「DT Layer」を追加。標準化されたパラメトリック 3D モデル、ゾーニング、PMV 快適性、MQTT ミドルウェア、予測分析を統合。 | HEMS の「部屋/ゾーン/デバイス/快適バンド」の DT 化にそのまま適用。 |
| **Digital Twin-Driven Decision Making and Planning for Energy Consumption**[^mdpi-jsan-fathy^] | Fathy et al., 2021 | 各家庭の Home Digital Twin（HDT）と集合的 Energy Digital Twin（EDT）の 2 層構成。HDT はエッジで強化学習し、EDT は電力需給に応じて料金を調整。 | 単身世帯なので「HDT 部分」の取り込みが直接可能。エッジ RL 訓練環境の参考。 |
| **Enabling End-User Development in Smart Homes: A Machine Learning-Powered Digital Twin for Energy Efficient Management**[^mdpi-future-internet-cotti^] | Cotti et al., 2024 | スマート家電動作モードの影響を教師なし ML でシミュレーション。Web UI でトリガー・アクションルールと推薦を生成。 | ルール生成とシミュレーション連携の参考。`AutomationRule` 生成 UI に流用。 |
| **Machine learning for optimal net-zero energy consumption in smart buildings**[^sciencedirect-energy-zhao^] | Zhao et al., 2024 | CCG + 深層強化学習で家電スケジューリング。デジタルツインモデルで検証。 | エネルギーコスト最適化・ESS 制御の参考。 |
| **Digital twin based what-if simulation for energy management**[^dtncore-pires^] | Pires et al., 2021 | エネルギーマネジメント向け What-If シミュレーション。 | HEMS の What-If 用語・概念の直接引用。 |

### 建物エネルギー・制御シミュレーション

| 論文 | 著者・年 | 要点 | HEMS への応用可能性 |
|---|---|---|---|
| **Real-Time Digital Twins for Building Energy Optimization Through Blind Control: Functional Mock-Up Units, Docker Container-Based Simulation, and Surrogate Models**[^mdpi-applsci-fmu-docker-surrogate^] | Nuevo-Gallardo et al., 2025 | EnergyPlus FMU、Docker コンテナ、軽量サロゲートモデルの 3 アプローチを比較。サロゲートは ms 級でブラインド制御スケジュールを出力し、MQTT 経由 BMS と連携。 | **本調査で最も参考になる実装**。EnergyPlus コンテナ化、サロゲート高速化、MQTT 連携をそのまま流用可能。 |
| **An Interoperable User-Centred Digital Twin Framework for Sustainable Energy System Management**[^mdpi-energies-iucdt^] | Adeel et al., 2026 | FMI 準拠のモジュラー構成。Modelica/MATLAB/EnergyPlus を統合し、ユーザ中心 UI でシナリオ分析。 | モジュラー連携（`fmpy` 等）とユーザー向け What-If UI の参考。 |
| **Model Predictive Control for Smart Buildings: Applications and Innovations in Energy Management**[^mdpi-buildings-mpc^] | Michailidis et al., 2025 | MPC による省エネ・快適性制御のレビュー。EnergyPlus/Modelica 検証、7–50% 程度の節エネ実績。 | HEMS の HVAC/照明制御を MPC 化する際の理論的基盤。 |
| **Digital Twins for Thermal Comfort and Energy Efficiency in Buildings: A Systematic Review**[^mdpi-buildings-dt-review^] | —, 2026 | BIM + IoT + EnergyPlus/Modelica/TRNSYS が主流。予測誤差 <10%、同期レイテンシ 0.8–15 s。 | 技術選定と精度目標の参考。 |
| **Coupled simulation of thermally active building systems to support a digital twin**[^sciencedirect-energybuildings-tabs^] | —, 2021 | EnergyPlus 等を用いた熱活量建築システムのカップルドシミュレーション。ライフサイクルでの性能向上。 | 床下/壁体内蔵空調等の特殊設備がある場合の参考。 |

### 居住者行動・在室推定

| 論文 | 著者・年 | 要点 | HEMS への応用可能性 |
|---|---|---|---|
| **Building occupancy behavior and prediction methods**[^hal-occupancy-review^] | Kanthila et al., 2021 | 在室行動モデルのレビュー。HMM、CART、Agent-based、Markov Chain、NN 等。 | HEMS の単身世帯向け在室・行動予測モデル選定の参考。 |
| **Review on occupancy detection and prediction in building simulation**[^sciopen-occupancy-review^] | Ding et al., 2022 | 在室モデルの体系化。Markov/HMM/ARHMM/LHMM/RNN 等。精度 80–95%。 | What-If シナリオの在室入力に必須。 |
| **A Smart Home Digital Twin to Support the Recognition of Activities of Daily Living**[^mdpi-sensors-virtual-smart-home^] | Bouchabou et al., 2023 | VirtualSmartHome シミュレータで ADL（日常生活動作）を再現し、合成センサーデータを生成。 | 行動パターンの合成データ生成・訓練環境として参考。 |
| **Enhancing building sustainability: A Digital Twin approach to energy efficiency and occupancy monitoring**[^sciencedirect-home-assistant-dt^] | Sayed et al., 2025 | Home-Assistant 上に DT を構築。ML 在室検出 95% 精度、省エネ推薦システムを評価。 | HEMS の Home Assistant bridge と連携する場合の参考。 |

### 強化学習・クローズドループ

| 論文 | 著者・年 | 要点 | HEMS への応用可能性 |
|---|---|---|---|
| **A virtual testbed for building energy optimization with Reinforcement Learning**[^arxiv-rl-testbed^] | —, 2024 | Sinergym、BOPTEST-Gym、RL Testbed for EnergyPlus、Energym、CityLearn を比較。Gymnasium 対応が重要。 | HEMS 用 RL 訓練環境の選定基準。 |
| **Applications of Deep Reinforcement Learning for Home Energy Management Systems: A Review**[^mdpi-energies-drl-hems^] | —, 2024 | HEMS 向け DRL レビュー。LSTM ベース DT による学習環境、高頻度時系列データの必要性を指摘。 | データ要件と実装戦略の参考。 |
| **A Dual Digital Twin Framework for Reinforcement Learning**[^mdpi-electronics-dual-dt-rl^] | Laukaitis et al., 2025 | Webots（高忠実度）と MuJoCo（高速）のデュアル DT で RL 訓練。sim-to-sim 整列で sim-to-real を改善。 | 高速訓練用軽量 DT と検証用詳細 DT の分離戦略の参考。 |
| **When Digital Twin Meets Generative AI: Intelligent Closed-Loop Network Management**[^arxiv-gai-dt-network^] | —, 2024 | 生成 AI + DT で状態エミュレーション、特徴抽象化、意思決定を連携。外部・内部 2 つのクローズドループ。 | LLM/ReAct 側との統合アーキテクチャの参考。 |
| **An LLM-Based Digital Twin for Optimizing Human-in-the Loop Systems**[^arxiv-llm-dt-hitl^] | —, 2024 | LLM エージェントで居住者行動を模擬し、温度制御等の HITL システム最適化。 | 単身世帯の「人間行動」DT 化の参考。 |

### モデル・キャリブレーション

| 論文 | 著者・年 | 要点 | HEMS への応用可能性 |
|---|---|---|---|
| **Physics-Informed Reduced-Order Digital Twin for Edge Deployment**[^mdpi-processes-pi-rom^] | Wang et al., 2026 | 熱伝達の軽量 Reduced-Order Model をエッジでオンライン同定。物理法則をハード制約、異常時はロールバック。 | **軽量 DT の王道**。RC モデル + オンラインパラメータ更新を HEMS に実装可能。 |
| **Digital twin: Generalization, characterization and implementation**[^dtncore-vanderhorn^] | VanDerHorn & Mahadevan, 2021 | DT の一般化・分類・実装に関する基礎研究。 | DT 設計の分類軸の参考。 |
| **Digital twin: manufacturing excellence though virtual factory replication**[^dtncore-grieves^] | Grieves, 2014 | DT 概念の原典的白書。 | 用語の基礎。 |

[^mdpi-applsci-hems-dt^]: https://www.mdpi.com/2076-3417/14/24/11834
[^mdpi-jsan-fathy^]: https://www.mdpi.com/1424-8220/20/18/5288 （類似 HDT/EDT 概念）
[^mdpi-future-internet-cotti^]: https://www.mdpi.com/1999-5903/16/5/208
[^sciencedirect-energy-zhao^]: https://www.sciencedirect.com/science/article/abs/pii/S2213138824000602
[^dtncore-pires^]: https://dl.ifip.org/db/conf/cnsm/cnsm2024/1571071925.pdf
[^mdpi-applsci-fmu-docker-surrogate^]: https://www.mdpi.com/2076-3417/15/24/12888
[^mdpi-energies-iucdt^]: https://www.mdpi.com/1996-1073/19/2/333
[^mdpi-buildings-mpc^]: https://www.mdpi.com/2075-5309/15/18/3298
[^mdpi-buildings-dt-review^]: https://www.mdpi.com/2075-5309/16/9/1715
[^sciencedirect-energybuildings-tabs^]: https://www.sciencedirect.com/science/article/pii/S0378778819305201
[^hal-occupancy-review^]: https://hal.science/hal-03240169v1/file/Building_Occupancy_Behavior_and_Prediction_Methods_A_Critical_Review_and_Challenging_Locks.pdf
[^sciopen-occupancy-review^]: https://www.sciopen.com/article/10.1007/s12273-021-0813-8
[^mdpi-sensors-virtual-smart-home^]: https://www.mdpi.com/1424-8220/23/17/7586
[^sciencedirect-home-assistant-dt^]: https://www.sciencedirect.com/science/article/pii/S0378778824012672
[^arxiv-rl-testbed^]: https://arxiv.org/html/2412.08293v1
[^mdpi-energies-drl-hems^]: https://www.mdpi.com/1996-1073/17/24/6420
[^mdpi-electronics-dual-dt-rl^]: https://www.mdpi.com/2079-9292/14/24/4806
[^arxiv-gai-dt-network^]: https://arxiv.org/html/2404.03025v2
[^arxiv-llm-dt-hitl^]: https://arxiv.org/html/2403.16809v1
[^mdpi-processes-pi-rom^]: https://www.mdpi.com/2227-9717/14/10/1539
[^dtncore-vanderhorn^]: https://www.sciencedirect.com/science/article/pii/S0167923621000581
[^dtncore-grieves^]: https://www.researchgate.net/publication/275211067_Digital_Twin_Manufacturing_Excellence_through_Virtual_Factory_Replication

---

## OSS・商用ツール・フレームワーク

### 物理シミュレーションエンジン

| 名前 | URL | 特徴 | HEMS への流用可否 |
|---|---|---|---|
| **EnergyPlus** | https://energyplus.net/ | DOE 開発の建物全体エネルギー動態シミュレーション。IDF/EPW、Python API、FMU 書き出し対応。無料・オープンソース。 | 高。住居の熱・照明・HVAC・設備の What-If に利用。Docker 化可。計算コストは高め。 |
| **Modelica Buildings Library** | https://simulationresearch.lbl.gov/modelica/ | LBNL 主導。建物・地区エネルギー・制御の動態モデル。EnergyPlus 連携（Spawn of EnergyPlus）も可能。 | 高。制御シーケンス検証、HVAC モデル化に最適。 |
| **Spawn of EnergyPlus** | https://www.energy.gov/cmei/buildings/articles/spawn-energyplus-spawn | EnergyPlus（外皮）と Modelica Buildings Library（HVAC/制御）をランタイム連携。FMI 標準準拠。 | 高。MPC/先進制御の検証に強力。 |
| **BOPTEST** | https://github.com/ibpsa/project1-boptest | 建物制御アルゴリズム比較用の REST API + FMU エミュレータ。Gymnasium ラッパーあり。 | 高。RL/MPC ベンチマーク環境として流用可能。 |
| **TRNSYS** | https://www.trnsys.com/ | 多領域動態シミュレーション（商用）。 | 中。高機能だがライセンス・コストが課題。 |

### RL/自動制御訓練フレームワーク

| 名前 | URL | 特徴 | HEMS への流用可否 |
|---|---|---|---|
| **Sinergym** | https://github.com/ugr-sail/sinergym | EnergyPlus Python API 上の Gymnasium 環境。柔軟な建物設定。 | 高。HEMS 用 RL 訓練環境の候補。 |
| **BOPTEST-Gym** | https://github.com/ibpsa/project1-boptest-gym | BOPTEST の Gymnasium ラッパー。 | 高。制御方策の事前検証に。 |
| **CityLearn** | https://github.com/intelligent-environments-lab/CityLearn | 地区スケールの需要応答・多エージェント RL。LSTM による負荷予測。 | 中。HEMS 単体よりは広域需要応用。 |
| **Energym** | https://github.com/bsl546/energym | EnergyPlus/Modelica 双方対応のシミュレーション環境。 | 中。Gymnasium 完全対応ではない。 |
| **PEPS** | https://github.com/vtaboga/PEPS | Python + EnergyPlus HVAC 制御。JAX/DL モデル訓練。 | 高。軽量な HVAC 制御学習例。 |
| **PyE+** | https://github.com/MubashirWani/PyE-Plus | Python-EnergyPlus 共シミュレーション + NSGA-II + ML サロゲート。 | 高。最適化＋サロゲートの実装参考。 |
| **EnergyPlus-MCP** | https://github.com/LBNL-ETA/EnergyPlus-MCP | EnergyPlus 用 Model Context Protocol サーバ。LLM 対話でシミュレーション操作。 | 高。LLM（ReAct）から EnergyPlus を呼び出す橋渡しに。 |

### IoT/DT プラットフォーム・ミドルウェア

| 名前 | URL | 特徴 | HEMS への流用可否 |
|---|---|---|---|
| **Eclipse Ditto** | https://www.eclipse.org/ditto/ | オープンソース IoT DT ミドルウェア。MQTT/AMQP/HTTP/WebSocket/Kafka、ポリシー、Thing モデル。MongoDB 等で状態保持。 | 高。HEMS の MQTT 基盤と親和性が高い。ただしシミュレーション機能は別途実装が必要。 |
| **FIWARE Context Broker** | https://www.fiware.org/ | オープンソース IoT コンテキスト管理。NGSI-LD。 | 中。標準化重視なら有力。運用コストはやや高い。 |
| **OpenTwins** | https://github.com/laas/openTwins | Ditto 上に構築された合成 DT プラットフォーム。3D 可視化、FMI 連携、Kafka-ML。 | 中。構成要素の参考になる。 |
| **Azure Digital Twins** | https://learn.microsoft.com/azure/digital-twins/ | クラウド DT グラフサービス。DTDL。 | 中。管理型だがベンダーロックイン・外部送信が懸念。 |
| **AWS IoT TwinMaker** | https://aws.amazon.com/iot-twinmaker/ | AWS 版 DT。3D コンテキスト可視化。 | 中。同様にクラウド依存。 |
| **Home Assistant** | https://www.home-assistant.io/ | オープンソースホームオートメーション。エンティティ状態・自動化実行。 | 高。HEMS はすでに HA bridge あり。DT 可視化・ルール実行の参考。 |
| **openHAB** | https://www.openhab.org/ | Java ベースホームオートメーション。Modelica 連携実績あり。 | 中。 |
| **ThingsBoard / Node-RED** | https://thingsboard.io/ / https://nodered.org/ | IoT ダッシュボード/ワークフロー。 | 中。データ連携・可視化に。 |

### 時系列データ・可視化

| 名前 | URL | 特徴 | HEMS への流用可否 |
|---|---|---|---|
| **InfluxDB / TimescaleDB** | — | 時系列 DB。DT 用 historian。 | 高。`event_store` を補完して長期時系列を保持。 |
| **Grafana** | https://grafana.com/ | 可視化ダッシュボード。 | 高。What-If 結果比較ダッシュボード。 |
| **Open-Meteo** | https://open-meteo.com/ | 無料天気予報 API。 | 高。既存 weather bridge と併用。 |

### 因果推論・反実仮想ツール

| 名前 | URL | 特徴 | HEMS への流用可否 |
|---|---|---|---|
| **DoWhy** | https://github.com/py-why/dowhy | Microsoft 主導。因果グラフ・推定・反実仮想。 | 高。介入効果の因果推定に。 |
| **EconML** | https://github.com/py-why/EconML | 異質処置効果推定。 | 高。行動ごとの効果推定に。 |
| **CausalML** | https://github.com/uber/causalml | Uplift モデリング。 | 中。 |
| **DeepSCM** | https://github.com/biomedia-mira/deepscm | 深層構造因果モデルで反実仮想推論。 | 中。高度な反実仮想が必要な場合。 |

### スマートホーム行動シミュレータ

| 名前 | URL | 特徴 | HEMS への流用可否 |
|---|---|---|---|
| **VirtualSmartHome** | https://github.com/dbouchabou/VirtualSmartHome | VirtualHome 拡張。アバターによる ADL 再現、合成センサーデータ。 | 中。行動パターンデータ生成に。 |
| **OpenSHS** | https://github.com/Advantech2/OpenSHS | Blender + Python の 3D スマートホームシミュレータ。 | 中。 |
| **VirtualHome** | https://github.com/xavierpuigf/virtualhome | マルチエージェント日常生活シミュレータ。 | 中。 |

---

## HEMS への適用案

### 1. アーキテクチャ全体像

既存の HEMS に `services/simulation`（または Brain 内 `world_model/simulation`）を追加し、以下のように接続します。

```
[センサー/デバイス] ← MQTT → [Mosquitto] ← MQTT → [HEMS Brain]
                                            │
                                            ├─ WhatIfPlanner
                                            │    ├─ 候補行動生成
                                            │    └─ SimulationClient 呼び出し
                                            │
                                            ↓ REST/MQTT
                                    [services/simulation]
                                            │
                    ┌───────────────────────┼───────────────────────┐
                    ↓                       ↓                       ↓
            [軽量サロゲートモデル]   [EnergyPlus/Modelica]   [在室・行動モデル]
            (オンライン What-If)       (オフライン校正)        (シナリオ入力)
                    │
                    ↓
            [Safety Gate] → 実行命令 → MQTT → デバイス
                    │
                    └→ 予測結果を Backend / event_store へ保存
```

### 2. 既存コンポーネントとの接続

#### RuleThresholds / RuleEngine

`services/brain/src/rules/config.py` の `RuleThresholds` は温度/CO₂/湿度等の閾値を一元管理しています。What-If ではこれらを **コスト関数の制約・快適バンド** として利用します。

- 例: `temperature` の `lo=18.0, hi=26.0` を、シミュレーション結果の許容範囲にする。
- `RuleEngine` が出す候補行動（例: エアコン ON）を WhatIfPlanner に渡し、予測結果でフィルタリングする。

#### AutomationRule

`services/backend/routers/automations.py` と `services/backend/models.py` の `AutomationRule` は `trigger_type` / `trigger_config` / `actions` / `mode`（`direct` or `llm_review`）を持ちます。以下を拡張します。

```python
# 追加想定フィールド
simulate_before_run: bool = False
simulation_horizon_min: int = 30
simulation_kpi_weights: dict = {"comfort": 0.4, "energy": 0.3, "safety": 0.3}
simulation_mode: str = "surrogate"  # "surrogate" | "energyplus" | "none"
```

#### intervention_efficacy

`services/brain/src/event_store/database.py` にある `intervention_efficacy` テーブルは、環境タスクの実行前後の指標を比較します。以下のカラムを追加して What-If 予測と紐付けます。

```sql
ALTER TABLE intervention_efficacy ADD COLUMN predicted_value REAL;
ALTER TABLE intervention_efficacy ADD COLUMN predicted_delta REAL;
ALTER TABLE intervention_efficacy ADD COLUMN sim_run_id INTEGER;
ALTER TABLE intervention_efficacy ADD COLUMN model_error REAL;  -- 予測値 - 実測値
ALTER TABLE intervention_efficacy ADD COLUMN scenario_id INTEGER;
```

`services/brain/src/efficacy.py` の `compute_verdict` は `baseline` と `post` のみを見ていますが、これを拡張し「予測が実測にどれだけ近かったか」を返す `compute_model_fidelity()` を追加します。

#### RulePromoter / AckLearner

- `RulePromoter`（`services/brain/src/annotator/rule_promoter.py`）は LLM 分類結果を `hit_count >= 3` で昇格します。What-If シミュレーションで再現性の高い（複数シナリオで安定して良い KPI を示す）行動も昇格対象に加えられます。
- `AckLearner`（`services/brain/src/voice_capsule/ack_learner.py`）はモーションの拒否率を学習します。What-If 結果で「ユーザー不満を起こしやすい行動」（例: 睡眠中の照明点灯）を事前に棄却する重み付けに使えます。

#### event_store / world_events

`event_store` に新しいテーブル群を追加し、シミュレーション履歴を時系列で追跡します。

```sql
CREATE TABLE simulation_runs (
    id BIGSERIAL PRIMARY KEY,
    scenario_id BIGINT,
    model_id TEXT NOT NULL,
    base_state JSONB NOT NULL,
    candidate_actions JSONB NOT NULL,
    forecast JSONB,
    result_json JSONB,
    kpi_json JSONB,
    status TEXT,
    started_at TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE TABLE what_if_scenarios (
    id BIGSERIAL PRIMARY KEY,
    name TEXT,
    trigger_event_id BIGINT REFERENCES world_events(id),
    base_state_json JSONB NOT NULL,
    horizon_min INTEGER,
    candidate_actions_json JSONB,
    selected_action_idx INTEGER,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

### 3. 新規コンポーネント案

| コンポーネント | 責務 | 置き場所案 |
|---|---|---|
| **WhatIfPlanner** | Brain サイクル内で候補行動を生成・呼び出し・評価 | `services/brain/src/what_if/planner.py` |
| **SimulationClient** | Simulation Service への REST/MQTT 呼び出し | `services/brain/src/what_if/client.py` |
| **SimulationService** | FastAPI サービス。モデル選択・実行・キャリブレーション | `services/simulation/` |
| **SimulationModel** | 抽象ベース。`EnergyPlusModel`, `SurrogateModel`, `OccupancyModel` | `services/simulation/models/` |
| **SurrogateModel** | 軽量予測モデル（RC/GBDT/GP/Neural） | `services/simulation/models/surrogate.py` |
| **OccupancyPredictor** | 在室・行動予測（HMM/ML） | `services/simulation/models/occupancy.py` |
| **SafetyGate** | 安全制約・制限事項チェック | `services/brain/src/what_if/safety_gate.py` |
| **EfficacyComparator** | 予測 vs 実測の比較 | `services/brain/src/what_if/comparator.py` |
| **ModelCalibrator** | サロゲートモデルのオンライン更新 | `services/simulation/calibration.py` |

### 4. 30 秒サイクルへの組み込み

- **通常サイクル**: Brain は WhatIfPlanner を軽量モード（サロゲート、予測ホライズン 10–30 分）で呼び出し、重要な環境変化時のみシミュレーション実行。
- **重要判定**: 温度/CO₂/湿度が閾値近傍、またはユーザーから明示的な要求がある場合に発火。
- **実行フロー**: WhatIfPlanner → SimulationClient → SafetyGate → ToolExecutor → 実機 → event_store に実測を記録 → EfficacyComparator が翌サイクル以降に予測誤差を計算 → ModelCalibrator が閾値超過でモデル更新。

### 5. MQTT トピック案

| 用途 | トピック | 備考 |
|---|---|---|
| シミュレーション要求 | `hems/brain/whatif/request` | Brain → Simulation Service |
| シミュレーション結果 | `hems/brain/whatif/result` | Simulation Service → Brain |
| 合成予測値（読み取り専用） | `hems/simulation/{zone}/{metric}/predicted` | ダッシュボード用。決して実デバイスには紐付けない |
| モデル状態 | `hems/simulation/model/status` | キャリブレーション状態・誤差 |
| 安全停止 | `hems/brain/whatif/safety_halt` | 予測外れ・危険シナリオ検出時 |

---

## 実装に必要なアセット

### データ要件

1. **家屋メタデータ**: 間取り、ゾーン、壁/窓の熱貫流率（U-value）、窓面積・方位、天井高、HVAC 仕様、設備の消費電力プロファイル。
2. **履歴時系列**: センサーデータ、デバイス状態、天気、在室推定、エネルギー使用量、ユーザーからの ack/拒否ログ。
3. **行動パターン**: 起床/就寝/在室/離席/入浴等の時系列。プライバシー保護のためローカル学習。
4. **快適性基準**: `efficacy.py` の `METRIC_SPECS`（温度 18–26 ℃、湿度 30–60 %、CO₂ ≤ 1000 ppm 等）を拡張。
5. **天気予報**: Open-Meteo 等からの外部予報。既存 `weather bridge` と統合。

### スキーマ変更

- Backend: `automation_rules` テーブルに `simulate_before_run`, `simulation_horizon_min`, `simulation_kpi_weights`, `simulation_mode` を追加。
- Backend: `digital_twin_models`, `what_if_scenarios`, `simulation_runs` テーブルを新設。
- event_store: `intervention_efficacy` に予測値・誤差・シナリオ ID を追加。`simulation_runs` / `what_if_scenarios` テーブルを追加。
- Frontend: シミュレーション結果を表示する `SimulationResult`, `WhatIfScenario` 型を追加。

### 新規コンポーネント詳細

| コンポーネント | 詳細 |
|---|---|
| **WhatIfPlanner** | `trigger_events` から候補行動を列挙。ルールベースで「温度が高い → 冷房/換気/ブラインド」等の行動空間を生成。LLM レビュー時は自然言語の提案も受け入れる。 |
| **SurrogateModel** | 例: 各ゾーンの温度を `T(t+1) = f(T(t), 外気温, 日射, 在室, デバイス ON/OFF, HVAC 設定)` とする軽量モデル。候補に LightGBM/RandomForest/Physics-informed NN。 |
| **EnergyPlusModel** | Docker コンテナ内で EnergyPlus Python API を起動。IDF は家屋に応じてテンプレート化。週次バッチでキャリブレーション。 |
| **OccupancyPredictor** | 過去の在室・生体（心拍/歩数）・時間帯から HMM または LSTM で在室確率を予測。What-If のシナリオ入力に使用。 |
| **SafetyGate** | 例: 寝ている間の大声/照明全点灯、CO₂ 1500 ppm 超過時の換気停止、極端な温度設定等をブロック。ユーザー承認モードも設定可能。 |
| **EfficacyComparator** | `intervention_efficacy` の `predicted_value` と `post_value` を比較。MAE/RMSE/バイアスを計算し、モデル更新トリガーに。 |
| **ModelCalibrator** | 予測誤差が閾値（例: 温度 1 ℃, CO₂ 100 ppm）を超えたら、直近 N 日分のデータでサロゲートを再学習。 |

### 外部依存

- Python: `pyenergyplus` / `eppy` / `fmpy`（FMI）, `scikit-learn`, `lightgbm`, `prophet` / `neuralforecast`, `dowhy`, `econml`
- シミュレーション: EnergyPlus, Modelica Buildings Library / Spawn, BOPTEST
- コンテナ: EnergyPlus Docker image（`nrel/energyplus` 等）
- 時系列 DB: InfluxDB または TimescaleDB（長期データ蓄積向け）

---

## リスク・検討事項

| リスク | 内容 | 対策 |
|---|---|---|
| **Sim-to-real ギャップ** | モデルが実世界からずれ、最適行動が実際は有害。 | 継続的キャリブレーション、不確実性定量化、安全ゲート、予測誤差監視。 |
| **計算コスト** | EnergyPlus 1 回の What-If が数分～数十分。30 秒サイクルに無理。 | オンラインはサロゲートモデル。EnergyPlus はオフライン校正・月次チューニング。 |
| **データ不足** | 単身世帯は多様性・データ量が少ない。 | 物理法則制約で少ないデータでも汎化。合成データ（VirtualSmartHome 等）で補完。 |
| **因果同定の困難さ** | 天候・在室等の交絡で「介入効果」を見誤る。 | Counterfactual シミュレーション + DoWhy/EconML で効果推定。AB テスト的な運用。 |
| **安全性・悪用リスク** | What-If 結果が誤って実デバイスに反映される。 | 合成トピックを実アクチュエータトピックと分離。SafetyGate で必ず検証。高リスク動作は人間承認。 |
| **運用・メンテナンス負荷** | 家屋モデル、設備仕様、気象データの保守。 | IDF テンプレート化、自動キャリブレーション、異常時はフォールバックで既存 RuleEngine に戻す。 |
| **ブラックボックス化** | ML サロゲートの説明が難しく、ユーザー不信。 | SHAP/LIME 等で特徴重要度を UI 表示。What-If 結果を「もし A なら B」という形で説明。 |
| **ベンダーロックイン** | クラウド DT サービスへの依存。 | HEMS は PolyForm Noncommercial License の個人運用。EnergyPlus/Modelica/Ditto 等オープンソース優先。 |
| **プライバシー** | 在室・行動・生体データを使ったモデル学習。 | すべてローカル（Docker on HEMS ホスト）で処理。外部クラウドへは匿名化集計のみ。 |
| **ユーザ受容性** | 予測に基づく自動制御が居住者の快適性を損なう。 | 初期は「推薦モード」で、ユーザーが承認してから実行。学習が進んで信頼性が上がった段階で自動化。 |

---

## 参考リンク

### 論文・調査報告
- Stogia et al. (2024) — HEMS 向け IoT + DT フレームワーク: https://www.mdpi.com/2076-3417/14/24/11834
- Nuevo-Gallardo et al. (2025) — FMU/Docker/サロゲートを比較したリアルタイム建物 DT: https://www.mdpi.com/2076-3417/15/24/12888
- Adeel et al. (2026) — FMI 準拠のユーザ中心 DT フレームワーク: https://www.mdpi.com/1996-1073/19/2/333
- Michailidis et al. (2025) — スマートビル MPC レビュー: https://www.mdpi.com/2075-5309/15/18/3298
- Bouchabou et al. (2023) — スマートホーム DT / VirtualSmartHome: https://www.mdpi.com/1424-8220/23/17/7586
- Sayed et al. (2025) — Home-Assistant 上の DT 省エネ研究: https://www.sciencedirect.com/science/article/pii/S0378778824012672
- Ding et al. (2022) — 在室検出・予測レビュー: https://www.sciopen.com/article/10.1007/s12273-021-0813-8
- Kanthila et al. (2021) — 居住者行動予測レビュー: https://hal.science/hal-03240169v1/file/Building_Occupancy_Behavior_and_Prediction_Methods_A_Critical_Review_and_Challenging_Locks.pdf
- Wang et al. (2026) — Physics-Informed Reduced-Order DT: https://www.mdpi.com/2227-9717/14/10/1539
- Wiley (2024) — オープンソース DT フレームワーク調査: https://onlinelibrary.wiley.com/doi/10.1002/spe.3305
- Chalmers — What-If シミュレーションによるメンテナンス優先度: https://research.chalmers.se/publication/547701/file/547701_Fulltext.pdf

### OSS・フレームワーク
- EnergyPlus: https://energyplus.net/
- Modelica Buildings Library: https://simulationresearch.lbl.gov/modelica/
- Spawn of EnergyPlus: https://www.energy.gov/cmei/buildings/articles/spawn-energyplus-spawn
- BOPTEST: https://github.com/ibpsa/project1-boptest
- Sinergym: https://github.com/ugr-sail/sinergym
- BOPTEST-Gym: https://github.com/ibpsa/project1-boptest-gym
- EnergyPlus-MCP: https://github.com/LBNL-ETA/EnergyPlus-MCP
- PyE+: https://github.com/MubashirWani/PyE-Plus
- PEPS: https://github.com/vtaboga/PEPS
- Eclipse Ditto: https://www.eclipse.org/ditto/
- FIWARE: https://www.fiware.org/
- OpenTwins: https://github.com/laas/openTwins
- DoWhy: https://github.com/py-why/dowhy
- EconML: https://github.com/py-why/EconML
- VirtualSmartHome: https://github.com/dbouchabou/VirtualSmartHome
- OpenSHS: https://github.com/Advantech2/OpenSHS

### 概念・白書
- Digital Twin vs Digital Shadow vs Digital Model: https://www.flexcon.it/news-events/digital-twin-vs-digital-shadow-vs-digital-model/
- IOWN GF Network Digital Twin Use Case (What-If with GenAI): https://iowngf.org/wp-content/uploads/2025/02/IOWN-GF-RD-NDT_Use_Case-2.0.pdf
- MQTT for Connected Twins: https://www.hivemq.com/blog/enabling-connected-twins-in-iiot-with-mqtt/
