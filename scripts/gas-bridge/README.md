# HEMS GAS Bridge — Google Apps Script デプロイ手順

## 概要

Google Apps Script (GAS) をWeb Appとしてデプロイし、HEMS gas-bridgeサービスからHTTPポーリングでGoogle Calendar / Tasks / Gmail / Sheets / Driveのデータを取得します。

## デプロイ手順

### 1. GASプロジェクト作成

1. [Google Apps Script](https://script.google.com/) にアクセス
2. 「新しいプロジェクト」を作成
3. プロジェクト名を「HEMS Bridge」に変更
4. `Code.gs` の内容を `scripts/gas-bridge/Code.gs` からコピー＆ペースト

### 2. Google Tasks API を有効化

1. GASエディタで「サービス」（＋アイコン）をクリック
2. 「Tasks API」を検索して追加
3. 「追加」をクリック

### 3. API キーの設定

1. GASエディタで「プロジェクトの設定」（歯車アイコン）をクリック
2. 「スクリプト プロパティ」セクションで「プロパティを追加」
3. プロパティ名: `API_KEY`、値: 任意の秘密文字列（例: `openssl rand -hex 32` で生成）

### 4. Web App としてデプロイ

1. 「デプロイ」→「新しいデプロイ」
2. 種類: 「ウェブアプリ」
3. 設定:
   - 説明: `HEMS Bridge v1`
   - 次のユーザーとして実行: `自分`
   - アクセスできるユーザー: `全員`（API_KEYで認証するため）
4. 「デプロイ」をクリック
5. 表示されたURLをコピー（`https://script.google.com/macros/s/xxx/exec`）

### 5. HEMS 設定

`.env` に以下を追加:

```bash
GAS_WEBAPP_URL=https://script.google.com/macros/s/xxx/exec
GAS_API_KEY=your-api-key-here
GAS_BRIDGE_URL=http://gas-bridge:8000
```

起動:

```bash
cd infra && docker compose --profile gas up -d --build
```

## 動作確認

```bash
# GAS Web App直接テスト
curl "https://script.google.com/macros/s/xxx/exec?key=YOUR_KEY&action=health"

# gas-bridge経由
curl http://localhost:8015/health
curl http://localhost:8015/api/gas/calendar
curl http://localhost:8015/api/gas/tasks
curl http://localhost:8015/api/gas/gmail
```

## 利用可能なアクション

| action | 説明 | 追加パラメータ |
|--------|------|---------------|
| `health` | ヘルスチェック | — |
| `calendar_today` | 今日のイベント | — |
| `calendar_upcoming` | 次N時間のイベント | `hours=24` |
| `calendar_free_slots` | 空き時間スロット | `hours=12` |
| `tasks_list` | 全タスクリスト | — |
| `tasks_due_today` | 今日期限+期限切れ | — |
| `gmail_summary` | ラベル別未読数 | — |
| `gmail_recent` | 最近のスレッド | `count=10` |
| `sheets_read` | シート読み取り | `id=SPREADSHEET_ID&sheet=SHEET_NAME&range=A1:D10` |
| `drive_recent` | 最近変更ファイル | `count=20` |

## GAS クォータ

- 日次クォータ: ~20,000 calls/day (consumer)
- デフォルトポーリング設定: ~1,100 calls/day
- カスタムポーリング間隔は `.env` で調整可能

## トラブルシューティング

### "unauthorized" エラー
→ `GAS_API_KEY` と GAS Script Property の `API_KEY` が一致しているか確認

### "Tasks is not defined" エラー
→ GASエディタで Tasks API サービスを追加しているか確認

### "You do not have permission" エラー
→ 初回デプロイ時に Google 認証ポップアップを承認しているか確認

### データが古い
→ GAS Web Appは新しいバージョンをデプロイするまでキャッシュされる。コード変更後は「デプロイ」→「デプロイを管理」→「新しいバージョン」で再デプロイ
