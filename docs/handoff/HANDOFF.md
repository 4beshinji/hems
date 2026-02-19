# 引き継ぎドキュメント — SOMS 全作業状態

**更新日**: 2026-02-13
**ブランチ**: main
**最新コミット**: `5a8bdfc` (SensorSwarm + WorldModel + Wallet + E2E テスト)
**状態**: SensorSwarm 実装完了・Docker E2E 検証済み、Wallet サービス並行開発中

---

## 1. 今回のセッション作業サマリ

### Session F (今回): SensorSwarm 2階層センサーネットワーク

Hub + Leaf の 2階層アーキテクチャで、低コスト・乾電池駆動の Leaf デバイスを
高機能 Hub (ESP32) が集約し MQTT に橋渡しする仕組みを実装。

#### F-1. バイナリプロトコル基盤 (`edge/lib/swarm/message.py`)

| 項目 | 詳細 |
|------|------|
| フレーム | 5–245 bytes (ESP-NOW 250B制限に収まる) |
| ヘッダ | Magic(0x53) + Version + MsgType + LeafID |
| チェックサム | XOR 全バイト |
| メッセージ型 | SENSOR_REPORT, HEARTBEAT, REGISTER, COMMAND, ACK, WAKE, CONFIG, TIME_SYNC |
| チャンネル型 | 14種 (temperature, humidity, co2, motion, door, battery_mv 等) |
| エンコード | little-endian float (`<f`), MicroPython 互換 (struct モジュールのみ) |

#### F-2. トランスポート層 (4種)

| トランスポート | ファイル | プラットフォーム | 状態 |
|---------------|---------|----------------|------|
| ESP-NOW | `edge/lib/swarm/transport_espnow.py` | ESP32-C3/C6 | 実装済み |
| UART | `edge/lib/swarm/transport_uart.py` | Pi Pico | 実装済み |
| I2C | `edge/lib/swarm/transport_i2c.py` | ATtiny | 実装済み |
| BLE | `edge/lib/swarm/transport_ble.py` | nRF54L15 | スタブ |

#### F-3. ファームウェア

| デバイス | ファイル | 言語 |
|---------|---------|------|
| SwarmHub (ESP32-S3/C6) | `edge/swarm/hub-node/main.py` | MicroPython |
| SwarmLeaf (ESP32-C3/C6) | `edge/swarm/leaf-espnow/main.py` | MicroPython |
| SwarmLeaf (Pi Pico) | `edge/swarm/leaf-uart/main.py` | MicroPython |
| SwarmLeaf (ATtiny I2C) | `edge/swarm/leaf-arduino/leaf-i2c-attiny/src/main.cpp` | C++ |
| SwarmLeaf (nRF54 BLE) | `edge/swarm/leaf-arduino/leaf-ble-nrf/src/main.cpp` | C++ (スタブ) |

#### F-4. 仮想エミュレータ (Docker 統合済み)

- `infra/virtual_edge/src/swarm_transport.py` — インメモリ双方向トランスポート
- `infra/virtual_edge/src/swarm_leaf.py` — 仮想 Leaf (TempHumidity, PIR, Door, Relay)
- `infra/virtual_edge/src/swarm_hub.py` — 仮想 Hub (VirtualDevice 拡張)
- `infra/virtual_edge/src/main.py` — SwarmHub + 3 Leaf 追加

#### F-5. Brain WorldModel 統合

- `motion` チャンネル → `pir_detected` + occupancy fusion → 在室人数推定
- `door` チャンネル → `door_opened`/`door_closed` イベント生成
- device_id = `swarm_hub_01.leaf_env_01` (ドット区切り) → WorldModel 変更最小

#### F-6. Docker 修正

- `.gitignore` に `!edge/lib/` 追加 (従来 `lib/` で無視されていた)
- `docker-compose.edge-mock.yml` に volume mount: `../edge/lib:/edge_lib`
- import path: Docker (`/edge_lib`) + ローカル (relative) の dual path

### E2E 検証結果

