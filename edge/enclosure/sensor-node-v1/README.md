# SOMS Sensor Node Enclosure v1.0

Parametric 3D-printable enclosure for the SOMS environmental sensor node.

## Target Hardware

| Component | Model | Role |
|-----------|-------|------|
| MCU | XIAO ESP32-C6 | WiFi 6, MCP/MQTT |
| Temp/Humidity/VOC | BME680 | I2C |
| CO₂ | MH-Z19C | UART (NDIR) |
| PIR (optional) | AM312 or HC-SR501 | GPIO |
| Fan (optional) | 25mm 5V | Forced exhaust |
| Connectors | JST-XH 2.5mm | Detachable wiring |

## Structure

```
┌─────────────────┐
│  Exhaust (top)   │  ← Hex vent / fan mount
├─────────────────┤
│  MCU Chamber     │  ← XIAO ESP32-C6
│  (upper)         │     Heat rises → exits top
├━━━━━━━━━━━━━━━━━┤  ← Thermal barrier (3mm solid + 5mm air gap)
│  Sensor Chamber  │  ← BME680 + MH-Z19C
│  (lower)         │     Cool air intake from below
├─────────────────┤
│  Intake (bottom) │  ← Side louvers
└─────────────────┘
     USB-C cable
```

## Parts (STL Export)

Change `part` variable in `enclosure.scad`:

| part | Description | Print orientation |
|------|-------------|-------------------|
| `"bottom"` | Sensor chamber + barrier | As-is (flat bottom on bed) |
| `"top"` | MCU chamber (no fan) | Auto-flipped (ceiling on bed) |
| `"top_fan"` | MCU chamber + 25mm fan | Auto-flipped |
| `"shell"` | Decorative outer cover | As-is |
| `"pir_am312"` | PIR insert for AM312 | As-is |
| `"pir_hcsr501"` | PIR insert for HC-SR501 | As-is |
| `"pir_blank"` | Blank cap (no PIR) | As-is |
| `"assembly"` | Visual check (exploded view) | — |

## Dimensions

| | Width | Depth | Height |
|---|---|---|---|
| Chassis (no fan) | 55.2mm | 33.2mm | 50.2mm |
| Chassis (with fan) | 55.2mm | 33.2mm | 59.2mm |
| Outer shell | 66.4mm | 44.4mm | 64.2mm |

## Print Settings

- **Material**: PETG recommended (heat resistance + flexibility)
- **Nozzle**: 0.4mm
- **Layer**: 0.2mm
- **Wall**: 4 perimeters (= 1.6mm)
- **Infill**: 20% gyroid
- **Supports**: Not required (designed for supportless printing)

## Assembly

1. Press M2 heat-set inserts into bottom half barrier (4x)
2. Wire sensors with JST-XH connectors
3. Mount MH-Z19C and BME680 in sensor chamber
4. Mount XIAO ESP32-C6 on rails in MCU chamber
5. Connect inter-chamber XH-8P harness through barrier
6. Join halves with M2×10 screws (through standoffs into inserts)
7. Insert PIR adapter (AM312/HC-SR501/blank)
8. Slide outer shell over chassis

## Wiring (JST-XH)

### Inter-chamber harness (XH-8P)

| Pin | Signal | Color (suggested) |
|-----|--------|-------------------|
| 1 | 3V3 | Red |
| 2 | GND | Black |
| 3 | SDA (I2C) | Blue |
| 4 | SCL (I2C) | Yellow |
| 5 | UART TX (CO₂) | Green |
| 6 | UART RX (CO₂) | White |
| 7 | PIR OUT | Orange |
| 8 | Reserved | — |

---

## OpenSCAD クイックガイド

### インストール

```bash
# Ubuntu / Debian
sudo apt install openscad

# Arch Linux
sudo pacman -S openscad

# macOS (Homebrew)
brew install --cask openscad

# Windows — https://openscad.org/downloads.html からインストーラを取得
```

### 基本操作

OpenSCAD はテキストベースの 3D CAD。`.scad` ファイルをコードとして記述し、プレビュー/レンダリングする。

| 操作 | ショートカット | 説明 |
|------|---------------|------|
| プレビュー | `F5` | 高速プレビュー（形状確認用） |
| レンダリング | `F6` | 完全レンダリング（STL出力前に必須） |
| STL出力 | `F7` | レンダリング後にSTLファイルとして保存 |
| ビューリセット | `Ctrl+0` | カメラをデフォルト位置に戻す |

マウス操作:
- **左ドラッグ** — 回転
- **右ドラッグ** — パン（平行移動）
- **スクロール** — ズーム

### このケースデータの使い方

#### 1. プレビュー（組み立て確認）

`enclosure.scad` を OpenSCAD で開く。デフォルトで `part = "assembly"` が設定されており、展開図（exploded view）が表示される。

