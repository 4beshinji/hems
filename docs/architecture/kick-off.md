共生型オフィス環境：大規模言語モデルとイベント駆動型エッジアーキテクチャによる自律的管理システムの構築

1. エグゼクティブサマリー

現代のオフィス環境管理は、従来の「自動化（Automation）」から「自律性（Agency）」へとパラダイムシフトの只中にある。既存のビル管理システム（BMS）は、温度センサーの閾値に基づく空調制御のような決定論的なルールベース処理には長けているが、文脈理解や物理的な柔軟性を欠いている。例えば、「窓が開いているため空調効率が低下しているが、外気を取り入れるために意図的に開けられているのか、閉め忘れなのか」といった状況判断や、「ロボットアームがない環境で窓を閉める」といった物理的介入は、従来のシステムでは不可能であった。

本報告書は、この限界を突破するために設計・実装された共生型オフィス環境管理システム（Symbiotic Office Management System: SOMS）のアーキテクチャと実装詳細を包括的に論じる技術研究報告書である。

本システムは、中央知能としてAMD RX 9700（RDNA4、16GB VRAM）上のOllamaで稼働するQwen2.5:14b大規模言語モデル（LLM）を中核に据え、MQTTメッセージバスを神経系として、エッジデバイス（ESP32）と人間を対等な「エージェント」として統合する。Docker Compose上で11サービスが連携し、完全にローカルで動作する自律型オフィス管理基盤を実現した。

特筆すべき技術的特徴は以下の通りである：

**オーケストレーションツールの排除とコードファーストアプローチ**: Node-REDやKubernetesのような重量級のミドルウェアを排除し、Pythonによる非同期イベントループとMQTTプロトコルを用いたシンプルかつ堅牢なイベント駆動型アーキテクチャ（EDA）を採用した。これにより、LLMがシステムの論理構造を直接理解・修正可能な「透明性」を確保している。

**MCP over MQTTプロトコル**: AIモデルとツール間の標準インターフェースであるModel Context Protocol（MCP）を、IoTの標準であるMQTT上に実装し、JSON-RPC 2.0ペイロードによる堅牢なツール呼び出しを実現した。10秒タイムアウトとasyncio.Futureによる非同期応答待ちを組み合わせ、物理デバイスの応答遅延を吸収する。

**視覚的グラウンディング**: YOLOv11（COCO事前学習重み）を用いた画像認識により、在室検知・活動分析・ホワイトボード状態のモニタリングを実現した。プラガブルなモニター設計とYAML設定により、カメラの追加・モニタータイプの変更を再起動なく行える。

**複式簿記経済圏の構築**: スマートホームAPIでは操作不可能な物理タスク（窓閉め、整理整頓等）を解決するため、LLMが報酬（500-5000ポイント）を発行し人間にタスクを依頼する経済システムを実装した。Walletサービスは独立した複式簿記台帳（Double-Entry Ledger）としてPostgreSQLのwalletスキーマ上に構築され、全取引のトレーサビリティを保証する。デバイスXPシステムにより、IoTデバイスの貢献度に応じた動的報酬倍率も実装されている。

**日本語音声合成による対話**: VOICEVOX（ナースロボ_タイプT、speaker_id=47）を用いた日本語音声合成により、タスクアナウンス・完了通知・リジェクション応答を音声で行う。リジェクションストック（最大100件）による事前生成と、デュアルボイス生成（アナウンス+完了の同時生成）により、低レイテンシかつ文脈に沿った音声体験を提供する。

**SensorSwarm 2階層アーキテクチャ**: Hub + Leafの2階層設計により、低コスト・乾電池駆動のLeafデバイスをESP32 Hubが集約しMQTTに橋渡しする。バイナリプロトコル（5-245バイト、MAGIC 0x53、XORチェックサム）と4種のトランスポート（ESP-NOW、UART、I2C、BLEスタブ）で、多様なマイコンプラットフォームに対応する。

本稿は、ハードウェア選定からプロンプトエンジニアリング、通信プロトコル設計、音声合成、経済システム、そして人間行動を促すためのインセンティブ設計に至るまで、実装済みシステムの全領域を網羅した技術研究報告書である。

2. 建築的パラダイム：自動化から自律的エージェンシーへ

2.1 従来のBMSの限界とエージェント型アプローチの必要性

従来のビル管理システム（BMS）は、IF-THEN形式の論理ゲートの集合体である。これは「室温が26度を超えたら冷房を入れる」といった単線的な制御には有効だが、多変量かつ非定型な現実世界の課題には対応できない。例えば、「重要な会議中で静寂が必要なため、室温が高くても空調の風量を下げたい」というニーズや、「CO2濃度が1000ppmを超えているが、在室者が集中作業中のため割り込みの優先度を下げたい」という複合的な判断を、センサーデータのみから推論し適切な行動を選択することはルールベースでは困難である。

本システム SOMS は、システム全体を一つの「有機体」として捉える。LLMが「脳」、MQTTバスが「神経系」、エッジデバイスが「感覚器」および「手足」、そして人間が「高度な外部アクチュエータ」として機能する。このシステムは、事前に定義されたルールに従うのではなく、「環境の快適性とエネルギー効率の最大化」という目的関数に向けて、自律的に思考し、ツールを選択し、行動する。

2.2 イベント駆動型アーキテクチャ（EDA）の採用

