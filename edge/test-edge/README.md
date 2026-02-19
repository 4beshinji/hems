# Test Edge Device Setup

このディレクトリには、本番環境とは独立したテスト用エッジデバイスのファームウェアとドキュメントが含まれています。

## ハードウェア構成

### カメラノード
- **ボード**: Freenove ESP32 WROVER v3.0
- **カメラ**: OV2640 (オンボード)
- **役割**: RTSPストリーム配信、物体検知用画像キャプチャ

### センサーノード
- **ボード**: Seeed Studio XIAO ESP32-S3
- **センサー**: BME680 (温度・湿度・気圧・ガス)
- **役割**: 環境モニタリング、MQTTテレメトリ送信

## ディレクトリ構造

```
test-edge/
├── camera-node/       # Freenove ESP32 WROVER v3.0 ファームウェア
├── sensor-node/       # XIAO ESP32-S3 + BME680 ファームウェア
├── docs/              # セットアップ・組み立てガイド
└── README.md          # このファイル
```

## クイックスタート

詳細は `docs/` 配下のドキュメントを参照してください：

1. [開発環境セットアップ](docs/01_development_setup.md)
2. [ハードウェア仕様・配線図](docs/02_hardware_specs.md)
3. [ファームウェアビルド・書き込み](docs/03_firmware_flashing.md)
4. [テスト手順](docs/04_testing.md)
