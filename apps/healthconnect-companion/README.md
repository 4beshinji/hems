# Health Connect Companion — Biometric Data Synchronizer

Kotlin / Jetpack Compose で実装した Android アプリ。Android の **Health Connect** フレームワークから心拍、歩数、睡眠などのバイオメトリクスデータを読み取り、HEMS の `biometric-bridge` へ webhook 経由で送信する。

## リポジトリ内での位置づけ

このプロジェクトは **Docker 化対象外**です。以下の理由から、HEMS の Docker Compose 構成には含まれません:

- Android APK として独立ビルド・配布(Google Play Store または Android Studio の apk 出力)
- Health Connect API は実デバイスでのみ利用可能(エミュレータでは機能しない)
- Docker 上での実行意義が薄い(本来のデプロイ形態は実デバイス)

詳細は [`docs/IMPLEMENTATION_MAP.md`](../../docs/IMPLEMENTATION_MAP.md) §1.2 を参照。

## 役割

HEMS のバイオメトリクス統合における **データ収集エージェント**:

1. **Health Connect 読み取り**: Android 14+ の Health Connect API で心拍 / 歩数 / 睡眠 / 体温 / 血圧などを定期的にポーリング
2. **Webhook Push**: 新規データを検出したら、HEMS `services/biometric-bridge` の webhook エンドポイント(`/devices/heartbeat` など)へ POST
3. **ローカルキャッシュ**: オフライン時のデータロスを防ぐため、同期済みタイムスタンプをローカル保存

詳細は [`services/biometric-bridge/CLAUDE.md`](../../services/biometric-bridge/CLAUDE.md) を参照。

## ビルド方法

### 前提

- Android Studio (2024.1 以降推奨)
- JDK 17 以上
- Android SDK 35 (API level 35)、**Health Connect サポートライブラリ** のインストール

### コマンドラインビルド

```bash
cd apps/healthconnect-companion

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

1. Android Studio で `apps/healthconnect-companion/` を開く
2. 実機を接続(Health Connect は API 35+ の実デバイスに限定)
3. メニュー: **Run → Run 'app'**

## 通信経路

- **HEMS Biometric Bridge Webhook**: `${BIOMETRIC_BRIDGE_URL}/devices/heartbeat`
- **認証**: HMAC-SHA256 署名 (request header: `X-Signature`)

環境変数の詳細は `env.example` を参照。

## 必須 Android 権限

```xml
<!-- AndroidManifest.xml -->
<uses-permission android:name="android.permission.HEALTH" />
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
```

## トラブルシューティング

- **Health Connect が見つからない**: Android 14 以上のデバイス、または "Health Connect" アプリのインストール(Google Play ストア)を確認
- **Webhook 接続失敗**: BIOMETRIC_BRIDGE_URL の設定、ファイアウォール、HMAC 署名生成ロジックを確認
- **データが同期されない**: アプリに Health データ読み取り権限が許可されているか確認(`Settings → Health Connect → Permissions`)
