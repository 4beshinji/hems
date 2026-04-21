# Ollama → llama.cpp 移行設計書

本ドキュメントは hems プロジェクト内の Ollama 依存箇所を llama.cpp（および補助サービス）へ置き換えるためのリファクタ計画です。**完全ローカルホスティング前提**で記述しています。

本 PJ は他 PJ と異なり、**Ollama 固有 API（`/api/chat`、`/api/embed`、`/api/tags`、`/api/generate`）を直接叩いている箇所が多数**あります。単純な URL 差し替えでは終わらず、コードの書き換えが必要です。

---

## 1. 現状調査サマリ

### 1.1 サービス別 Ollama 利用箇所

| サービス | ファイル | 主な行 | 用途 | エンドポイント | モデル |
|---|---|---|---|---|---|
| **news-bridge** | `src/news_summarizer.py` | 89–186 | 日次サマリ + 翻訳 | `POST /api/chat` | `qwen3.5` (env `OLLAMA_MODEL`) |
| news-bridge | `src/urgency.py` | 14–55 | 緊急度スコアリング | `POST /api/chat` | 同上 |
| news-bridge | `src/main.py` | 154–159 | 初期化 | — | — |
| news-bridge | `src/config.py` | 13–16 | 環境変数 | — | — |
| **perception** | `src/vlm_analyzer.py` | 38–269 | シーン解析（VLM） | `POST /api/chat`, `GET /api/tags`, `POST /api/generate` (unload) | `moondream`, `minicpm-v` |
| perception | `src/main.py` | 24–27, 330–351 | VLM 初期化 | — | — |
| perception | `src/config.py` | 30–42 | 環境変数 | — | — |
| **knowledge-bridge** | `src/embedding.py` | 1–200 | 埋め込み（単発・バッチ） | `POST /api/embed` | `nomic-embed-text` |
| knowledge-bridge | `src/config.py` | 35–42 | 環境変数 | — | — |
| **stt** | `src/query_cleaner.py` | 56–132 | 認識結果クリーン | `POST /v1/chat/completions` | env `STT_LLM_MODEL` / `LLM_MODEL` |
| **brain** | `src/llm_client.py` | 42–98 | ReAct チャット（tool 呼出） | `POST /api/chat` (Ollama native) | `LLM_MODEL` (例 `mistral-small:24b`) |
| brain | `src/persona_rewriter.py`, `ambient_speaker.py`, `event_automation.py` | — | 発話書換・周辺発話 | LLMClient 経由 | 同上 |
| **infra/docker-compose.yml** | 415–459 | — | `ollama` + `ollama-pull` サービス | port 11444→11434 | profile `ollama` |
| **infra/scripts/gpu_setup.py** | 312–351 | — | ROCm/CUDA イメージ切替 | — | `ollama/ollama:rocm` 等 |
| **env.example** | 46–62, 222–265, 277–279 | — | LLM/VLM/EMBED/STT 環境変数 | — | — |
| **CLAUDE.md** / **README.md** | 各所 | — | セットアップ・運用記述 | — | — |

### 1.2 Ollama 固有 API の利用箇所（書き換え必須）

| API | 利用ファイル | 用途 | llama.cpp 対応 |
|---|---|---|---|
| `POST /api/chat` | news-bridge, perception VLM, brain | チャット完了 | `POST /v1/chat/completions` で代替（応答スキーマ差あり） |
| `POST /api/embed` | knowledge-bridge | 単発・バッチ埋め込み | `POST /v1/embeddings` で代替（embedding 専用 server プロセス） |
| `GET /api/tags` | perception VLM | 利用可能モデル一覧 | `GET /v1/models` |
| `POST /api/generate` (with `keep_alive=0`) | perception VLM | モデルアンロード | **直接対応なし**：プロセスごとに 1 モデル常駐モデル |

### 1.3 重要な前提