本システムでは、Node-REDのようなビジュアルプログラミングツールや、LangChainの複雑なチェーン構造を排し、純粋なPythonコードによる**イベント駆動型アーキテクチャ（EDA）**を採用した。これは以下の理由による。

**レイテンシとスループット**: MQTTブローカーを介したパブ/サブモデルは、HTTPリクエストのようなポーリングオーバーヘッドがなく、ミリ秒単位のリアルタイム通信が可能である。Brainサービスは `office/#`、`hydro/#`、`aqua/#`、`mcp/+/response/#` を購読し、状態変化をイベントとして検出する。

**ハイブリッドトリガー**: Brainの認知サイクルは、30秒間隔のポーリングとMQTTイベント駆動のハイブリッドで起動する。新しいイベントがWorldModelに登録されると `asyncio.Event` がセットされ、3秒のバッチ遅延の後に認知サイクルが開始される。これにより、複数のセンサーが同時に変化した場合も一度の推論サイクルで効率的に処理できる。

**状態の分離**: 各コンポーネント（視覚、推論、制御、音声、経済）は疎結合であり、互いの存在を直接知る必要がない。共通のMQTTトピックおよびREST APIを通じてのみ連携するため、システムの拡張性や保守性が高い。

**LLMとの親和性**: Pythonコードとして記述されたロジックは、テキストベースであるためLLMが解釈しやすく、将来的な「自己修復」や「コード生成による機能拡張」への道を開く。

2.3 システムトポロジー

システムは物理的・論理的に以下の4層で構成される。Docker Compose上の11サービスが協調動作する。

**中央知能層 (Central Intelligence Layer)**:
AMD RX 9700（RDNA4、16GB VRAM）搭載のGPUサーバー。Ollama上でQwen2.5:14b（Q4_K_M量子化）モデルが稼働し、ReActパターンによる高度な推論、タスク計画、自然言語処理を行う。`HSA_OVERRIDE_GFX_VERSION=12.0.1` によるROCm互換性設定でAMD GPUのコンピューティングを有効化している。

**知覚層 (Perception Layer)**:
カメラとYOLOv11モデルによる視覚情報の構造化。3種のプラガブルモニター（OccupancyMonitor、WhiteboardMonitor、ActivityMonitor）が `config/monitors.yaml` で宣言的に設定され、物理世界のアナログ情報をデジタルなJSONデータに変換する。

**神経伝達層 (Communication Layer)**:
MQTTブローカー（Mosquitto）と、その上で動作するMCPブリッジ（JSON-RPC 2.0）。パスワード認証によるアクセス制御を実装。

**物理・人間相互作用層 (Interaction Layer)**:
ESP32によるセンサー・アクチュエータ制御。SensorSwarm Hub+Leafアーキテクチャによる2階層センサーネットワーク。React 19/TypeScript/Vite 7ベースのダッシュボードとVOICEVOX音声合成による人間へのタスク依頼と報酬管理。PostgreSQL上のWalletサービスによる複式簿記経済システム。

3. 中央知能インフラストラクチャ：LLMと推論エンジン

3.1 モデル選定：Qwen2.5の優位性

本システムの中核には、Qwen2.5:14bを採用した。オープンモデルランドスケープにおいて、Qwen2.5は特に以下の点において優位性を持つ。

**命令追従能力 (Instruction Following)**: エージェントシステムにおいて最も重要なのは、OpenAI function-calling schemaを厳密に遵守する能力である。Qwen2.5はコーディングタスクでの高い性能に裏打ちされた論理的整合性を持ち、`tool_calls` フィールドの JSON 出力においてもエラー率が極めて低い。実測ベンチマークでは、12リクエスト連続でツール呼び出し精度100%を達成した。

**多言語対応**: オフィス環境の音声通知は日本語で行われるが、システムプロンプトとツール定義も日本語で記述されている。Qwen2.5の多言語能力により、日本語でのタスクタイトル・説明文の生成品質が高い。

**コンテキストウィンドウ**: 最大128kトークンのコンテキスト長をサポートしており、長時間のセンサーログ、アクティブタスク一覧、30分間のアクション履歴を参照しながらの推論が可能である。

**推論速度**: AMD RX 9700上でのOllama実行において約51 tokens/secの推論速度を達成しており、30秒の認知サイクル間隔に対して十分な応答性能を確保している。

3.2 AMD RX 9700（RDNA4）環境における最適化戦略

本システムのGPU環境はAMD RX 9700（RDNA4、gfx1201、16GB VRAM）である。NVIDIAのCUDAエコシステムとは異なり、ROCm（Radeon Open Compute）スタックを用いる。

3.2.1 量子化 (Quantization)

Qwen2.5:14Bモデルを16GB VRAMに収めるため、**Q4_K_M量子化**を採用した。Ollamaが提供する量子化済みモデル（約9.0GB）により、十分なKVキャッシュ容量を確保しつつ高品質な推論を維持している。

- モデルサイズ: 約9.0GB（Q4_K_M量子化後）
- KVキャッシュ: 残りの約7GBをKVキャッシュおよびランタイムオーバーヘッドに割当
- 推論速度: 約51 tokens/sec
3.2.2 推論エンジン：Ollamaの採用

推論エンジンにはOllamaを採用した。Ollamaは以下の利点を提供する。

