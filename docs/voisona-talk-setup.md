# VoiSona Talk VM セットアップガイド

Linux (Ubuntu) 上で Windows VM を動かし、VoiSona Talk の音声合成 API を LAN 内に公開する構成。

## 構成概要

```
[HEMS / LAN デバイス]
        │
        │ HTTP (192.168.1.173:32766)
        ▼
   [Linux ホスト] ─── br0 ブリッジ ─── [Windows 11 VM]
   192.168.1.180                       192.168.1.173
                                         │
                                    portproxy (v4tov6)
                                    0.0.0.0:32766 → [::1]:32766
                                         │
                                    [VoiSona Talk API]
                                    [::1]:32766
```

## VM スペック

| 項目 | 値 |
|------|-----|
| VM名 | `win11-voisona` |
| OS | Windows 11 (24H2) |
| CPU | 4コア (host-passthrough) |
| RAM | 8GB |
| ディスク | 60GB qcow2 (virtio) |
| ネットワーク | ブリッジ `br0` (virtio) |
| 固定IP | `192.168.1.173` |
| オーディオ | SPICE経由 |

## 自動起動の流れ

1. ホスト起動 → VM 自動起動 (`virsh autostart`)
2. Windows 自動ログイン（ローカルアカウント・パスワードなし）
3. VoiSona Talk 起動（タスクスケジューラ、ログオン後30秒遅延）
4. virt-manager 自動接続（`~/.config/autostart/virt-viewer-voisona.desktop`、音声出力用）

## API 仕様

- ベースURL: `http://192.168.1.173:32766/api/talk/v1`
- 認証: Basic認証
- 詳細仕様: `/home/sin/Downloads/talk_api.yaml`

### ボイス一覧取得

```bash
curl -u "user:pass" http://192.168.1.173:32766/api/talk/v1/voices
```

### 音声合成（スピーカー再生）

```bash
curl -u "user:pass" \
  -X POST http://192.168.1.173:32766/api/talk/v1/speech-syntheses \
  -H "Content-Type: application/json" \
  -d '{
    "language": "ja_JP",
    "text": "こんにちは",
    "voice_name": "nurse-robot-type-t_ja_JP",
    "force_enqueue": true
  }'
```

レスポンス:
```json
{"uuid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"}
```

### 合成状態確認

```bash
curl -u "user:pass" \
  http://192.168.1.173:32766/api/talk/v1/speech-syntheses/{uuid}
```

state: `queued` → `running` → `succeeded` / `failed`

### 音声合成パラメータ

| パラメータ | 範囲 | デフォルト | 説明 |
|-----------|------|-----------|------|
| speed | 0.2 〜 5.0 | 1.0 | 話速 |
| pitch | -600 〜 600 | 0 | ピッチ (cent) |
| volume | -8 〜 8 | 0 | 音量 (dB) |
| intonation | 0 〜 2 | 1.0 | 抑揚 |
| huskiness | -20 〜 20 | 0 | ハスキー度 |
| alp | -1 〜 1 | 0 | 声の年齢感 |

使用例:
```json
{
  "language": "ja_JP",
  "text": "こんにちは",
  "voice_name": "nurse-robot-type-t_ja_JP",
  "force_enqueue": true,
  "global_parameters": {
    "speed": 1.2,
    "pitch": 100,
    "volume": 3
  }
}
```

### 利用可能ボイス

| 名前 | voice_name | バージョン |
|------|-----------|-----------|
| ナースロボ＿タイプＴ | `nurse-robot-type-t_ja_JP` | 2.0.0 |

## ネットワーク詳細

### ブリッジ構成 (ホスト側)

```bash
# NetworkManager で構築済み
nmcli con show br0        # ブリッジ確認
nmcli con show br0-slave  # スレーブ (enp10s0) 確認
```

### portproxy (VM内)

VoiSona Talk は `[::1]:32766` (IPv6 ループバック) でリッスンするため、
`netsh portproxy` (v4tov6) で外部からのアクセスを転送している。

```powershell
# 確認
netsh interface portproxy show all

# 再設定（消えた場合）
netsh interface portproxy add v4tov6 listenaddress=0.0.0.0 listenport=32766 connectaddress=::1 connectport=32766
```

**注意**: `virsh destroy`（強制停止）すると portproxy 設定が消える。正常シャットダウンなら永続。

## 運用コマンド

```bash
# VM 状態確認
virsh list --all

# VM 起動
virsh start win11-voisona

# VM 正常シャットダウン
virsh shutdown win11-voisona

# VM 強制停止（portproxy が消えるので非推奨）
virsh destroy win11-voisona

# コンソール接続
virt-manager --connect qemu:///system --show-domain-console win11-voisona
```

## トラブルシューティング

