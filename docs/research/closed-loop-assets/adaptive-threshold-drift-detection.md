# Adaptive Threshold Drift Detection — HEMS 調査レポート

## 概要

**Adaptive Threshold Drift Detection（適応的閾値ドリフト検知）** は、IoT センサー・生体情報・スマートデバイス・PC/サービス監視など、時間とともに分布が変化するデータストリームに対し、固定した異常検知閾値ではなく、データの「普通」の変化を追従しながら異常を検出する技術群である。HEMS の閉 loop（観測 → 意思決定 → 実行 → 結果観測 → 学習 → 次の意思決定）において、本トピックは以下の問題を解く。

- 季節変動・生活リズム変化・デバイス交換などによる「普通」の基準の自然な変化を、異常と誤認しない。
- 長期的に閾値が陳腐化（threshold rot）して、過剰アラート（false positive）や見逃し（false negative）が増大するのを防ぐ。
- ユーザーのフィードバックや介入効果測定を使って、ルールエンジン・LLM 推論の閾値を継続的に再較正する。
- 概念ドリフト（concept drift）を検知したら、モデルや閾値を適切にリセット・再学習し、システムの信頼性を維持する。

本レポートでは、核心概念、代表的な論文、OSS/商用ツール、HEMS への適用案、必要なデータ・スキーマ・コンポーネント、リスクと妥協点を網羅的にまとめる。

## 核心概念

### 1. 概念ドリフト（Concept Drift）

データストリームにおいて、入力データの分布 `P(X)` や入出力の関係 `P(Y|X)` が時間とともに変化する現象。HEMS では、季節による室温・湿度の変動、新生活開始、在宅勤務化、デバイス交換、エアコンのフィルタ劣化などが該当する。Gama et al. (2014) は、ドリフトを以下のように分類した。

| タイプ | 特徴 | HEMS の例 |
|--------|------|-----------|
| **Abrupt（急変）** | 一瞬で分布が切り替わる | エアコン買い替え、引っ越し、デバイス故障 |
| **Gradual（漸変）** | ゆっくりと新しい分布へ移行 | 季節の変化、生活リズムの変化 |
| **Incremental（増分的）** | 小さな変化が積み重なる | 家電の経年劣化、フィルタ詰まり |
| **Recurrent（再発的）** | 一定周期で繰り返される | 夏/冬の冷暖房パターン、平日/休日の違い |

### 2. 適応的閾値（Adaptive Threshold）

固定閾値 `T` の代わりに、最近のデータ分布から動的に閾値を計算する手法。典型的には、予測残差やセンサ値の移動平均 `μ` と標準偏差 `σ` を用いて

```
T(t) = μ(t) + z(t) · σ(t)
```

の形で表される。`z(t)` は false positive 率やデータの変動に応じて適応的に更新される係数。例えば、頻繁に閾値を超えてユーザーに無視されている場合は `z` を大きくし、重要な異常を見逃している場合は `z` を小さくする。

### 3. ドリフト検知（Drift Detection）

データ分布やモデルの予測誤差の変化を検知し、閾値・モデル・学習窓を更新するトリガー。代表的なアプローチは以下の3つ。

| アプローチ | 監視対象 | 代表手法 | 特徴 |
|------------|----------|----------|------|
| **Performance-based** | モデルの予測誤差 | DDM, EDDM, HDDM | ラベルあり/遅延ラベルで使える。誤差増大でドリフト判定 |
| **Distribution-based** | データ分布そのもの | ADWIN, KSWIN, Page-Hinkley | ラベル不要。統計検定や累積和で分布変化を検知 |
| **Context-aware** | 文脈・残差の動的モデル | HTM, ADWIN-U, AnDri | 季節性・再発パターンを考慮 |

### 4. 異常とドリフトの分離

AnDri (Chiang & Milani, 2025) や AdapAD (Nguyen et al., 2024) が指摘するように、単なる分布変化（ドリフト）と異常は区別すべき。HEMS では、「エアコン設定温度を下げたので室温が下がった」は正常なドリフト、「窓が開いたままエアコンが全開」は異常。両者を混同すると、過剰な再学習や閾値緩和を招く。

### 5. HEMS における閉 loop との接続