- **ROCm対応**: `ollama/ollama:rocm` Dockerイメージにより、AMD GPUネイティブなコンピューティングが可能。`HSA_OVERRIDE_GFX_VERSION=12.0.1` の環境変数設定により、RDNA4アーキテクチャとの互換性を確保している。
- **OpenAI互換API**: `/v1/chat/completions` エンドポイントを提供するため、Brain の LLMClient は標準的な OpenAI クライアント形式でリクエストを送信できる。温度パラメータ 0.3、最大トークン数 1024、タイムアウト 120秒の設定で運用している。
- **モデル管理**: `ollama_models` Docker ボリュームによるモデルの永続化と、コンテナ再起動時の自動ロードを実現している。

3.2.3 GPU分離設計

サーバーには2つのGPUが搭載されている。

| GPU | 用途 | PCIアドレス | DRIノード |
|-----|------|------------|-----------|
| AMD RX 9700 (dGPU) | ROCm コンピュート | 03:00.0 | card1/renderD128 |
| AMD Raphael (iGPU) | ディスプレイ出力 | 0e:00.0 | card2/renderD129 |

Docker コンテナには dGPU のデバイスノード (`/dev/kfd`, `/dev/dri/card1`, `/dev/dri/renderD128`) のみをパススルーする。`/dev/dri` 全体を渡すと iGPU のリセットが発生し、GNOME デスクトップがクラッシュするため、この分離設計は安定運用上必須である。

3.3 プロンプトエンジニアリング：憲法的AIアプローチ

LLMを単なるチャットボットから「オフィス管理者」に変貌させるため、「憲法的AI（Constitutional AI）」のアプローチを取り入れたシステムプロンプトを実装した。

3.3.1 システムプロンプトの構成要素

**役割定義**: 「あなたは自律型オフィス管理AI『Brain』です。センサーデータとイベント情報を分析し、オフィスの快適性と安全性を維持します。」

**行動原則**: 5つの原則を明示的に規定している。
1. 安全第一: 人の健康・安全に関わる問題は最優先
2. コスト意識: 報酬ポイントは適切に設定（簡単: 500-1000、中程度: 1000-2000、重労働: 2000-5000）
3. 重複回避: `get_active_tasks` で既存タスクを確認し類似タスクを作成しない
4. 段階的対応: まず状況を確認し、必要な場合のみアクション
5. プライバシー: 個人を特定する情報は扱わない

**判断基準**: 具体的な閾値を数値で規定している。
- 温度: 18-26度が快適範囲
- 湿度: 30-60%が快適範囲
- CO2: 1000ppm未満が正常
- 照度: 300lux以上が作業に適切

**ツール選択ガイド**: `speak`（音声のみ・行動不要）と `create_task`（人間のアクションが必要）の使い分け基準を詳細に記述している。正常時にspeakを使用することは明示的に禁止されている。

**制約**: 1サイクルで作成するタスクは最大2件まで。正常範囲内のデータに対してはアクションを起こさない。

3.3.2 構造化出力：OpenAI Function Calling Schema

LLMの出力制御には、OpenAI互換のFunction Calling Schemaを採用した。ツール定義は `tool_registry.py` で以下の形式で宣言されている。

```json
{
    "type": "function",
    "function": {
        "name": "create_task",
        "description": "ダッシュボードに人間向けタスクを作成する。...",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "..."},
                "bounty": {"type": "integer", "description": "..."},
                "urgency": {"type": "integer", "description": "緊急度 0-4"}
            },
            "required": ["title", "description"]
        }
    }
}
```

LLMが `tool_calls` を含むレスポンスを返した場合、`LLMClient._parse_response()` が OpenAI 互換形式をパースし、`ToolExecutor` がルーティングと実行を行う。Sanitizer がバウンティ上限（5000）、緊急度範囲（0-4）、レート制限（10タスク/時間）、speak クールダウン（5分/ゾーン）などのバリデーションを事前に適用する。

3.4 ReAct認知ループの実装

Brain の認知サイクルは ReAct（Think → Act → Observe）パターンで実装されている。

**ループ制御パラメータ**:
- 最大イテレーション: 5回（`REACT_MAX_ITERATIONS = 5`）
- ポーリング間隔: 30秒（`CYCLE_INTERVAL = 30`）
- イベントバッチ遅延: 3秒（`EVENT_BATCH_DELAY = 3`）
- 最小サイクル間隔: 25秒（`MIN_CYCLE_INTERVAL = 25`）
- speak上限: 1回/サイクル（`MAX_SPEAK_PER_CYCLE = 1`）
- 連続エラー上限: 1回（`MAX_CONSECUTIVE_ERRORS = 1`）

**ガード機構**: ReActループ内には3層のガードが実装されている。
1. **重複検出**: 同一サイクル内で同一ツール+引数の組み合わせの再実行を防止
2. **speak制限**: サイクルあたりの speak 呼び出しを1回に制限
3. **連続エラー停止**: 連続エラーが閾値に達した場合にサイクルを中断

**アクション履歴（Layer 5）**: 過去30分間のツール実行履歴をLLMコンテキストに注入し、短期間の同一アクション繰り返しを防止する。履歴は2時間でプルーニングされる。

**コンテキスト構築**: 各サイクルで以下の情報がLLMに提供される。
1. WorldModelから取得した全ゾーンの現在状態
2. 直近5分間のイベント一覧
3. 現在のアクティブタスク一覧（重複作成防止用）
4. 直近30分のBrainアクション履歴

4. 神経系：MCP over MQTT プロトコル設計

4.1 通信プロトコルの選定理由

Model Context Protocol (MCP) は、AIモデルがツールやデータソースと対話するための標準仕様であるが、通常はHTTP (SSE) や stdio 上で動作する。IoT環境においては以下の理由からMQTTが最適であり、本システムではMQTT上にMCPを実装した。

