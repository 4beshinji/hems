# 01. 開発環境セットアップ

このドキュメントでは、テストエッジデバイスの開発に必要な環境構築手順を説明します。

## 1. 前提条件

- **OS**: Linux (Ubuntu 20.04以降推奨) / macOS / Windows 10/11
- **Python**: 3.8以上
- **インターネット接続**: 依存パッケージのダウンロード用

---

## 2. 開発環境の選択

以下の2つの選択肢があります。**PlatformIOを推奨**します。

### オプションA: PlatformIO (推奨)

**利点:**
- プロジェクト管理が容易
- 依存関係の自動解決
- 複数のボードを簡単に切り替え可能
- CLIとVSCode拡張の両方が利用可能

### オプションB: Arduino IDE

**利点:**
- シンプルなGUI
- 初心者向け

---

## 3. PlatformIOのインストール

### 3.1 方法1: VSCode拡張 (推奨)

1. **VSCodeのインストール**
   ```bash
   # Linux (Ubuntu/Debian)
   sudo snap install code --classic
   
   # macOS
   brew install --cask visual-studio-code
   ```

2. **PlatformIO IDE拡張のインストール**
   - VSCodeを起動
   - 拡張機能タブ (Ctrl+Shift+X) を開く
   - "PlatformIO IDE" を検索してインストール
   - VSCodeを再起動

### 3.2 方法2: CLI版

```bash
# Python pipを使用
pip install platformio

# インストール確認
pio --version
```

---

## 4. Arduino IDEのインストール (オプションB選択時)

### 4.1 Arduino IDE 2.xのインストール

```bash
# Linux
wget https://downloads.arduino.cc/arduino-ide/arduino-ide_latest_Linux_64bit.zip
unzip arduino-ide_latest_Linux_64bit.zip
sudo mv arduino-ide_* /opt/arduino-ide
sudo ln -s /opt/arduino-ide/arduino-ide /usr/local/bin/arduino-ide

# macOS
brew install --cask arduino-ide
```

### 4.2 ESP32ボードサポートの追加

1. Arduino IDEを起動
2. **ファイル → 環境設定**
3. **追加のボードマネージャのURL** に以下を追加：
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
4. **ツール → ボード → ボードマネージャ**
5. "esp32" で検索し、**ESP32 by Espressif Systems** をインストール

### 4.3 必要なライブラリのインストール

**ツール → ライブラリを管理** から以下をインストール：

| ライブラリ名 | 用途 |
| :--- | :--- |
| `PubSubClient` | MQTT通信 |
| `ArduinoJson` | JSON処理 |
| `Adafruit BME680 Library` | BME680センサー (Sensor Node用) |
| `Adafruit Unified Sensor` | センサー抽象化レイヤー |

---

## 5. USBドライバのインストール

### 5.1 Linux

ESP32デバイスへのアクセス権限を付与：

```bash
# ユーザーをdialoutグループに追加
sudo usermod -a -G dialout $USER

# 再ログインが必要 (またはシステム再起動)
# 確認
groups
```

**udevルールの設定 (オプション):**

```bash
# ファイル作成
sudo nano /etc/udev/rules.d/99-platformio-udev.rules

# 以下の内容を追加
# ESP32
SUBSYSTEMS=="usb", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", MODE:="0666"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", MODE:="0666"

# ルール再読み込み
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### 5.2 macOS

通常はドライバ不要ですが、CH340チップ搭載ボードの場合：

```bash
# CH340ドライバのインストール
brew install --cask wch-ch34x-usb-serial-driver
```

### 5.3 Windows

- **CP210x**: [Silicon Labs公式サイト](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers)
- **CH340**: [WCH公式サイト](http://www.wch-ic.com/downloads/CH341SER_EXE.html)

---

## 6. 接続テスト

### 6.1 デバイスの検出

```bash
# Linux/macOS
ls /dev/tty* | grep -E "USB|ACM"

# 期待される出力例:
# /dev/ttyUSB0  (Freenove ESP32 WROVER)
# /dev/ttyUSB1  (XIAO ESP32-S3)
```

### 6.2 PlatformIOでの接続確認

```bash
# デバイス一覧表示
pio device list

# 期待される出力例:
# /dev/ttyUSB0
# ----------
# Hardware ID: USB VID:PID=10C4:EA60 SER=01234567
# Description: CP2102 USB to UART Bridge Controller
```

---

## 7. プロジェクトの初期化 (PlatformIO)

```bash
cd /home/sin/code/gemini/bigbrother/edge/test-edge

# Camera Node
cd camera-node
pio project init --board esp32dev

# Sensor Node
cd ../sensor-node
pio project init --board seeed_xiao_esp32s3
```

---

## 8. トラブルシューティング

### デバイスが認識されない

1. **ケーブル確認**: データ転送対応のUSBケーブルを使用
2. **ポート権限**: `sudo chmod 666 /dev/ttyUSB0` (一時的)
3. **ドライバ再インストール**

### アップロード失敗

1. **ブートモード**: ボード上の"BOOT"ボタンを押しながらリセット
2. **ボーレート変更**: `platformio.ini` で `upload_speed = 115200` に設定
3. **別のUSBポート試行**

---

## 9. 次のステップ

開発環境が整ったら、[02_hardware_specs.md](02_hardware_specs.md) でハードウェア仕様と配線を確認してください。