HEMS はすでに以下の学習/適応機構を持つ。

- `RuleThresholds`：ルールエンジンの静的閾値セット（`services/brain/src/rules/config.py`）
- `RulePromoter`：LLM 分類キャッシュの高頻度エントリを `source=llm` から `source=promoted` へ昇格（`services/brain/src/annotator/rule_promoter.py`）
- `AckLearner`：voice capsule の再生ログ `trigger_drift_sec` からリマインダーの `lead_time_min` を学習（`services/brain/src/voice_capsule/ack_learner.py`）
- `intervention_efficacy`：環境タスク実行前後のメトリクスを比較し、介入効果を判定（`services/brain/src/efficacy.py`, `services/brain/src/event_store/database.py`）

Adaptive Threshold Drift Detection は、これらの仕組みを「数値的閾値の自己較正」に拡張する橋渡し概念である。

## 論文・先行研究

### 基礎論文

| タイトル | 著者 | 年 | 要点 | HEMS 応用可能性 |
|----------|------|-----|------|-----------------|
| **Learning with Drift Detection** | Gama, Medas, Castillo, Rodrigues | 2004 | DDM（Drift Detection Method）を提案。オンライン誤差率の平均と標準偏差を監視し、warning/drift の2段階でドリフトを検知。 | ルールエンジンの予測/発火頻度を監視し、閾値の再較正トリガーに使える。 |
| **Learning from Time-Changing Data with Adaptive Windowing (ADWIN)** | Bifet, Gavalda | 2007 | 可変長スライディングウィンドウで2つの部分窓の平均差を Hoeffding bound で検定。ドリフト検出時に古いデータを破棄。 | センサーストリームの分布変化をラベルなしで検知。 Seasonal/gradual drift に強い。 |
| **Early Drift Detection Method (EDDM)** | Baena-García et al. | 2006 | 誤差の発生間隔（距離）を監視し、漸変ドリフトを早期検出。DDM の遅延を補う。 | ルールの false positive 頻度の変化をゆるやかに捉える。 |
| **A Survey on Concept Drift Adaptation** | Gama et al. | 2014 | 概念ドリフト適応の包括的サーベイ。drift detector、adaptive learner、ensemble の分類。 | HEMS 全体のアーキテクチャ設計の理論基盤。 |
| **Learning Under Concept Drift: A Review** | Lu et al. | 2018 | ドリフトの分類と検知・適応手法の体系的レビュー。 | 手法選択の指針。 |

### 異常検知×ドリフトの統合

| タイトル | 著者 | 年 | 要点 | HEMS 応用可能性 |
|----------|------|-----|------|-----------------|
| **Adaptive Anomaly Detection in the Presence of Concept Drift (AnDri)** | Chiang, Milani | 2025 | 動的な normal model と Adjacent Hierarchical Clustering (AHC) で、漸変・再発ドリフトと異常を分離。 | 季節性のある室温・湿度パターンと、真の異常（窓開き等）を区別。 |
| **Concept-drift-adaptive anomaly detector for marine sensor data streams (AdapAD)** | Nguyen et al. | 2024 | 海洋センサーデータ向け。専門家知識と統計的手法を組み合わせ、40手法を上回る精度。 | 同様の「専門家（ユーザー）知識＋データ」アプローチを HEMS 生体・環境センサーに展開。 |
| **Detecting Spacecraft Anomalies Using LSTMs and Nonparametric Dynamic Thresholding** | Hundman et al. | 2018 | LSTM 予測の残差に対し、動的閾値を非パラメトリックに設定。NASA の運用実績。 | 室温・CO₂・消費電力などの時系列予測と組み合わせた異常検知。 |
| **Unsupervised Real-Time Anomaly Detection for Streaming Data (Numenta HTM)** | Ahmad et al. | 2017 | Hierarchical Temporal Memory (HTM) で連続学習し、予測誤差と「異常尤度」で検知。 | 電力・温度などのストリームを継続的に学習し、閾値チューニングを減らす。 |
| **PWPAE: An Ensemble Framework for Concept Drift Adaptation in IoT Data Streams** | Yang, Manias, Shami | 2021 | 複数のオンライン学習器をアンサンブルし、IoT データストリームのドリフトに適応。 | 複数センサー・複数ドメインの HEMS 異常検知に対するロバストな統合モデル。 |
| **Binary Anomaly Detection in Streaming IoT Traffic under Concept Drift** | Carnier et al. | 2025 | ストリーミングラーニング（ARF, Hoeffding Tree）がバッチ学習よりドリフトに強いことを実証。 | エッジ/クラウドでのオンライン異常検知器の選定指針。 |