**非同期性**: LLMの推論（数秒）と物理デバイスの動作（数ミリ秒から数分）の時間的非対称性を、ブローカーがバッファリングすることで吸収できる。MCPBridgeは `asyncio.Future` と10秒タイムアウトでこの非対称性を管理する。

**軽量性**: ヘッダオーバーヘッドが小さく、ESP32のような低リソースデバイスでも容易に実装可能。エッジ側のMCPクライアントは `soms_mcp.py` の共有ライブラリとして50行程度で実装されている。

**耐障害性**: ネットワーク切断時の再送制御（QoS）がプロトコルレベルでサポートされている。

4.2 トピック設計と名前空間

MQTTのトピック設計は、システムのAPI定義に等しい。本システムでは以下の階層構造を採用している。

```
office/{zone}/{device_type}/{device_id}/{channel}
```

**テレメトリ（センサーデータ）**:
```
office/main/sensor/env_01/temperature    → {"value": 24.5}
office/main/sensor/env_01/humidity       → {"value": 55.2}
office/main/sensor/env_01/co2            → {"value": 820}
office/kitchen/camera/cam_01/status      → {"status": "online"}
office/main/activity/activity_01         → {"persons": 2, ...}
```

テレメトリペイロードは統一フォーマット `{"value": X}` を採用している。これにより WorldModel の `update_from_mqtt()` メソッドが一貫したパース処理で全チャンネルを処理できる。

**SensorSwarm テレメトリ（Hub代理publish）**:
```
office/main/sensor/swarm_hub_01.leaf_env_01/temperature  → {"value": 22.5}
office/main/sensor/swarm_hub_01.leaf_pir_01/motion       → {"value": 1}
office/main/sensor/swarm_hub_01.leaf_door_01/door        → {"value": 0}
office/main/sensor/swarm_hub_01/heartbeat → {"status":"online","leaf_count":3}
```

`device_id` にドット区切り（`swarm_hub_01.leaf_env_01`）を用いることで、WorldModel への変更を最小限に抑えつつ Hub-Leaf 階層を表現している。

**MCP制御チャネル**:
```
mcp/{agent_id}/request/call_tool          → JSON-RPC 2.0 リクエスト
mcp/{agent_id}/response/{request_id}      → JSON-RPC 2.0 レスポンス
```

Brain は `mcp/+/response/#` を購読し、全エージェントからのレスポンスをキャッチする。

4.3 MCP over MQTT パケット構造

MCPのJSON-RPC 2.0メッセージをMQTTペイロードにカプセル化する。

**リクエスト（LLM -> Edge）**:
トピック: `mcp/esp32_01/request/call_tool`
```json
{
    "jsonrpc": "2.0",
    "method": "call_tool",
    "params": {
        "name": "set_led_color",
        "arguments": {"r": 255, "g": 0, "b": 0}
    },
    "id": "req-uuid-12345"
}
```

**レスポンス（Edge -> LLM）**:
トピック: `mcp/esp32_01/response/req-uuid-12345`
```json
{
    "jsonrpc": "2.0",
    "result": {
        "content": [{"type": "text", "text": "LED set to red"}]
    },
    "id": "req-uuid-12345"
}
```

**SensorSwarm MCPコマンド（Brain → Hub → Leaf）**:
```python
send_device_command(
    agent_id="swarm_hub_01",
    tool_name="leaf_command",
    arguments='{"leaf_id":"leaf_relay_01","command":"set_state","args":{"state":"on"}}'
)
```

Hub は `leaf_command` と `get_swarm_status` の2つのMCPツールを公開している。

4.4 Pythonブリッジの実装

中央サーバー上では、`MCPBridge` クラスがMQTTブローカーとLLMを繋ぐ。`paho-mqtt` ライブラリ（v2.0+、CallbackAPIVersion.VERSION2）と `asyncio` を用いて実装されている。

**動作ロジック**:
1. LLMがツール実行を決定すると、ブリッジは `uuid.uuid4()` で一意な `request_id` を生成し、該当するMQTTトピックへリクエストをPublishする。
2. 同時に、`request_id` をキーとして `asyncio.Future` オブジェクトを生成し、`pending_requests` マップに保存する。
3. エッジデバイスからのレスポンスが `mcp/+/response/#` トピックに届くと、`handle_response()` が `request_id` を照合し、`call_soon_threadsafe` で対応する Future を完了させる（MQTTコールバックはネットワークスレッドで実行されるため、asyncioスレッドへのブリッジが必要）。
4. `asyncio.wait_for()` により10秒のタイムアウトが設定されており、デバイスが応答しない場合は `TimeoutError` が発生する。

5. 視覚的知覚システム

5.1 YOLOv11によるプラガブルモニター設計

知覚層は `services/perception/` に実装され、YOLOv11（Ultralytics）をベースとした3種のモニターが稼働する。モニターは `config/monitors.yaml` で宣言的に設定され、コード変更なくカメラの追加・モニタータイプの変更が可能である。

5.1.1 モニタータイプ

| モニター | 用途 | YOLO モデル |
|---------|------|------------|
| OccupancyMonitor | 在室人数の検出 | yolo11s.pt (COCO事前学習) |
| WhiteboardMonitor | ホワイトボード状態の監視 | yolo11s.pt (COCO事前学習) |
| ActivityMonitor | 姿勢・活動レベルの分析 | yolo11s-pose.pt (COCO事前学習) |

