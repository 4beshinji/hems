# SOMS アクセスガイド (Access Guide)

このドキュメントは、SOMS（Smart Office Management System）へのアクセス方法をまとめたものです。

## サーバー情報

**サーバーIPアドレス**: `192.168.128.161`

## サービスエンドポイント一覧

### 1. ダッシュボード（フロントエンド）
- **URL**: `http://192.168.128.161` または `http://192.168.128.161:80`
- **説明**: Webベースの管理画面
- **用途**: システム全体の監視、タスク管理、カメラ映像表示

### 2. バックエンドAPI
- **URL**: `http://192.168.128.161:8000`
- **API仕様**: `http://192.168.128.161:8000/docs` (FastAPI Swagger UI)
- **説明**: REST API + WebSocket
- **用途**: システムとの統合、データ取得

### 3. Ollama（ローカルLLM）
- **URL**: `http://192.168.128.161:11434`
- **API**: `http://192.168.128.161:11434/v1/chat/completions`
- **説明**: OpenAI互換APIを持つローカルLLMエンジン
- **用途**: AI推論、チャット機能

### 4. 音声サービス
- **URL**: `http://192.168.128.161:8002`
- **説明**: Text-to-Speech サービス
- **用途**: テキストから音声生成

### 5. Voicevox Engine
- **URL**: `http://192.168.128.161:50021`
- **説明**: 音声合成エンジン
- **用途**: 音声サービスのバックエンド

### 6. MQTT Broker
- **URL**: `mqtt://192.168.128.161:1883`
- **プロトコル**: MQTT v3.1.1
- **説明**: メッセージングブローカー
- **用途**: IoTデバイス、センサーとの通信

## ローカルアクセス

サーバー自身からアクセスする場合は、`localhost`を使用できます：

- ダッシュボード: `http://localhost`
- バックエンドAPI: `http://localhost:8000`
- Ollama: `http://localhost:11434`

## ファイアウォール設定

外部からアクセスできない場合、以下のポートを開放してください：

```bash
sudo ufw allow 80/tcp      # Dashboard
sudo ufw allow 8000/tcp    # Backend API
sudo ufw allow 11434/tcp   # Ollama LLM
sudo ufw allow 1883/tcp    # MQTT
```

## セキュリティに関する注意

- 現在の設定では、すべてのサービスがHTTP（非暗号化）です
- 本番環境では以下を推奨します：
  - HTTPS/TLS の設定
  - 認証・認可機構の実装
  - ファイアウォールによるアクセス制限
  - VPN経由でのアクセス

## ネットワーク外からのアクセス

インターネットからアクセスする場合は、ルーターで以下の設定が必要です：

1. **ポートフォワーディング**を設定
   - 外部ポート → `192.168.128.161:[ポート番号]`
2. **動的DNS**の設定（IPアドレスが変動する場合）
3. **HTTPSリバースプロキシ**の導入を推奨（例: Nginx, Caddy）

## トラブルシューティング

### サービスに接続できない

1. サービスが起動しているか確認：
   ```bash
   cd /home/nyantangle/code/Office_as_AI_ToyBox
   docker compose -f infra/docker-compose.yml ps
   ```

2. ファイアウォールの状態を確認：
   ```bash
   sudo ufw status
   ```

3. サーバーのIPアドレスを確認：
   ```bash
   hostname -I
   ```

### サービスを再起動する

```bash
cd /home/nyantangle/code/Office_as_AI_ToyBox
docker compose -f infra/docker-compose.yml restart
```

## 更新履歴

- 2026-02-11: 初版作成