### HEMS / スマートホーム・BEMS 応用

| タイトル | 著者 | 年 | 要点 | HEMS 応用可能性 |
|----------|------|-----|------|-----------------|
| **EnergiQ: A Prescriptive LLM-Driven Intelligent Platform for Interpreting Appliance Energy Consumption Patterns** | Papaioannou et al. | 2025 | スマートプラグ＋CNN-LSTM 異常検知＋LLM 説明＋ユーザーフィードバックによる継続学習。 | HEMS の LLM 推論層と Appliance 異常検知との統合モデル。 |
| **Systematic Review of Optimization Methodologies for Smart Home Energy Management Systems** | MDPI Energies | 2025 | HEMS における教師なし学習・異常検知・クラスタリングのレビュー。 | HEMS 最適化における異常検知の位置づけ。 |
| **An Active Learning Methodology for Expert-Assisted Anomaly Detection** | Trujillo et al. | 2023 | 専家フィードバック（confirm/dismiss/modify/add）に基づき閾値を更新。 | ユーザーの「これは異常ではない」「見逃した」フィードバックを閾値調整に反映。 |

## OSS・商用ツール・フレームワーク

### Python ストリーム学習・ドリフト検知

| 名前 | URL | 特徴 | HEMS への流用可否 |
|------|-----|------|-------------------|
| **River** | https://riverml.xyz | scikit-multiflow の後継。ADWIN, DDM, EDDM, Page-Hinkley, KSWIN, HDDM, Hoeffding Tree, ARF, SRP, LeveragingBagging などを実装。Python 3.11 対応。軽量。 | **最も推奨**。`services/brain/src` 内の新コンポーネントに容易に組み込める。閾値更新ループに ADWIN/DDM を組み込む。 |
| **scikit-multiflow** | https://scikit-multiflow.readthedocs.io | River の前身。ADWIN, DDM, EDDM, PageHinkley, KSWIN などを含む。 | 既にプロジェクトで `river` が使われているなら River を優先。 |
| **Frouros** | https://github.com/ibm/frouros | IBM 製。ドリフト検知・データ検証の Python ライブラリ。 | 比較的新しい。分布検知の追加選択肢。 |
| **heimdall (R)** | https://cran.r-project.org/web/packages/heimdall | R 版ストリームドリフト検知。 | Python ベースの HEMS には不向き。 |

### 時系列異常検知フレームワーク

| 名前 | URL | 特徴 | HEMS への流用可否 |
|------|-----|------|-------------------|
| **Numenta HTM / NuPIC** | https://github.com/numenta/NAB | 脳皮質モデルに基づく連続学習型異常検知。NAB ベンチマーク付き。 | Python 3.11 対応は限定的。理論的参考価値は高いが、導入コスト大。 |
| **TSB-UAD** | https://github.com/yyeunji/TSB-UAD | 時系列異常検知ベンチマーク。 | 評価用データセットとして活用。 |
| **Reckon** | https://github.com/waltzofpearls/reckon | Prometheus メトリクスを Prophet / Tangram で予測し、異常バンドを返す exporter。 | 監視系の参考実装。HEMS のメトリクス予測に応用可能。 |
| **Grafana PromQL Anomaly Detection** | https://github.com/grafana/promql-anomaly-detection | adaptive / robust（MAD）異常検知の Prometheus ルール集。 | HEMS が Prometheus を使う場合の運用監視に流用。 |

### 商用クラウドサービス

| 名前 | URL | 特徴 | HEMS への流用可否 |
|------|-----|------|-------------------|
| **AWS Lookout for Equipment / CloudWatch Anomaly Detection** | aws.amazon.com | 時系列異常検知、ドリフト検知。 | クラウド連携時の候補。ただしローカル/オフライン運作には不向き。 |
| **Azure Anomaly Detector** | azure.microsoft.com | 時系列の変化点・異常検知 API。 | 同上。 |
| **Google Cloud AIOps / Vertex AI Monitoring** | cloud.google.com | モデルドリフト・特徴量ドリフト監視。 | LLM/ML モデルの運用監視に参考。 |