全モニターは COCO データセットで事前学習された標準重みを使用しており、カスタムトレーニングは行っていない。COCO の 80 クラス（person, chair, bottle 等）の検出で、オフィス環境の監視に十分な精度を実現している。

5.1.2 ActivityAnalyzer：階層的ポーズバッファ

ActivityMonitor の中核である `ActivityAnalyzer` は、4階層の時間減衰バッファを実装している。

| 階層 | 保持期間 | 解像度 | 最大エントリ数 |
|------|---------|--------|-------------|
| Tier 0 (raw) | 60秒 | 全フレーム | 約20 |
| Tier 1 (10s) | 10分 | 10秒/サマリー | 約60 |
| Tier 2 (1min) | 1時間 | 60秒/サマリー | 約60 |
| Tier 3 (5min) | 4時間 | 300秒/サマリー | 約48 |

合計最大188エントリで最大4時間の履歴をカバーする。各サマリーは腰中心・肩幅正規化された姿勢シグネチャを保持し、位置・スケール不変な姿勢比較を可能にしている。20分以上同一姿勢を維持した場合に `static` 判定が行われ、Brain への `sedentary_alert` イベントとして通知される。

5.1.3 カメラ自動検出

`CameraDiscovery` モジュールにより、ネットワーク上のカメラを自動検出する機能を実装した。ICMPピングスイープでネットワーク内のホストを検出し、オプションでYOLO推論による映像検証を行った上で、自動的にActivityMonitorを登録する。検出結果は `office/perception/discovery` トピックにMQTTで公開される。

5.1.4 画像ソースの抽象化

画像取得は `ImageSourceFactory` を通じて抽象化されており、以下の3種をサポートする。
- **RTSPSource**: IPカメラからのRTSPストリーム
- **MQTTSource**: MQTTトピック経由の画像データ
- **HTTPStream**: HTTPストリーミング（virtual-camera対応）

5.2 知覚データのWorldModel統合

WorldModelは知覚層からのMQTTメッセージを受信し、ゾーン単位の統合状態を維持する。特にSensorSwarmからの `motion` チャンネルは `pir_detected` フラグおよび在室推定（occupancy fusion）に変換され、`door` チャンネルは `door_opened`/`door_closed` イベントとして生成される。

6. バイオ・デジタル経済圏：人間参加型（HITL）統合

6.1 クレジット経済の設計と実装

スマートホームAPIで操作できない物理的タスク（窓閉め、ホワイトボードの清掃、コーヒー豆の補充等）を解決するため、システムは人間を「高度な汎用アクチュエータ」として扱う。インセンティブ設計（ナッジ理論）に基づくポイント経済を実装した。

**通貨**: クレジット（ポイント）。Wallet サービスで管理。音声告知時の単位名は毎回ランダムに変化（「お手伝いポイント」「AI奴隷ポイント」等）。
**報酬レンジ**: タスクの難易度と緊急度に応じて、LLMが500-5000ポイントの範囲で報酬額を動的に決定する。
**緊急度レベル**: 0（後回し可）から 4（緊急）の5段階。urgency >= 4 は TaskDispatchDecision により即座にディスパッチされる。

6.2 Walletサービス：複式簿記台帳

経済システムの整合性を保証するため、独立した Wallet サービス（ポート 8003）を PostgreSQL 16 の `wallet` スキーマ上に実装した。単純な残高の加減算ではなく、全取引を DEBIT/CREDIT のペアとして記録する**複式簿記（Double-Entry Ledger）**を採用している。

6.2.1 データモデル

| モデル | 役割 |
|--------|------|
| Wallet | ユーザーウォレット。`user_id=0` はシステムウォレット（通貨発行元）。残高は非負制約（システムウォレットを除く）。 |
| LedgerEntry | 台帳エントリ。`transaction_id`（UUID）で取引をグループ化。`amount`（正=credit、負=debit）、`balance_after`、`entry_type`（DEBIT/CREDIT）、`transaction_type`（INFRASTRUCTURE_REWARD/TASK_REWARD/P2P_TRANSFER）。 |
| Device | デバイス登録。`device_id`、`owner_id`、`device_type`（llm_node/sensor_node/hub）、`xp`（経験値）。 |
| RewardRate | デバイスタイプ別報酬レート（milli-units/時間）。 |
| SupplyStats | 通貨供給統計（total_issued, total_burned, circulating）。 |

6.2.2 デバイスXPシステム

`xp_scorer.py` はゾーンベースのXP分配を実装している。タスクが作成・完了されると、そのゾーンに登録された全アクティブデバイスにXPが付与される。デバイスのXPに基づく動的報酬倍率は以下の式で計算される。

```
multiplier = min(1.0 + (xp / 1000.0) * 0.5, 3.0)
```

- 0 XP: 1.0倍、1000 XP: 1.5倍、4000 XP: 3.0倍（上限）

これにより、より良いセンサー配置 → より有用なデータ → より多くのタスク → より多くのXP → より高い報酬という正のフィードバックループが形成される。

6.2.3 APIエンドポイント

Walletサービスは4つのルーターを提供する。

| ルーター | 機能 |
|---------|------|
| wallets | ウォレット作成・残高照会 |
| transactions | タスク報酬・P2P送金（複式簿記） |
| devices | デバイス登録・XP付与 |
| admin | 報酬レート管理・供給統計 |

6.3 React/FastAPIダッシュボードのアーキテクチャ

