# HEMS Mobile Companion — Android

Kotlin / Jetpack Compose で実装した Android コンパニオンアプリ。HEMS 本体(backend + brain)と REST API / MQTT を経由して通信し、モバイルデバイスからの音声入力、在宅/外出状態の報告、購買リスト・タスク管理を担当する。

## リポジトリ内での位置づけ

このプロジェクトは **Docker 化対象外**です。以下の理由から、HEMS の Docker Compose 構成には含まれません:

- Android APK として独立ビルド・配布(Google Play Store または Android Studio の apk 出力)
- デバイス固有のハードウェア(GPS・マイク・加速度計)へのアクセスが必要
- Docker 上での実行意義が薄い(本来のデプロイ形態は実デバイス)

詳細は [`docs/IMPLEMENTATION_MAP.md`](../../docs/IMPLEMENTATION_MAP.md) §1.2 を参照。

## ビルド方法

### 前提

- Android Studio (2024.1 以降推奨)
- JDK 17 以上
- Android SDK 35 (API level 35) のインストール

### コマンドラインビルド

```bash
cd services/mobile-android

# Debug APK のビルド
./gradlew assembleDebug
# 出力: app/build/outputs/apk/debug/app-debug.apk

# Release APK のビルド (keystore が必要)
./gradlew assembleRelease -Pandroid.injected.signing.store.file=path/to/keystore \
  -Pandroid.injected.signing.store.password=store_pw \
  -Pandroid.injected.signing.key.alias=alias \
  -Pandroid.injected.signing.key.password=key_pw
# 出力: app/build/outputs/apk/release/app-release.apk
```

### Android Studio での実行

1. Android Studio で `services/mobile-android/` を開く
2. 実機またはエミュレータを接続 / 起動
3. メニュー: **Run → Run 'app'**

## 通信経路

- **Backend REST**: `${HEMS_BACKEND_URL}/mobile/*` エンドポイント(タスク / 購買リスト / デバイス制御)
- **Brain Chat**: `${HEMS_BACKEND_URL}/chat/mobile` エンドポイント(自然言語リクエスト)
- **MQTT**: 在宅/外出状態、バッテリー残量などを `office/mobile/{device_id}/*` へ publish

認証は `BACKEND_API_KEY` 環境変数で設定される shared key を使用。詳細は [`services/backend/CLAUDE.md`](../backend/CLAUDE.md) を参照。

## 環境変数

`.env` ファイル (または GitHub Actions secrets) で以下を設定:

```env
# Backend API
HEMS_BACKEND_URL=http://192.168.1.100:8010

# 認証
BACKEND_API_KEY=<shared_key>

# MQTT
MQTT_BROKER_HOST=192.168.1.100
MQTT_BROKER_PORT=1893

# オプション
MQTT_USERNAME=<if_required>
MQTT_PASSWORD=<if_required>
```

## トラブルシューティング

- **APK インストール失敗**: `adb install-multiple app-debug.apk` を試す(分割 APK 対応)
- **MQTT 接続できない**: ファイアウォール確認、MQTT broker の TLS/auth 設定確認
- **Backend API 401**: BACKEND_API_KEY 設定確認
