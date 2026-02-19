# Local LLM Engine (vLLM)

このディレクトリは、SOMSシステムから独立して動作するローカルLLMエンジンの構成を含みます。
AMD Radeon GPU (ROCm) 環境向けに最適化されています。

## 前提条件

*   **OS**: Linux (推奨)
*   **GPU**: AMD Radeon (ROCm対応)
*   **Drivers**: ROCmドライバがインストールされ、`/dev/kfd` および `/dev/dri` が利用可能であること。
*   **Docker**: Docker および Docker Compose

## セットアップ手順

1.  **Hugging Face Tokenの設定**:
    `.env` ファイルを作成し、`HF_TOKEN` を設定してください（モデルダウンロード用）。
    ```bash
    echo "HF_TOKEN=your_hugging_face_token" > .env
    ```

2.  **起動**:
    ```bash
    docker-compose up -d
    ```

3.  **動作確認**:
    ```bash
    curl http://localhost:8001/v1/models
    ```

## メインシステムとの連携

メインシステム（Brainサービス）からこのLLMを利用する場合は、Brainサービスの環境変数 `LLM_API_URL` を設定してください。

*   **同一マシン内の場合 (Host)**: `http://localhost:8001/v1`
*   **同一マシン内の場合 (Docker Network)**: `http://llm-engine:8000/v1`
*   **別マシンの場合**: `http://<LLM-Machine-IP>:8000/v1`

## 注意事項

*   初回起動時は数GB〜数十GBのモデルダウンロードが発生します。
*   GPU VRAMの使用量に注意してください。