人間とのインターフェースとなるダッシュボードは、リアルタイム性を重視したシングルページアプリケーション（SPA）として実装した。

6.3.1 技術スタック

| コンポーネント | 技術 | バージョン |
|---------------|------|-----------|
| Frontend | React + TypeScript | React 19.2, TypeScript 5.9 |
| ビルドツール | Vite | 7.3 |
| スタイリング | Tailwind CSS | 4.1 |
| アニメーション | Framer Motion | 12.x |
| アイコン | Lucide React | 0.563 |
| バックエンド | Python FastAPI | - |
| ORM | SQLAlchemy (async) | - |
| DB (Docker) | PostgreSQL 16 (asyncpg) | - |
| DB (フォールバック) | SQLite (aiosqlite) | - |
| リアルタイム更新 | HTTP ポーリング（5秒間隔） | - |

リアルタイム更新にはWebSocketではなくHTTPポーリング（5秒間隔）を採用している。WebSocketの接続管理の複雑さと、5秒間隔で十分な応答性が得られることのトレードオフによる実用的な判断である。

6.3.2 データベーススキーマ設計

Taskモデルは19カラムを持つ包括的な設計となっている。

```python
class Task(Base):
    __tablename__ = "tasks"
    id           = Column(Integer, primary_key=True)
    title        = Column(String, index=True)
    description  = Column(String)
    location     = Column(String)
    bounty_gold  = Column(Integer, default=10)
    bounty_xp    = Column(Integer, default=50)
    is_completed = Column(Boolean, default=False)
    announcement_audio_url = Column(String, nullable=True)
    announcement_text      = Column(String, nullable=True)
    completion_audio_url   = Column(String, nullable=True)
    completion_text        = Column(String, nullable=True)
    created_at    = Column(DateTime, server_default=func.now())
    completed_at  = Column(DateTime, nullable=True)
    expires_at    = Column(DateTime, nullable=True)
    task_type     = Column(String, nullable=True)
    urgency             = Column(Integer, default=2)  # 0-4
    zone                = Column(String, nullable=True)
    min_people_required = Column(Integer, default=1)
    estimated_duration  = Column(Integer, default=10)
    is_queued           = Column(Boolean, default=False)
    dispatched_at       = Column(DateTime, nullable=True)
    last_reminded_at = Column(DateTime, nullable=True)
    assigned_to = Column(Integer, nullable=True)
    accepted_at = Column(DateTime, nullable=True)
```

音声関連4フィールドにより、タスク作成時に生成された音声データがタスクレコードに永続化される。ダッシュボードの音声再生は追加のAPI呼び出しなしに実現される。

6.3.3 タスク重複検出

ToolExecutor の `create_task` 実行前に、2段階の重複検出が行われる。

1. **タイトル+ロケーション一致**: 同一タイトルかつ同一ゾーンの既存タスクが存在するかチェック
2. **ゾーン+タスクタイプ一致**: 同一ゾーンかつ同一タスクタイプの既存タスクが存在するかチェック

加えて、認知サイクル時にアクティブタスク一覧がLLMコンテキストに注入され、「上記タスクと同じ目的のタスクを新規作成しないでください」という指示が付与される。

6.3.4 nginx リバースプロキシ

フロントエンドの nginx は、マルチサービスへのリクエストルーティングを担う。

| パス | ルーティング先 | 説明 |
|------|---------------|------|
| `/api/wallet/` | wallet:8000 | Walletサービス |
| `/api/voice/` | voice-service:8000 | 音声サービス |
| `/api/` | backend:8000 | ダッシュボードバックエンド |
| `/audio/` | voice-service:8000 | 音声ファイル配信 |
| `/` | 静的ファイル | React SPA |

6.4 インタラクションフロー

1. **タスク生成**: LLMが `create_task` ツールを実行。ToolExecutor が DashboardClient を呼び出す。
2. **音声生成**: DashboardClient が Voice サービスの `announce_with_completion` を呼び出し、アナウンス音声と完了音声の2つを同時生成する。
3. **タスク登録**: 音声URLを含むペイロードが Dashboard Backend に POST される。TaskQueueManager がディスパッチ判定を行う。
4. **フロントエンド通知**: React SPA が5秒ポーリングで新規タスクを検出し、AudioQueue にアナウンス音声を enqueue する。
5. **受注**: ユーザーが「受注（Accept）」ボタンを押す。`assigned_to` と `accepted_at` が更新され、Voice サービスの `synthesize` エンドポイントで受諾音声が即時生成される。
6. **完了**: ユーザーが「完了（Complete）」ボタンを押す。タスクレコードに保存済みの `completion_audio_url` が AudioQueue で再生される。
7. **無視**: ユーザーが「無視（Ignore）」ボタンを押す。リジェクションストックから事前生成済みの音声が即座に返される。

7. 音声合成サービス

7.1 アーキテクチャ

音声サービス（`services/voice/`）は VOICEVOX エンジン（speaker_id=47: ナースロボ_タイプT）を用いた日本語音声合成を提供する。

7.1.1 エンドポイント