### API に接続できない
1. VM が起動しているか: `virsh list`
2. VoiSona Talk が起動しているか: virt-manager で確認
3. portproxy が設定されているか: VM内で `netsh interface portproxy show all`
4. ファイアウォール: VM内で `netstat -an | findstr 32766` で LISTEN 確認

### 音声が聞こえない
- virt-manager のコンソールウィンドウが開いているか確認（SPICE 音声出力に必要）
- Windows の音量がミュートになっていないか確認

### 合成が failed になる
- VoiSona Talk のボイスライブラリの認証状態を確認
- 起動直後はライブラリ初期化に時間がかかる場合がある

## HEMS 統合

`audio_device` モードで動作。VoiSona が VM スピーカー経由で直接再生する。
HEMS voice service は合成結果として空の `audio_data` を返すため、フロントエンドでは
「既に直接再生済み」として音声キューをスキップする。

### .env 設定

```bash
TTS_PROVIDER=voisona
TTS_FALLBACK=voicevox        # VoiSona VM 停止時の fallback
VOISONA_URL=http://192.168.1.173:32766
VOISONA_USERNAME=user@example.com
VOISONA_PASSWORD=your_password
VOISONA_VOICE_NAME=nurse-robot-type-t_ja_JP
VOISONA_LANGUAGE=ja_JP
```

### 動作フロー

```
Brain speak tool → voice-service /api/voice/synthesize
    → VoisonaProvider.synthesize()
        → POST /api/talk/v1/speech-syntheses
        → Poll GET /api/talk/v1/speech-syntheses/{uuid}
        → state=succeeded → AudioResult(audio_data=b"", format="wav", duration=duration)
    → voice-service sets played_directly=true because audio_data is empty
    → VoiSona VM がスピーカーで直接再生 (SPICE → ホスト音声出力)
```

### 注意点
- `audio_data` が空のため voice-service が `played_directly=true` を設定し、フロントエンドでの音声再生はスキップされる
- 音声はVMのSPICE出力経由でホストスピーカーから鳴る
- virt-manager のコンソール接続が必須（SPICE音声転送のため）
- `HEMS_INTERNAL_TOKEN` を設定している場合、`/api/voice/synthesize` へ `Authorization: Bearer <token>` が必要

## キャラクターYAMLとの連携

キャラクター YAML の `voice.voisona` セクションで、VoiSona Talk API の全パラメータをトーン別に制御できる。

### パラメータ一覧

| パラメータ | 範囲 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `speed` | 0.2 – 5.0 | 1.0 | 話速 |
| `pitch` | -600 – 600 | 0 | ピッチ (cent) |
| `volume` | -8 – 8 | 0 | 音量 (dB) |
| `intonation` | 0 – 2 | 1.0 | 抑揚スケール |
| `huskiness` | -20 – 20 | 0 | ハスキー度（息混じり感） |
| `alp` | -1 – 1 | 0 | 声の年齢感 (alpha) |
| `style_weights` | [0–1, ...] | テンプレート依存 | スタイル補間ウェイト。コード上の固定 default ではなく、キャラクターテンプレートで慣例的に使われる値 |

### style_weights

ナースロボ＿タイプTのスタイル名（`GET /voices/nurse-robot-type-t_ja_JP/{version}`）:

| インデックス | スタイル名 |
|------------|-----------|
| 0 | Normal |
| 1 | Happy |
| 2 | Angry |
| 3 | Sad |
| 4 | Smol |

例: `[0.4, 0.3, 0.0, 0.0, 0.3]` = Normal 40% + Happy 30% + Smol 30%

### キャラクターYAML例

```yaml
voice:
  backend: "voisona"
  voisona:
    # ベースパラメータ（全トーン共通のデフォルト）
    speed: 0.95
    intonation: 0.85
    huskiness: 3
    alp: 0.15
    # トーン別オーバーライド
    tones:
      neutral:
        style_weights: [1.0, 0.0, 0.0, 0.0, 0.0]
      caring:
        style_weights: [0.4, 0.3, 0.0, 0.0, 0.3]
        speed: 0.85
        huskiness: 5
      alert:
        style_weights: [0.2, 0.0, 0.5, 0.3, 0.0]
        speed: 1.05
        volume: 1.5
```

### パラメータの適用フロー

```
Brain speak tool (tone="caring")
  → tool_executor: POST /api/voice/synthesize {text, tone}
    → VoisonaProvider._build_params("caring", speed=1.0)
      1. base params from YAML (speed=0.95, huskiness=3, ...)
      2. tone override (caring: speed=0.85, huskiness=5, style_weights=[...])
      3. runtime speed multiplier
      4. clamp to API limits
      5. remove defaults → minimal global_parameters
    → POST /api/talk/v1/speech-syntheses {global_parameters: {...}}
```

### バリデーション

```bash
# 単体
python validate_character.py config/characters/nurserobo-typet.yaml -v

# 全テンプレート
python validate_character.py --all
```