- **brain** の `LLMClient` は `LLM_PROVIDER` で `ollama` / `openai` / `anthropic` を切替えるマルチプロバイダ実装。`openai` 分岐を選べば `/v1/chat/completions` で動く（既存）。
- **stt** は既に OpenAI 互換 API を使っており書き換え不要。
- **knowledge-bridge** は埋め込みが空文字（`EMBEDDING_URL=""`) ならベクトル検索を無効化してフォールバックする実装あり。
- **perception** の VLM は Ollama に組み込みの multimodal を使用。llama.cpp に移行する場合は `--mmproj` でビジョンモデル（LLaVA、MiniCPM-V、Qwen2-VL 等）をロード。
- **モデルホットスワップ**（軽量 VLM ⇄ 重量 VLM、Brain ⇄ Report モデル）は Ollama の `keep_alive` に依存していたが、llama.cpp では原則「1 プロセス＝1 モデル常駐」のため**スワップ概念を別アーキで実現する必要**がある。

---

## 2. 移行先候補比較（ローカルホスティング前提）

### 2.1 LLM 本体

| 候補 | API 互換 | GPU | Tool calling | モデル管理 | 推奨度 | 備考 |
|---|---|---|---|---|---|---|
| **llama.cpp `llama-server`** | OpenAI 互換 + 独自 | CUDA/ROCm/Vulkan/Metal | ◯（Qwen, Mistral 等） | パス指定 | ★★★ | GGUF ネイティブ |
| **vLLM** | OpenAI 互換 | CUDA/ROCm | ◯ | HF cache | ★★ | 同時要求多い時 |
| **SGLang** | OpenAI 互換 | CUDA/ROCm | ◯ | HF cache | ★★ | エージェント・RAG ヘビー時 |
| **LocalAI** | OpenAI 互換 | llama.cpp | ◯ | ギャラリー | ★★★ | **本 PJ の代替候補として最有力**：chat+embed+VLM+TTS を 1 サーバ |
| **Cortex.cpp** | OpenAI 互換 | llama.cpp | ◯ | `cortex pull` | ★★ | Ollama UX クローン、自動 load/unload |
| **mistral.rs** | OpenAI 互換 | CUDA/Metal | ◯ | HF cache | ★ | Rust 単一バイナリ |
| **TGI** | OpenAI 互換 | CUDA/ROCm | ◯ | HF cache | ★ | HF 寄り |
| **MLX-LM** | OpenAI 互換 | Apple Silicon | △ | HF cache | — | macOS 限定 |

### 2.2 埋め込み（knowledge-bridge）

| 候補 | API | GPU | 推奨度 | 備考 |
|---|---|---|---|---|
| **text-embeddings-inference (TEI)** | OpenAI 互換 | CUDA/CPU/Metal | ★★★ | HF 製、本番想定。BGE/Nomic/E5 全部行ける |
| **Infinity (michaelfeil/infinity)** | OpenAI 互換 | CUDA/CPU/MPS | ★★ | Embed + rerank + classifier + CLIP |
| **llama.cpp `--embeddings`** | OpenAI 互換 | 同上 | ★★ | 単一バイナリで完結、別プロセスで起動 |
| **LocalAI** | OpenAI 互換 | llama.cpp | ★★ | 1 サーバで chat+embed |
| **fastembed** | ライブラリ（HTTP なし） | CPU/ONNX | — | サイドカー化が必要 |

### 2.3 VLM（perception）

| 候補 | 形式 | 性能 | 推奨度 | 備考 |
|---|---|---|---|---|
| **llama.cpp `--mmproj`** | GGUF | 中 | ★★★ | LLaVA, MiniCPM-V, Qwen2-VL, SmolVLM, Gemma3 |
| **vLLM multimodal** | HF | 高 | ★★ | スループット重視 |
| **mistral.rs** | HF | 高 | ★★ | LLaVA-Next, Qwen2-VL, Phi-3.5-V |
| **SGLang** | HF | 高 | ★ | LLaVA, Qwen-VL, MiniCPM-V |

