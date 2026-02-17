# SOMS デプロイメントガイド (Deployment Guide JA)

## 1. 前提条件

ターゲットマシンに以下がインストールされていることを確認してください。

-   **OS**: Linux (Ubuntu 22.04+ 推奨)
-   **Git**: `sudo apt install git`
-   **Docker Engine**: [インストールガイド](https://docs.docker.com/engine/install/ubuntu/)
-   **Docker Compose Plugin**: `sudo apt install docker-compose-plugin`
    -   `docker compose version` で動作を確認してください。
-   **AMD Drivers (ROCm)**: ローカルLLMを使用する場合にのみ必要です。[インストールガイド](https://rocm.docs.amd.com/en/latest/deploy/linux/quick_start.html)。
    -   `rocminfo` または `clinfo` コマンドで動作を確認してください。

## 2. クローンとセットアップ

1.  **リポジトリの複製**:
    ```bash
    git clone <repository_url> Office_as_AI_ToyBox
    cd Office_as_AI_ToyBox
    ```

2.  **環境設定**:
    ```bash
    cp env.example .env
    # 必要に応じて .env を編集 (LLM接続先、PostgreSQL認証情報等)
    nano .env
    ```

3.  **初期化 (ボリュームとネットワーク作成)**:
    ```bash
    chmod +x infra/scripts/setup_dev.sh
    ./infra/scripts/setup_dev.sh
    ```

## 3. 利用シナリオの実行

### シナリオ A: 完全シミュレーション (ハードウェア不要・GPU不要)

ロジックやネットワークフローの検証に最適です。Mock LLM + 仮想エッジデバイスで動作します。

```bash
./infra/scripts/start_virtual_edge.sh
```

起動サービス: Brain, Dashboard (Backend+Frontend), Mock LLM, Voice Service, VOICEVOX, Wallet, PostgreSQL, Mosquitto, Virtual Edge, Virtual Camera

-   **検証方法**: `python3 infra/scripts/e2e_full_test.py` でE2Eテスト (7シナリオ) を実行

### シナリオ B: 実機本番環境 (AMD ROCm GPU + エッジデバイス)

1.  **`.env` の編集**:
    -   `LLM_API_URL=http://ollama:11434/v1` (Docker内部通信)
    -   `LLM_MODEL=qwen2.5:14b`
    -   `RTSP_URL` を実際のカメラのIPアドレスに設定
    -   PostgreSQL認証情報を本番用に変更

2.  **GPU デバイスの確認**:
    -   `docker-compose.yml` 内の `ollama` / `perception` サービスの `devices` マッピングを確認:
      ```yaml
      devices:
        - /dev/kfd:/dev/kfd
        - /dev/dri/card1:/dev/dri/card1        # dGPU
        - /dev/dri/renderD128:/dev/dri/renderD128
      ```
    -   **重要**: `/dev/dri` 全体を渡すとiGPUリセット→GNOMEクラッシュの原因になります。dGPU のみを指定してください。

3.  **Ollama モデルの準備**:
    ```bash
    # Ollamaコンテナ起動後にモデルをダウンロード
    docker compose -f infra/docker-compose.yml up -d ollama
    docker exec -it soms-ollama ollama pull qwen2.5:14b
    ```

4.  **全サービスの起動**:
    ```bash
    docker compose -f infra/docker-compose.yml up -d --build
    ```

### シナリオ C: ホストOllama使用 (Docker外でLLM実行)

Ollama をホストマシンで直接実行し、Docker内のサービスから接続する場合:

```bash
# ホスト側でOllamaを起動
ollama serve  # 0.0.0.0:11434 でリスン

# .env を編集
LLM_API_URL=http://host.docker.internal:11434/v1
LLM_MODEL=qwen2.5:14b
```

`docker-compose.yml` の `brain` / `voice-service` に `extra_hosts: host.docker.internal:host-gateway` が設定済みです。

## 4. サービスの確認

```bash
# 全コンテナの状態確認
docker compose -f infra/docker-compose.yml ps

# ログ確認
docker logs -f soms-brain        # Brain の認知ループ
docker logs -f soms-voice        # 音声合成
docker logs -f soms-backend      # Dashboard API

# ダッシュボード
# ブラウザで http://localhost にアクセス

# API ドキュメント (Swagger UI)
# Backend:  http://localhost:8000/docs
# Wallet:   http://localhost:8003/docs
# Voice:    http://localhost:8002/docs
```

## 5. サービス一覧

| サービス | ポート | コンテナ名 | 用途 |
|---------|--------|-----------|------|
| Dashboard Frontend | 80 | soms-frontend | nginx (SPA + リバースプロキシ) |
| Dashboard Backend | 8000 | soms-backend | タスクCRUD API |
| Mock LLM | 8001 | soms-mock-llm | テスト用LLMシミュレータ |
| Voice Service | 8002 | soms-voice | 音声合成 + LLMテキスト生成 |
| Wallet Service | 8003 | soms-wallet | クレジット経済 (複式簿記) |
| PostgreSQL | 5432 | soms-postgres | Dashboard/Wallet 共有DB |
| VOICEVOX | 50021 | soms-voicevox | 日本語音声合成エンジン |
| Ollama | 11434 | soms-ollama | LLM推論 (ROCm) |
| MQTT | 1883 | soms-mqtt | メッセージブローカー |
| Perception | host network | soms-perception | YOLOv11 画像認識 |

## 6. トラブルシューティング

-   **MQTT Connection Refused**: `docker ps` で `soms-mqtt` が起動しているか確認。
-   **LLM Out of Memory**: `rocm-smi` でVRAM使用量を確認。より小さいモデル (`qwen2.5:7b`) に切り替えるか、量子化レベルを下げてください。
-   **Permission Denied**: ユーザーが `docker` および `video`/`render` グループに追加されているか確認: `sudo usermod -aG docker,video,render $USER`
-   **iGPU クラッシュ**: `/dev/dri` 全体ではなく dGPU デバイスのみを `devices:` に指定してください。
-   **PostgreSQL 接続エラー**: `docker logs soms-postgres` でログを確認。`.env` の `POSTGRES_USER`/`POSTGRES_PASSWORD` がdocker-compose.ymlの設定と一致しているか確認。