| テスト | 結果 |
|--------|------|
| Docker コンテナ起動 | PASS — 3 Leaf 全登録 |
| MQTT データ流通 | PASS — `swarm_hub_01.leaf_*/temperature,motion,door` |
| MCP `get_swarm_status` | PASS — 3 Leaf の状態 (battery, last_seen, capabilities) |
| MCP `leaf_command` | PASS — `read_now` コマンド送信・ACK |
| Brain WorldModel 統合 | PASS — 気温 20.9℃ = sensor_01 + Leaf のフュージョン結果 |
| WorldModel motion → occupancy | PASS — PIR検知 → person_count=1 |
| WorldModel door → event | PASS — door_opened/closed イベント生成 |

---

## 2. コミット履歴 (最新)

```
5a8bdfc add: full E2E integration test — 7 scenarios across brain/voice/dashboard
98c905c add: wallet service — double-entry ledger for credit economy
aabc371 refactor: extract AudioQueue with priority-based sequential playback
c9de557 feat: WorldModel motion/door channel support
ff1a5d2 fix: virtual-edge Docker path resolution for shared edge/lib
b48a458 feat: add SensorSwarm 2-tier sensor network (Hub + Leaf architecture)
15da7d4 add: promotional materials — tech slides, pitch deck, article, image prompts, figma assets
e6291e9 fix: duplicate task prevention and temperature alert visibility
e94cbb0 fix: ImageRequester singleton — accept broker/port args in get_instance
942e4af add: LLM benchmark tool and updated handoff document
```

---

## 3. 未コミット作業 (main ブランチ)

wallet/phase ブランチからの stash pop で main に残っている未コミット変更:

| ファイル | 内容 |
|---------|------|
| `infra/docker-compose.yml` | PostgreSQL + wallet service 追加 |
| `services/dashboard/backend/models.py` | User model 更新 |
| `services/dashboard/backend/schemas.py` | User schema 更新 |
| `services/dashboard/backend/routers/tasks.py` | PostgreSQL 関数対応 |
| `services/dashboard/frontend/src/App.tsx` | Wallet UI 統合 (conflict あり) |
| `services/dashboard/frontend/src/components/TaskCard.tsx` | wallet 連携 |
| `services/wallet/` | wallet サービス全体 |
| `services/dashboard/frontend/src/components/UserSelector.tsx` | NEW |
| `services/dashboard/frontend/src/components/WalletBadge.tsx` | NEW |
| `services/dashboard/frontend/src/components/WalletPanel.tsx` | NEW |

**注意**: `App.tsx` に merge conflict が残っている (`UU` ステータス)。解決が必要。

---

## 4. SensorSwarm アーキテクチャ

```
Brain (LLM) ← MQTT → Hub (ESP32) ← ESP-NOW/UART/I2C/BLE → Leaf デバイス
```

### MQTT トピック構造

```
# Hub 代理 publish (Leaf のデータ)
office/main/sensor/swarm_hub_01.leaf_env_01/temperature  → {"value": 22.5}
office/main/sensor/swarm_hub_01.leaf_pir_01/motion       → {"value": 1}
office/main/sensor/swarm_hub_01.leaf_door_01/door        → {"value": 0}

# Hub 自身
office/main/sensor/swarm_hub_01/heartbeat → {"status":"online","leaf_count":3}

# MCP (Brain → Hub → Leaf)
mcp/swarm_hub_01/request/call_tool  → leaf_command / get_swarm_status
mcp/swarm_hub_01/response/{id}     → JSON-RPC 2.0 response
```

### MCP ツール

| ツール | 引数 | 説明 |
|--------|------|------|
| `leaf_command` | leaf_id, command, args | Leaf にコマンド送信 (set_state, read_now, set_interval, deep_sleep, reset) |
| `get_swarm_status` | (なし) | 全 Leaf の状態一覧 (battery_mv, last_seen, capabilities, online) |

Brain からの呼び出し:
```
send_device_command(agent_id="swarm_hub_01", tool_name="leaf_command",
                    arguments='{"leaf_id":"leaf_relay_01","command":"set_state","args":{"state":"on"}}')
```

### ファイル構成

```
edge/lib/swarm/              # 共有 MicroPython ライブラリ
  message.py                 # バイナリ codec
  hub.py                     # SwarmHub (MCPDevice composition)
  leaf.py                    # SwarmLeaf 基底クラス
  transport_espnow.py        # ESP-NOW
  transport_uart.py          # UART (フレーム同期)
  transport_i2c.py           # I2C マスタ
  transport_ble.py           # BLE (スタブ)

edge/swarm/                  # デバイスファームウェア
  hub-node/                  # Hub: ESP32-S3/C6
  leaf-espnow/               # Leaf: ESP32-C3/C6
  leaf-uart/                 # Leaf: Pi Pico
  leaf-arduino/              # Leaf: ATtiny (I2C), nRF54 (BLE)

infra/virtual_edge/src/      # 仮想エミュレータ
  swarm_transport.py         # インメモリトランスポート
  swarm_leaf.py              # 仮想 Leaf (4種)
  swarm_hub.py               # 仮想 Hub (VirtualDevice 拡張)
```