### 2.4 採用案

本 PJ は「**chat + embed + VLM が混在し、モデル切替の運用機能（pull / list / unload）を活用している**」点で Ollama に深く依存しているため、**2 案を並列に検討**する：

#### 案 A：llama.cpp + TEI + 個別 VLM サービス（純粋分離型）

- LLM (brain, news, stt) → `llama-server`
- 埋め込み (knowledge) → `text-embeddings-inference`
- VLM (perception) → `llama-server --mmproj` 別プロセス
- 各サービスは 1 モデル常駐。スワップは **行わない**（VRAM が許す範囲で並列、足りなければ専用 GPU 割当）

利点：各コンポーネントが独立、障害分離、性能最良
欠点：Ollama にあった「pull → 即実行」の柔軟さが消える

#### 案 B：LocalAI 単体（互換性最優先）

- LocalAI を Ollama の置換として 1 つ立て、chat / embed / VLM をすべて REST で受ける
- モデルギャラリー機能で `pull` 相当が利用可能
- Ollama API（`/api/tags`、`/api/pull` 等）は依然として直接互換ではないため `chat_server.py` 等は OpenAI 互換 (`/v1/models`) に書き換え必要

利点：単一サーバ、Ollama に近い運用感
欠点：内部は llama.cpp なので性能は Ollama と同等止まり

**推奨**：将来的なスケール余地を残すため**案 A をベース**、ただし pull / list 系の管理 UI が運用上重要な場合は LocalAI を併用する。

---

## 3. ファイル別 移行手順

### 3.1 brain — `services/brain/src/llm_client.py`

既に `LLM_PROVIDER=openai` 分岐がある。**`.env` の `LLM_PROVIDER` を `openai` に固定**するだけで OpenAI 互換経路に切替可能。`LLM_API_URL` を llama.cpp の `/v1` に向ける。

```bash
LLM_PROVIDER=openai
LLM_API_URL=http://llm:8080/v1
LLM_MODEL=qwen2.5-14b-instruct
```

`_chat_ollama` メソッド（42–98 行）の存在は維持してよいが、デフォルト経路から外す。

### 3.2 news-bridge — `news_summarizer.py` / `urgency.py`

**現在**：独自 `OllamaClient` クラスで `POST /api/chat` を直接叩く。

**変更**：OpenAI 互換クライアントに置換。最小修正で済ませるなら以下：

```python
# OllamaClient の chat メソッドを下記の形に書き換え（または OpenAI SDK 採用）
async def chat(self, messages, *, temperature=0.3, max_tokens=2048):
    payload = {
        "model": self.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    async with self._session.post(
        f"{self.base_url}/v1/chat/completions",
        json=payload,
        timeout=aiohttp.ClientTimeout(total=120),
    ) as resp:
        data = await resp.json()
    return data["choices"][0]["message"]["content"]

async def is_available(self):
    try:
        async with self._session.get(f"{self.base_url}/v1/models", timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False
```

`OLLAMA_URL` 系環境変数は `LLM_API_URL` への統合を推奨：

```diff
- OLLAMA_URL=http://ollama:11434
- OLLAMA_MODEL=qwen3.5
+ NEWS_LLM_API_URL=http://llm:8080
+ NEWS_LLM_MODEL=qwen2.5-7b-instruct
```

### 3.3 knowledge-bridge — `embedding.py`

**現在**：`POST /api/embed` で `nomic-embed-text` を呼出。

**変更**：埋め込み専用サーバ（TEI）または llama.cpp `--embeddings` を別プロセスで立ち上げ、`POST /v1/embeddings` を使用。

```python
async def embed(self, text: str | list[str]) -> list[list[float]]:
    payload = {"model": self.model, "input": text if isinstance(text, list) else [text]}
    async with self._session.post(
        f"{self.base_url}/v1/embeddings",
        headers={"Authorization": f"Bearer {self.api_key or 'EMPTY'}"},
        json=payload,
    ) as resp:
        data = await resp.json()
    return [item["embedding"] for item in data["data"]]
```