### 関連参考実装

| 名前 | URL | 特徴 | HEMS への流用可否 |
|------|-----|------|-------------------|
| **PWPAE 実装** | https://github.com/Western-OC2-Lab/PWPAE-Concept-Drift-Detection-and-Adaptation | River を使った IoT ドリフト検知・適応の実装例。 | コード設計の参考。 |
| **NAB** | https://github.com/numenta/NAB | リアルタイム異常検知ベンチマーク。 | 自前アルゴリズムの評価基盤。 |

## HEMS への適用案

### 1. 全体アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────┐
│  Edge / Sensors (MQTT: hems/sensors/+, office/+, hems/pc/+)      │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Brain: AdaptiveThresholdDriftTracker                           │
│  - センサー/デバイス/PC ごとの DriftDetector インスタンス保持     │
│  - ADWIN / Page-Hinkley / DDM で分布変化・予測誤差変化を検知      │
│  - 異常スコアを計算し、動的閾値を更新                             │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Brain: ThresholdAdjuster                                       │
│  - RuleEngine の閾値を、ドリフト検知・フィードバックに応じ更新    │
│  - ユーザーからの dismiss/confirm を学習                         │
│  - 介入効果（intervention_efficacy）を閾値評価に反映              │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Backend: threshold_drift_log / threshold_adjustments テーブル   │
│  - 閾値変更履歴・根拠・承認状態を永続化                           │
│  - Frontend ダッシュボードで可視化・手動承認                      │
└─────────────────────────────────────────────────────────────────┘
```

### 2. RuleThresholds との接続

現在 `RuleThresholds` は環境変数から1回読み込まれる静的 dataclass。Adaptive Threshold Drift Detection を組み込むには、以下のように進化させる。

```python
@dataclass
class AdaptiveRuleThresholds:
    # 静的基準値（env から読み込まれる）
    temp_high_base: float = 28.0
    # 動的オフセット（ドリフト検知・フィードバックで更新）
    temp_high_offset: float = 0.0
    # 現在の実効閾値
    @property
    def temp_high(self) -> float:
        return self.temp_high_base + self.temp_high_offset
    # ドリフト状態
    drift_state: dict[str, dict] = field(default_factory=dict)
```

`RuleEngine` は `thresholds.temp_high` のようなプロパティを参照するだけなので、実装変更を最小化できる。

### 3. DriftDetector 統合

各メトリクス（温度、湿度、CO₂、消費電力、心拍数、PC CPU など）に対し、`river.drift.ADWIN` または `river.drift.PageHinkley` のインスタンスを保持する。

```python
from river import drift

class MetricDriftTracker:
    def __init__(self, metric_key: str, detector: drift.ADWIN):
        self.metric_key = metric_key
        self.detector = detector
        self.last_drift_at: float | None = None

    def update(self, value: float) -> dict:
        self.detector.update(value)
        return {
            "drift_detected": self.detector.drift_detected,
            "estimation": self.detector.estimation,
            "variance": self.detector.variance,
            "width": self.detector.width,
        }
```

### 4. AckLearner / RulePromoter との融合

既存の `AckLearner` は voice capsule の時間ズレを学習する。これを「数値閾値の学習」に一般化する。

- **confirm**：ユーザーがアラートを承認した場合、その値を「異常」として閾値を下げる方向に作用。
- **dismiss**：ユーザーがアラートを無視/却下した場合、その値を「正常」として閾値を上げる方向に作用。
- **intervention_efficacy**：環境タスクの効果 `effective/counterproductive/inconclusive` に応じて、対応するメトリクスの閾値感度を調整。

例えば、換気タスク後に CO₂ が下がらない（`counterproductive`）場合、換気のトリガー閾値を引き下げる（より敏感に）か、タスクの実行方法を見直す。

### 5. 介入効果ループの活用

`services/brain/src/efficacy.py` はすでに「タスク → 前後のメトリクス → verdict」を実装している。これを閾値学習に組み込む。

```python
# 例: 換気タスク後の CO₂ 改善が不十分なら、トリガー閾値を引き下げる
if verdict == "counterproductive" and metric == "co2":
    adjuster.nudge_threshold("co2_high", delta=-50, reason="counterproductive_ventilation")