---

## 5. 過去セッションの作業

### Session E: GPU テスト + ローカル LLM ベンチマーク
- RX 9700 (RDNA4) ROCm 認識、Ollama コンテナ起動
- qwen2.5:14b: ~51 tok/s、Brain ReAct 正常動作
- ベンチマーク: 12リクエスト 0エラー、ツール呼び出し精度 OK

### Session D: ダッシュボード音声改善 + LLM切替
- 音声バグ修正、リジェクションストック、mock-LLM 修正
- UI改善、正常時発話抑制

### Session C: カーネル安定化 + GPU 分離
- dGPU のみ Docker パススルー、iGPU 保護

### Session B: バグ修正
- models.py 重複カラム、voice-service LLM_API_URL

### Session A: Edge デバイスリファクタリング
- per-channel テレメトリ、soms_mcp.py、MCP JSON-RPC 2.0

---

## 6. 現在の環境

### Docker コンテナ

| コンテナ | 状態 | ポート |
|---------|------|--------|
| soms-mqtt | Running | 1883, 9001 |
| soms-brain | Running | — |
| soms-backend | Running | 8000 |
| soms-frontend | Running | 80 |
| soms-mock-llm | Running | 8001 |
| soms-voice | Running | 8002 |
| soms-voicevox | Running | 50021 |
| soms-ollama | Running | 11434 |
| soms-perception | Running | host network |
| soms-virtual-edge | Running | — |
| soms-postgres | Running | 5432 |

### .env (重要な値)

```
LLM_API_URL=http://host.docker.internal:11434/v1
LLM_MODEL=qwen2.5:14b
MQTT_BROKER=mosquitto
```

---

## 7. 次のアクション

### A. 優先度高

1. **App.tsx merge conflict 解決** — wallet ブランチからの stash pop で発生
2. **Wallet サービス統合テスト** — PostgreSQL + double-entry ledger
3. **SensorSwarm 実機テスト** — ESP32-S3 Hub + ESP32-C3 Leaf で ESP-NOW 通信確認

### B. 優先度中

4. **BLE トランスポート実装** — nRF54L15 用 (現在スタブ)
5. **Wake Chain 検証** — PIR Leaf → Camera 起床の GPIO 配線テスト
6. **バッテリー監視ダッシュボード** — get_swarm_status データの可視化

### C. 優先度低

7. 受諾音声のストック化 (現在は毎回 VOICEVOX 合成待ち 1-2秒)
8. Sub-GHz (LoRa) トランスポート追加
9. Leaf ファームウェア OTA アップデート機構

---

## 8. ハードウェア構成

| コンポーネント | 詳細 |
|---------------|------|
| CPU | AMD Ryzen 7 9800X3D (8C/16T, Raphael, iGPU 内蔵) |
| dGPU | AMD RX 9700 (RDNA4, gfx1201, 32GB VRAM, PCI 03:00.0) |
| iGPU | AMD Raphael (gfx1036, PCI 0e:00.0, ディスプレイ用) |
| カーネル | 6.17.0-14-generic |
| amdgpu-dkms | 6.16.6 (ROCk module) |
| Ollama | v0.16.0 (rocm イメージ) |
| LLM | qwen2.5:14b (9.0 GB, ~51 tok/s) |
| TTS | VOICEVOX (speaker 47: ナースロボ_タイプT) |

---

## 9. 既知の問題

| 問題 | 重要度 | 詳細 |
|------|--------|------|
| App.tsx merge conflict | 高 | wallet stash pop で発生、手動解決必要 |
| DRI ノード番号変動リスク | 中 | カーネル変更で card1/card2 入れ替わる可能性 |
| 受諾音声は合成待ち | 低 | ストック化されていないため 1-2秒レイテンシ |
| BLE トランスポート未実装 | 低 | スタブのみ、nRF54L15 実機待ち |