環境変数：

```diff
- EMBEDDING_URL=http://ollama:11434
- EMBEDDING_MODEL=nomic-embed-text
+ EMBEDDING_URL=http://embed:8080
+ EMBEDDING_MODEL=nomic-embed-text-v1.5
```

### 3.4 perception — `vlm_analyzer.py`

**最も影響範囲大**。書き換え観点：

1. **`/api/chat` → `/v1/chat/completions`**：image_url コンテンツに base64 を入れる OpenAI Vision フォーマットへ
2. **`/api/tags` → `/v1/models`**：レスポンス JSON 構造が異なる
3. **`/api/generate` (keep_alive=0) → 廃止**：llama.cpp はモデル常駐。アンロード相当は「該当 VLM コンテナを停止/再起動」または「軽/重 VLM を別ポートで両方常駐」で対処

軽/重モデルスワップを継続したい場合の選択肢：
- **(a) 別ポート常駐型**：`vlm-light` (port 8081) と `vlm-heavy` (port 8082) を両方起動。VRAM が許せば最も単純
- **(b) コンテナ swap 型**：Docker API で `docker stop vlm-light && docker start vlm-heavy` を `vlm_analyzer` から呼出。MQTT モデル swap 通知は維持
- **(c) LocalAI 採用**：LocalAI のモデル auto load/unload を利用

推奨は **(a)**（VRAM 8 GB 以上あれば moondream + minicpm-v 同時常駐可能）。

### 3.5 stt — `query_cleaner.py`

既に OpenAI 互換 (`/v1/chat/completions`) を使用。**変更不要**。`STT_LLM_API_URL` (= `LLM_API_URL`) を llama.cpp に向けるだけ。

### 3.6 `infra/docker-compose.yml`

`ollama` / `ollama-pull` サービスを以下で置換：

```yaml
llm:
  image: ghcr.io/ggml-org/llama.cpp:server-cuda
  container_name: hems-llm
  restart: unless-stopped
  profiles: ["llm"]
  ports:
    - "${HEMS_PORT_LLM:-8080}:8080"
  volumes:
    - ./models:/models:ro
  command: >
    --model /models/Qwen2.5-14B-Instruct-Q4_K_M.gguf
    --host 0.0.0.0 --port 8080 --n-gpu-layers 99
    --ctx-size 32768 --parallel 4 --cont-batching --flash-attn on
  healthcheck:
    test: ["CMD-SHELL", "curl -fsS http://localhost:8080/health || exit 1"]
    interval: 30s
    timeout: 10s
  deploy: { resources: { reservations: { devices: [{driver: nvidia, count: 1, capabilities: [gpu]}] } } }
  networks: [hems-net]

embed:
  image: ghcr.io/huggingface/text-embeddings-inference:1.5
  container_name: hems-embed
  profiles: ["llm"]
  ports: ["${HEMS_PORT_EMBED:-8090}:80"]
  volumes: ["./models/embed:/data"]
  command: ["--model-id", "nomic-ai/nomic-embed-text-v1.5", "--port", "80"]
  networks: [hems-net]

vlm-light:
  image: ghcr.io/ggml-org/llama.cpp:server-cuda
  container_name: hems-vlm-light
  profiles: ["llm", "vlm"]
  ports: ["${HEMS_PORT_VLM_LIGHT:-8081}:8080"]
  volumes: ["./models:/models:ro"]
  command: >
    --model /models/MiniCPM-V-2_6-Q4_K_M.gguf
    --mmproj /models/mmproj-MiniCPM-V-2_6-f16.gguf
    --host 0.0.0.0 --port 8080 --n-gpu-layers 99
  networks: [hems-net]
```

（必要に応じ `vlm-heavy` も同様に追加）