```

### 6. 30 秒サイクルでの実行

Brain の ReAct ループは30秒周期。ドリフト検知は以下のタイミングで実行する。

- 毎サイクル：センサー値を `MetricDriftTracker` にフィード。
- ドリフト検出時：閾値更新を提案し、`threshold_adjustments` テーブルに `proposed` 状態で記録。
- 承認後（または自動承認設定時）：`RuleThresholds` の動的オフセットを更新。
- 日次バッチ：`AckLearner` 的に、過去24時間のフィードバックを集計し、閾値を再較正。

## 実装に必要なアセット

### データ要件

- **時系列センサーデータ**：`raw_events`, `world_events` に蓄積された各種センサー値。
- **アラート/タスク履歴**：どの閾値が発火し、どの介入が行われたか。
- **ユーザーフィードバック**：dismiss, confirm, modify, add のラベル。
- **介入効果データ**：`intervention_efficacy` テーブルの verdict。
- **外部文脈**：時刻、曜日、季節、在宅/不在、天気（weather bridge）。

### スキーマ変更

#### Backend (`services/backend/models.py`)

```python
class ThresholdDriftLog(Base):
    __tablename__ = "threshold_drift_log"
    id = Column(Integer, primary_key=True)
    metric_key = Column(String, nullable=False, index=True)  # "co2_high", "temp_high"
    detector = Column(String, nullable=False)  # "ADWIN", "PageHinkley"
    detected_at = Column(TZDateTime(timezone=True), server_default=func.now())
    old_value = Column(Float)
    proposed_value = Column(Float)
    reason = Column(String)  # "drift", "feedback", "efficacy"
    status = Column(String, default="proposed")  # proposed, approved, rejected, auto_applied

class ThresholdAdjustment(Base):
    __tablename__ = "threshold_adjustments"
    id = Column(Integer, primary_key=True)
    metric_key = Column(String, nullable=False, index=True)
    base_value = Column(Float, nullable=False)
    offset = Column(Float, default=0.0)
    applied_at = Column(TZDateTime(timezone=True), server_default=func.now())
    approved_by = Column(String)  # "system", "user", "auto"