```bash
openscad edge/enclosure/sensor-node-v1/enclosure.scad
```

`F5` を押すとプレビューが描画される。半透明パーツはゴースト表示（部品位置の参考用）。

#### 2. パーツ個別の STL エクスポート

印刷するパーツごとに `part` 変数を変更して STL を出力する。

**GUI の場合:**

1. エディタ上部の `part = "assembly";` を変更（例: `part = "bottom";`）
2. `F6` で完全レンダリング（数十秒かかる場合がある）
3. `File` → `Export` → `Export as STL...` または `F7`

**コマンドラインの場合（バッチ出力）:**

```bash
cd edge/enclosure/sensor-node-v1

# 個別出力
openscad -o bottom.stl -D 'part="bottom"' enclosure.scad
openscad -o top.stl -D 'part="top"' enclosure.scad
openscad -o shell.stl -D 'part="shell"' enclosure.scad
openscad -o pir_am312.stl -D 'part="pir_am312"' enclosure.scad

# 全パーツ一括出力
for p in bottom top top_fan shell pir_am312 pir_hcsr501 pir_blank; do
  openscad -o "${p}.stl" -D "part=\"${p}\"" enclosure.scad
  echo "Exported: ${p}.stl"
done
```

#### 3. パラメータのカスタマイズ

ファイル冒頭のパラメータセクションを編集して寸法を調整できる。

```openscad
// --- Print settings ---
wall    = 1.6;      // 壁厚（ノズル径×ペリメータ数）
tol     = 0.3;      // 嵌合クリアランス（プリンタ精度に応じて調整）
layer   = 0.2;      // 積層ピッチ
nozzle  = 0.4;      // ノズル径

// --- Chamber internals [W, D, H] ---
SENS_INT = [52, 30, 22];   // センサー室の内寸
MCU_INT  = [52, 30, 17];   // MCU室の内寸
```

よくあるカスタマイズ:

| やりたいこと | 変更するパラメータ |
|-------------|-------------------|
| プリンタの精度に合わせる | `tol`（0.2〜0.4mm） |
| 壁を厚くする | `wall`（ノズル径の倍数にする） |
| センサー室を広げる | `SENS_INT` の各値 |
| ファンなし版を使う | `part = "top"`（`top_fan` ではなく） |
| PIR 不要 | `part = "pir_blank"` でブランクキャップを印刷 |

コマンドラインでもパラメータを上書きできる:

```bash
# クリアランスを 0.2mm に変更して出力
openscad -o bottom_tight.stl -D 'part="bottom"' -D 'tol=0.2' enclosure.scad
```

#### 4. 印刷する最小パーツセット

| 構成 | 必要パーツ |
|------|-----------|
| 基本（PIR なし、ファンなし） | `bottom` + `top` + `pir_blank` + `shell` |
| PIR あり（AM312） | `bottom` + `top` + `pir_am312` + `shell` |
| PIR あり（HC-SR501） | `bottom` + `top` + `pir_hcsr501` + `shell` |
| フル装備（PIR + ファン） | `bottom` + `top_fan` + `pir_am312` + `shell` |

### OpenSCAD の基本構文（参考）

このファイルで使用している主要な構文:

```openscad
// プリミティブ（基本形状）
cube([10, 20, 5]);              // 直方体 [幅, 奥行, 高さ]
cylinder(d = 10, h = 5);       // 円柱 (d=直径, h=高さ)
sphere(r = 5);                 // 球 (r=半径)

// 変換
translate([x, y, z])  ...      // 平行移動
rotate([rx, ry, rz])  ...      // 回転（度数）
scale([sx, sy, sz])   ...      // 拡大縮小

// ブーリアン演算（CSG）
difference() { A(); B(); }     // A から B を引く（穴あけ）
union() { A(); B(); }          // A と B を合体
intersection() { A(); B(); }   // A と B の共通部分

// よく使うパターン
hull() { ... }                 // 凸包（角丸の長穴などに使用）
linear_extrude(h) ...          // 2D形状を押し出して3Dにする
for (i = [0 : n]) ...          // ループ（配列パターン生成）

// モジュール（関数のようなもの）
module my_part(size) {         // 定義
    cube(size);
}
my_part([10, 20, 5]);          // 呼び出し

// 特殊変数
$fn = 48;                      // 円の分割数（大きいほど滑らか）
```

### トラブルシューティング

| 症状 | 対処 |
|------|------|
| F5 で何も表示されない | コンソール（下部パネル）にエラーがないか確認 |
| レンダリングが終わらない | `$fn` を一時的に下げる（例: `$fn = 24;`） |
| STL がスライサーで壊れている | F6 で完全レンダリングしてから出力したか確認 |
| パーツが嵌まらない | `tol` を 0.05mm ずつ増やす |
| 壁が薄すぎて印刷できない | `wall` をノズル径の 3〜4 倍に設定 |