`gpu_setup.py` は ROCm/CUDA で llama.cpp / TEI のイメージタグを差し替える形に書き換える。

### 3.7 `env.example`

```diff
- LLM_PROVIDER=openai
- LLM_API_URL=http://ollama:11434/v1
- LLM_MODEL=mistral-small:24b
+ LLM_PROVIDER=openai
+ LLM_API_URL=http://llm:8080/v1
+ LLM_MODEL=qwen2.5-14b-instruct

- VLM_OLLAMA_URL=http://ollama:11434
- VLM_LIGHT_MODEL=moondream
- VLM_HEAVY_MODEL=minicpm-v
+ VLM_LIGHT_API_URL=http://vlm-light:8080/v1
+ VLM_HEAVY_API_URL=http://vlm-heavy:8080/v1
+ VLM_LIGHT_MODEL=minicpm-v
+ VLM_HEAVY_MODEL=qwen2-vl-7b

- OLLAMA_URL=http://ollama:11434
- OLLAMA_MODEL=qwen3.5
+ NEWS_LLM_API_URL=http://llm:8080
+ NEWS_LLM_MODEL=qwen2.5-7b-instruct

- EMBEDDING_URL=http://ollama:11434
- EMBEDDING_MODEL=nomic-embed-text
+ EMBEDDING_URL=http://embed:80
+ EMBEDDING_MODEL=nomic-embed-text-v1.5
```

### 3.8 ドキュメント更新

- `CLAUDE.md` (21–31, 80, 114, 376–410, 452–494, 525–530)：起動コマンド、ポート表、各サービス節を `--profile llm` ベースに書換
- `README.md` (45–51)：サービス構成図とセットアップ手順
- `docs/pitch-*`：Ollama 言及を llama.cpp に更新（プロモ用は急ぎでなくてよい）

---

## 4. 移行リスクと検証項目

| リスク | 対応 |
|---|---|
| Tool calling の応答差 | brain の tool 呼出で Qwen2.5 / Mistral 系のチャットテンプレートを `--chat-template` で指定要 |
| 同時要求多発 | `--parallel N`、もしくは負荷高なら vLLM 切替 |
| VLM スワップ機構喪失 | 軽/重両方常駐 or コンテナ swap で代替。MQTT 通知は維持 |
| 埋め込み次元差 | `nomic-embed-text` v1 と v1.5 で次元が同じか確認、ベクトルストアの再構築が要 |
| ROCm 環境 | `ghcr.io/ggml-org/llama.cpp:server-rocm` を `gpu_setup.py` で出力 |
| keep-alive | プロセス常駐に変わるため、複数モデルロードは VRAM 計画を更新 |
| `chat_server.py` 等の Ollama 管理 API（pull/list/delete） | 該当機能が brain にあれば LocalAI 採用または UI から削除 |

検証：

```bash
docker compose -f infra/docker-compose.yml --profile llm up -d
curl http://llm:8080/health
curl http://embed:80/health
pytest tests/
```

---

## 5. 移行ステップ（推奨順序）

1. `models/` 配下に GGUF（LLM、VLM、mmproj）と TEI 用 embedding model を配置
2. `docker-compose.yml` に `llm` / `embed` / `vlm-light` 追記。旧 `ollama` は当面残置
3. brain の `.env` で `LLM_PROVIDER=openai`、`LLM_API_URL` を llama.cpp に切替えて回帰
4. stt → 動作確認のみ（既に OpenAI 互換）
5. news-bridge の `OllamaClient` を OpenAI 互換に書換（PR）
6. knowledge-bridge の `embedding.py` を `/v1/embeddings` に書換（PR、ベクトルストア再構築要）
7. perception VLM スワップを軽/重両常駐構成に書換（PR）
8. ドキュメント、`gpu_setup.py` 更新
9. 旧 `ollama` / `ollama-pull` サービス、`ollama_models` ボリューム削除