```

#### Event Store (`services/brain/src/event_store/database.py`)

```sql
CREATE TABLE IF NOT EXISTS drift_detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    metric_key TEXT NOT NULL,
    detector TEXT NOT NULL,
    old_threshold REAL,
    proposed_threshold REAL,
    detector_state TEXT DEFAULT '{}'
);
```

### 新規コンポーネント

| コンポーネント | 配置 | 役割 |
|----------------|------|------|
| `AdaptiveThresholdManager` | `services/brain/src/adaptive_thresholds/manager.py` | 各メトリクスの DriftTracker 群を管理し、閾値更新を提案する。 |
| `MetricDriftTracker` | `services/brain/src/adaptive_thresholds/tracker.py` | 1 メトリクスあたりの ADWIN/Page-Hinkley ラッパー。 |
| `ThresholdAdjuster` | `services/brain/src/adaptive_thresholds/adjuster.py` | フィードバックと介入効果を使って閾値オフセットを更新。 |
| `AdaptiveRuleThresholds` | `services/brain/src/rules/config.py` 内 | `RuleThresholds` の動的版。 |
| `threshold_drift` API | `services/backend/routers/automations.py` または新規 `adaptive_thresholds.py` | 閾値変更提案の取得・承認。 |
| Frontend UI | `services/frontend/src/app/settings/thresholds/` | 閾値変更提案の可視化・手動承認。 |

### 外部依存

- **River**: `requirements*.txt` に `river>=0.21` を追加。MIT ライセンス。軽量で Python 3.11 対応。
- **scipy / numpy**: 統計計算（既存依存の可能性あり）。
- **pytest 用モック**: River の drift detector は状態を持つため、テストで deterministic にする必要あり。

### 実装手順（推奨）

1. **Phase 0**: River を依存に追加し、1〜2 メトリクス（例：`co2_high`, `temp_high`）で ADWIN によるドリフト検知を実験。
2. **Phase 1**: `ThresholdDriftLog` テーブルを追加し、検知結果を可視化（提案のみ、自動適用なし）。
3. **Phase 2**: ユーザーフィードバック（dismiss/confirm）を `ThresholdAdjuster` に統合。
4. **Phase 3**: `intervention_efficacy` を閾値調整に反映。
5. **Phase 4**: 複数メトリクス・季節性対応（contextual bandit や HTM 的アプローチを検討）。

## リスク・検討事項

### 技術的リスク

| リスク | 内容 | 対策 |
|--------|------|------|
| **False positive の増大** | ドリフトを過敏に捉え、正常変動を異常とする。 | `delta` パラメータを保守的に設定。複数 detector の投票（ensemble）を用いる。 |
| **閾値の暴走** | フィードバックが偏ると閾値が極端に寄る。 | オフセットに上限/下限を設ける。ユーザー承認制にする。 |
| **季節性との混同** | 夏の室温上昇をドリフトと誤認。 | 時刻・季節を特徴量に加え、context-aware な detector（HTM, AnDri）を検討。 |
| **計算コスト** | 多数のメトリクスで ADWIN を常時実行すると負荷。 | 重要メトリクスのみ対象。edge 側で簡易検知を行い、brain では集約検知。 |
| **解釈性の低下** | 動的閾値は「なぜその閾値？」と説明しにくい。 | 閾値変更理由（drift/feedback/efficacy）を常に記録し、LLM/ダッシュボードで説明。 |

### 運用上の罠

- **「全部異常」になる**：引っ越し後など abrupt drift で、旧閾値が一切当てはまらなくなる。ドリフト検知後のリセット基準を明確にする。
- **ユーザー疲労**：頻繁な閾値変更提案は無視される。提案頻度を制限（例：1日1回まで）。
- **ラベルなし運用**：HEMS は通常、異常の正解ラベルがない。Performance-based detector（DDM）は使いにくい。Distribution-based（ADWIN）を優先。
- **デバイス交換**：同じ device_id でデバイスが交換されると分布が変わる。デバイス履歴（firmware バージョン、model）を管理し、交換時に detector をリセット。

### 妥協点

- **完全自動化 vs 人間承認**: 安全系メトリクス（CO₂ 警報、SpO₂ 低下）は人間承認制。快適系（照明、温度）のみ自動化。
- **適応速度 vs 安定性**: `delta` を小さくすると遅いが安定。大きくすると速いが騒がしい。メトリクスごとに異なる `delta` を設定。
- **精度 vs 計算コスト**: 全メトリクスに DNN 予測器を置くのは重い。予測には Prophet / Holt-Winters / 移動平均を優先し、必要な箇所のみ LSTM/HTM を使う。

## 参考リンク

- River ML: https://riverml.xyz
- scikit-multiflow: https://scikit-multiflow.readthedocs.io
- PWPAE GitHub: https://github.com/Western-OC2-Lab/PWPAE-Concept-Drift-Detection-and-Adaptation
- Numenta NAB: https://github.com/numenta/NAB
- Grafana PromQL Anomaly Detection: https://github.com/grafana/promql-anomaly-detection
- Reckon (Prometheus exporter): https://github.com/waltzofpearls/reckon
- EnergiQ paper: https://pmc.ncbi.nlm.nih.gov/articles/PMC12390151/
- AnDri paper: https://arxiv.org/abs/2506.15831
- AdapAD paper: https://www.sciencedirect.com/science/article/pii/S254266052400355X
- Hundman et al. LSTM + Nonparametric Dynamic Thresholding: https://arxiv.org/abs/1802.04431
- Gama et al. (2004) DDM: https://doi.org/10.1007/978-3-540-28645-5_29
- Bifet & Gavalda (2007) ADWIN: https://doi.org/10.1137/1.9781611972771.42
- Gama et al. (2014) Survey on Concept Drift Adaptation: https://doi.org/10.1145/2523813
- Lu et al. (2018) Learning Under Concept Drift: https://doi.org/10.1109/TKDE.2018.2876857