| エンドポイント | メソッド | 機能 |
|---------------|---------|------|
| `/api/voice/synthesize` | POST | テキスト直接合成（Brain の speak ツール用） |
| `/api/voice/announce` | POST | LLMテキスト生成 + 音声合成（タスクアナウンス） |
| `/api/voice/announce_with_completion` | POST | デュアルボイス生成（アナウンス+完了） |
| `/api/voice/feedback/{type}` | POST | フィードバック音声生成 |
| `/api/voice/rejection/random` | GET | リジェクションストックから即座取得 |
| `/api/voice/rejection/status` | GET | ストック状況確認 |
| `/api/voice/rejection/clear` | POST | ストック全消去 |
| `/audio/{filename}` | GET | 音声ファイル配信 |
| `/audio/rejections/{filename}` | GET | リジェクション音声配信 |

7.1.2 リジェクションストック

`RejectionStock` クラスは、最大100件のリジェクション音声を事前生成して保持する。アイドル時にバックグラウンドタスクとしてLLMテキスト生成 + VOICEVOX合成を実行し、ストックを補充する。ストックが80件を下回ると補充が開始される。ユーザーがタスクを無視した際の音声応答はストックからの即座取得（レイテンシほぼゼロ）で返される。

7.1.3 Mock LLMのデュアルモード

Mock LLM（`infra/mock_llm/`）は、リクエストに `tools` パラメータが含まれるか否かで動作モードを切り替える。

- **tools あり（Brain モード）**: キーワードマッチングによるツール呼び出しレスポンスを生成
- **tools なし（Voice テキスト生成モード）**: 音声サービスからのテキスト生成リクエストとして処理

7.2 AudioQueue：優先度ベースの音声再生

フロントエンドの `AudioQueue` シングルトンが全音声再生を管理する。

| 優先度 | 値 | 用途 |
|--------|---|------|
| USER_ACTION | 0 (最高) | 受諾・完了・無視の応答音声 |
| ANNOUNCEMENT | 1 | タスクアナウンス |
| VOICE_EVENT | 2 (最低) | speak ツールの音声イベント |

最大キューサイズ20件、同一優先度内はFIFO順、`useSyncExternalStore` でReactと状態同期、シーケンシャル再生。

8. エッジエンジニアリング：ESP32とSensorSwarm

8.1 ESP32による分散制御

エッジデバイスにはESP32を採用。2つのファームウェアバリアントが存在する。

- **MicroPython (`edge/office/`)**: 本番用。BME680、MH-Z19C CO2、DHT22センサー接続。
- **PlatformIO C++ (`edge/test-edge/`)**: 開発・テスト用。

8.1.1 センサー構成

| センサー | 測定項目 | インターフェース |
|---------|---------|----------------|
| BME680 | 温度、湿度、気圧、VOC | I2C (SDA=GPIO23, SCL=GPIO22) |
| MH-Z19C | CO2濃度 | UART (TX=GPIO1, RX=GPIO0) |
| DHT22 | 温度、湿度 | GPIO デジタル |

8.1.2 ファームウェア設計

ESP32のコードは「シン・クライアント」設計に基づく。`soms_mcp.py` 共有ライブラリが MCP の JSON-RPC 2.0 通信を抽象化し、テレメトリはチャンネルごとに個別トピックで publish される。

8.2 SensorSwarm：2階層センサーネットワーク

Hub + Leaf の2階層アーキテクチャで、低コスト・乾電池駆動の Leaf デバイスを ESP32 Hub が集約し MQTT に橋渡しする。

8.2.1 バイナリプロトコル

| 項目 | 仕様 |
|------|------|
| フレームサイズ | 5-245 バイト（ESP-NOW 250B制限内） |
| ヘッダ | Magic(0x53) + Version + MsgType + LeafID |
| チェックサム | XOR 全バイト |
| エンコード | Little-endian float、MicroPython struct 互換 |
| メッセージ型 | SENSOR_REPORT, HEARTBEAT, REGISTER, COMMAND, ACK, WAKE, CONFIG, TIME_SYNC |
| チャンネル型 | 14種（temperature, humidity, co2, motion, door, battery_mv 等） |

8.2.2 トランスポート層（4種）

| トランスポート | 対象プラットフォーム | 状態 |
|---------------|-------------------|------|
| ESP-NOW | ESP32-C3/C6 | 実装済み |
| UART | Raspberry Pi Pico | 実装済み |
| I2C | ATtiny | 実装済み |
| BLE | nRF54L15 | スタブ |

8.2.3 仮想エミュレータ

Docker 統合テスト用に `infra/virtual_edge/` に仮想エミュレータを実装。SwarmHub + 3 Leaf（TempHumidity, PIR, Door）をエミュレートし、E2E テストで検証済み。

8.3 WorldModel統合

- **motion → occupancy fusion**: PIR検知を在室人数推定に統合
- **door → event generation**: ドア状態変化から `door_opened`/`door_closed` イベントを生成

9. インフラストラクチャと運用

9.1 Docker Compose構成（11サービス）

| サービス | コンテナ名 | ポート | GPU |
|---------|-----------|--------|-----|
| mosquitto | soms-mqtt | 1883, 9001 | - |
| brain | soms-brain | - | - |
| postgres | soms-postgres | 5432 | - |
| backend | soms-backend | 8000 | - |
| frontend | soms-frontend | 80 | - |
| voicevox | soms-voicevox | 50021 | - |
| voice-service | soms-voice | 8002 | - |
| wallet | soms-wallet | 8003 | - |
| ollama | soms-ollama | 11434 | RX 9700 |
| mock-llm | soms-mock-llm | 8001 | - |
| perception | soms-perception | host network | RX 9700 |

9.2 MQTT認証

Mosquitto は `allow_anonymous false` で設定。パスワードファイルによるユーザー認証を要求する。

9.3 データベース構成

| サービス | DB | ドライバ | スキーマ |
|---------|-----|---------|---------|
| Dashboard Backend | PostgreSQL 16 | asyncpg | public |
| Wallet Service | PostgreSQL 16 | asyncpg | wallet |
| フォールバック | SQLite | aiosqlite | - |

10. システムの安全性

10.1 LLM幻覚への多層防御

| 検証項目 | 制約 |
|---------|------|
| bounty上限 | 最大5000ポイント |
| urgency範囲 | 0-4 |
| タスク作成レート | 最大10件/時間 |
| speak クールダウン | 5分/ゾーン |
| デバイスホワイトリスト | `allowed_devices` + `swarm_hub*` |
| 温度設定範囲 | 18-28度 |

加えて、ReActループガード（重複防止、speak制限、連続エラー停止）およびアクション履歴注入（30分）が機能する。

10.2 プライバシー保護

カメラ映像はオンメモリ処理のみ。YOLO推論結果はJSON変換後に画像を破棄。システムプロンプトに個人情報不使用の原則を明記。

11. 運用ケーススタディ：「高温検知プロトコル」

1. ESP32 BME680 が 30.5度を検出 → `office/main/sensor/env_01/temperature` に `{"value": 30.5}` を publish
2. WorldModel が main ゾーンを更新、`high_temperature` イベント生成
3. `asyncio.Event` セット → 3秒バッチ遅延 → 認知サイクル開始
4. `get_active_tasks` で重複チェック
5. Qwen2.5:14b が `create_task` ツール呼び出しを生成（bounty=1500, urgency=3）
6. Sanitizer 検証通過
7. Voice サービスで `announce_with_completion` → アナウンス+完了音声を同時生成
8. Dashboard Backend に POST → TaskQueueManager が urgency=3 で即時ディスパッチ
9. フロントエンド 5秒ポーリングで検出 → AudioQueue で再生 → TaskCard 表示
10. 社員が受注 → 実行 → 完了 → 完了音声再生 → Wallet 経由で 1500pt 付与

12. 結論

本システムは、LLMの認知能力とIoTの接続性を融合させ、従来の自動化の限界を超えるアプローチを実証した。

**コードファースト設計**: Pythonコードと MCP over MQTT で論理を構成し、LLM がシステムの API を直接理解・操作できる透明性を確保した。

**完全ローカル動作**: AMD RX 9700（16GB VRAM）上で LLM推論・音声合成・画像認識の全てをローカル実行。プライバシーを保護する。

**複式簿記経済圏**: 全取引を DEBIT/CREDIT ペアで記録し、デバイスXPによる動的報酬倍率を実装した。

**SensorSwarm拡張性**: Hub+Leaf 2階層設計と4種トランスポートで多様なマイコンを統合する。

**多層安全機構**: Sanitizer・ReActガード・アクション履歴・レート制限の6層防御を実装した。

今後の課題: BLEトランスポート実装完了、受諾音声ストック化、SensorSwarm実機検証。

付録：データテーブルと仕様

**表1: LLMツール定義**

| ツール | 必須パラメータ | オプション | 用途 |
|--------|-------------|----------|------|
| create_task | title, description | bounty(500-5000), urgency(0-4), zone, task_types | タスク作成 |
| send_device_command | agent_id, tool_name | arguments(JSON) | デバイス制御 |
| get_zone_status | zone_id | - | ゾーン状態取得 |
| speak | message(70字以内) | zone, tone | 音声通知 |
| get_active_tasks | - | - | タスク一覧 |

**表2: 報酬設計マトリクス**

| タスク種別 | 難易度 | 報酬レンジ |
|-----------|--------|-----------|
| 環境調整（照明・空調） | 低 | 500-1000 |
| 換気・加湿 | 低-中 | 800-1200 |
| 備品補充 | 中 | 1000-1500 |
| 緊急環境対応 | 中 | 1500-2000 |
| 重労働・清掃 | 高 | 2000-5000 |

**表3: MQTT テレメトリ例**

| トピック | ペイロード | 発行元 |
|---------|-----------|--------|
| `office/main/sensor/env_01/temperature` | `{"value": 24.5}` | ESP32 (BME680) |
| `office/main/sensor/env_01/humidity` | `{"value": 55.2}` | ESP32 (BME680) |
| `office/main/sensor/env_01/co2` | `{"value": 820}` | ESP32 (MH-Z19C) |
| `office/main/sensor/swarm_hub_01.leaf_env_01/temperature` | `{"value": 22.5}` | SwarmHub代理 |
| `office/main/sensor/swarm_hub_01.leaf_pir_01/motion` | `{"value": 1}` | SwarmHub代理 |
| `mcp/esp32_01/request/call_tool` | JSON-RPC 2.0 | Brain |

**表4: ハードウェア構成**

| コンポーネント | 詳細 |
|---------------|------|
| CPU | AMD Ryzen 7 9800X3D (8C/16T) |
| dGPU | AMD RX 9700 (RDNA4, gfx1201, 16GB VRAM) |
| iGPU | AMD Raphael (gfx1036, ディスプレイ用) |
| カーネル | 6.17.0-14-generic |
| Ollama | v0.16.0 (rocm) |
| LLM | Qwen2.5:14b (Q4_K_M, 9.0GB, ~51 tok/s) |
| TTS | VOICEVOX (speaker_id 47) |
| ROCm | HSA_OVERRIDE_GFX_VERSION=12.0.1 |