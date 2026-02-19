# SOMS 画像生成AIプロンプト集

スライド・記事・ウェブサイト用のビジュアル素材を生成するためのプロンプト集。
DALL-E 3 / Midjourney / Stable Diffusion 向けに最適化。
都市のAI化・分散型ローカル知能をビジュアルの主軸とする。

---

## 1. ヒーローイメージ: 都市のAI化 (メインビジュアル)

**用途**: `slides_pitch.md` スライド1, `slides_tech.md` スライド1, `article.md` アイキャッチ, LP ヒーロー

### DALL-E 3 / ChatGPT

```
An aerial view of a modern city at dusk, rendered in deep blue tones. Each building
has a warm golden pillar of light emanating upward from its rooftop, representing
autonomous local AI processing — each building "thinking" independently. The pillars
do NOT connect to any cloud above — instead, thin golden lines connect neighboring
buildings at ground level, representing minimal structured data exchange between
Core Hubs. The sky above is deliberately clear and dark, empty of cloud symbols.
One building in the foreground is larger and more detailed, showing glowing IoT
sensor nodes on its walls connected by neural-network-like golden threads to a
central crystalline structure on the roof (the Core Hub GPU server). A few people
are visible inside through windows, working alongside the intelligent environment.
Photorealistic, cinematic lighting, bird's eye perspective, 16:9 aspect ratio.
```

### Midjourney

```
/imagine aerial view modern city at dusk, deep blue tones, each building with warm
golden pillar of light from rooftop representing local AI brain, no cloud connections
above, thin golden lines between buildings at ground level for minimal data exchange,
clear dark sky without cloud symbols, foreground building showing IoT sensors connected
to rooftop Core Hub server, people visible inside, photorealistic cinematic lighting
--ar 16:9 --v 6.1 --style raw
```

### Stable Diffusion (SDXL)

```
Prompt: aerial view modern city at dusk, deep blue ambient, golden light pillars from
each building rooftop representing AI processing, no cloud symbols, thin golden lines
between buildings at ground level, foreground building with IoT sensors and neural
network threads, people inside, photorealistic cinematic
Negative: cartoon, anime, low quality, blurry, cloud computing symbols, AWS logos
Steps: 30, CFG: 7, Size: 1920x1080
```

---

## 2. Core Hub 概念図: 建物レベルの自律AI

**用途**: `slides_tech.md` スライド3-4, `slides_pitch.md` スライド3, `article.md` Core Hub セクション

### DALL-E 3 / ChatGPT

```
A cross-section architectural diagram of a modern office building, showing the
Core Hub concept. The building is rendered in clean technical illustration style
with subtle glow effects against a dark navy background (#0a1628).

At the top floor: a compact GPU server rack with a golden glowing "brain" symbol
(the LLM). From it, blue neural pathways (MQTT message bus) extend downward through
all floors. On each floor: small ESP32 sensor nodes with green LEDs mounted on walls
(connected via golden threads), and security cameras with blue lens glows.

On the ground floor: a wall-mounted dashboard display showing task cards with gold
reward badges. A person nearby holds a smartphone (wallet PWA). Outside the building:
a dotted golden line leads to a distant cluster of similar buildings (other Core Hubs),
with "~1MB/day" label showing minimal data exchange.

Above the building: clear sky, deliberately NO cloud symbols. The building is
self-contained and autonomous. Technical architectural diagram style, clean lines,
golden and blue accent colors on dark background.
```

### Midjourney

```
/imagine cross-section modern office building, Core Hub AI concept, dark navy background,
GPU server with golden brain on top floor, blue neural pathways extending through floors,
ESP32 sensors with green LEDs on walls, cameras with blue lens glow, dashboard with gold
badges on ground floor, person with smartphone, dotted golden line to distant buildings
showing minimal data exchange, no cloud symbols above, clean technical illustration
--ar 16:9 --v 6.1
```

---

## 3. 有機体メタファー: システム全体を一つの生命として

**用途**: `slides_tech.md` スライド5, `article.md` 有機体セクション

### DALL-E 3 / ChatGPT

```
A semi-transparent human silhouette standing in a modern office, viewed from the side.
Inside the silhouette, a glowing golden brain represents the LLM, with blue neural
pathways (MQTT) extending down through the body. The eyes glow with a camera lens
overlay (computer vision / YOLOv11). The hands extend outward: one hand connects to
small ESP32 circuit boards via golden threads (SensorSwarm), the other hand reaches
toward a floating smartphone showing a wallet app (human collaboration). Around the
figure, floating icons represent: a speaker (VOICEVOX voice), a wall dashboard screen,
sensor modules, and a small binary data stream (swarm protocol). At the feet, a
cluster of tiny Leaf sensor nodes connected to a central Hub node. The background
is dark navy blue (#0a1628). Clean, technical illustration style with subtle glow
effects. Labeled diagram aesthetic.
```

### Midjourney

```
/imagine semi-transparent human body silhouette in office, glowing golden brain inside
head representing LLM, blue neural pathways through body as MQTT, camera lens eyes for
YOLO vision, one hand connected to ESP32 IoT boards via golden threads, other hand
reaching to floating smartphone wallet app, speaker icon for voice, dashboard screen,
cluster of tiny leaf sensors at feet connected to hub node, dark navy background,
technical illustration subtle glow --ar 16:9 --v 6.1
```

---

## 4. SensorSwarm: 2層エッジネットワーク

**用途**: `slides_tech.md` スライド9, `article.md` SensorSwarm セクション

### DALL-E 3 / ChatGPT

```
A product photography style overhead shot of the SensorSwarm two-tier architecture
laid out on a clean dark surface. In the center: an ESP32 Hub node (slightly larger,
with WiFi antenna and green status LED, connected via USB cable). Around it in a
radial pattern: 4 smaller Leaf sensor nodes, each a tiny ESP32 board with different
sensors attached (BME680 silver module, MH-Z19C green module, DHT22 white module,
PIR motion sensor). Thin colored lines connect each Leaf to the Hub, with small
labels: "ESP-NOW", "UART", "I2C", "BLE" indicating the 4 transport types.

Above the Hub, a faint golden upward arrow labeled "MQTT → Core Hub". The overall
arrangement shows the hierarchical tree topology. Each node has a small label with
dot-notation device ID (e.g., "swarm_hub_01.leaf_env_01"). Technical product
photography, soft studio lighting, shallow depth of field on the Hub node.
```

### Midjourney

```
/imagine overhead product photography, ESP32 SensorSwarm network layout on dark surface,
central Hub node with WiFi antenna, 4 surrounding Leaf sensor nodes with different sensors
BME680 MH-Z19C DHT22 PIR, thin colored lines labeled ESP-NOW UART I2C BLE connecting
leaves to hub, golden arrow upward labeled MQTT, dot-notation device IDs, studio lighting
shallow depth of field --ar 16:9 --v 6.1 --style raw
```

---

## 5. 嵐のプロトコル (シナリオ説明)

**用途**: `slides_tech.md` スライド13, `article.md` シナリオセクション

### DALL-E 3 / ChatGPT

```
A dramatic scene viewed through a rain-streaked office window at twilight. Heavy rain
falls outside, visible through the glass. In the foreground, a person's hand holds a
smartphone displaying a task notification card with a glowing gold reward badge
showing "5000" points and a red "URGENT" label. The phone screen has a dark UI with
blue and gold accents. On the window sill, a small ESP32 sensor device with a green
LED blinks. The office interior is warmly lit with blue-tinted smart lighting. Behind
the person, a wall-mounted dashboard shows the same urgent task card highlighted in
gold. Cinematic, moody atmosphere, shallow depth of field focusing on the phone screen.
```

### Midjourney

```
/imagine dramatic rainy office window at twilight, person holding smartphone showing
task notification with gold reward badge "5000" and red urgent label, dark UI with
blue gold accents, ESP32 sensor on windowsill green LED, wall dashboard behind showing
same task, warm interior lighting, rain drops on glass, cinematic shallow depth of field
--ar 16:9 --v 6.1 --style raw
```

---

## 6. 都市の呼吸パターン (データビジュアライゼーション)

**用途**: `slides_pitch.md` スライド7, `slides_tech.md` スライド14, `article.md` 呼吸パターン

### DALL-E 3 / ChatGPT

```
A data visualization showing the "urban breathing pattern". The image is split into
two halves on a dark navy background (#0a1628).

Left half: A simplified city map viewed from above, with three districts colored
differently — blue (office district), green (commercial district), warm orange
(residential district). Each district has a subtle pulsing glow that varies in
intensity, showing CO2 concentration levels at different times. Golden arrows between
districts show the flow of people: residential→office (morning), office→commercial
(evening), commercial→residential (night).

Right half: Three overlaid time-series line charts (24-hour axis), one for each
district, showing CO2 peaks at different times. Lines are colored to match their
districts. Key peaks are annotated: "9:00 Office", "15:00 Commercial", "20:00
Residential". A small annotation reads "Data transmitted: ~1MB/Hub/day".

Clean data visualization style, minimal, information-rich. No decorative elements.
```

### Midjourney

```
/imagine data visualization urban breathing pattern on dark navy background, left side
city map with three colored districts blue green orange showing CO2 intensity, golden
arrows showing people flow between districts, right side three overlaid time-series
CO2 charts with peaks at different times, clean minimal infographic style, annotation
"1MB/Hub/day" --ar 16:9 --v 6.1
```

---

## 7. ダッシュボード + ウォレットPWA (プロダクト紹介)

**用途**: `slides_tech.md` スライド12, `article.md` 経済セクション

### DALL-E 3 / ChatGPT

```
Two devices displayed side by side on a dark surface. On the left: a large wall-mounted
monitor showing the SOMS dashboard — a dark-mode kiosk UI with 3 task cards arranged
vertically. Each card has a Japanese title, location badge in blue, gold circular
reward badge showing points (1500, 2000, 5000), colored urgency indicator, and action
buttons. One card is highlighted with golden glow. On the right: a smartphone showing
the wallet PWA — dark theme mobile app with a balance card showing credit amount,
bottom navigation tabs (Home, Scan, Send, History), and a QR code scanner view overlay.
Both screens share the same design language: dark navy background, blue and gold accents.
Photorealistic product photography, slight perspective angle showing both devices.
```

### Midjourney

```
/imagine wall monitor and smartphone side by side on dark surface, monitor showing
dark-mode dashboard with task cards Japanese text gold reward badges urgency indicators,
smartphone showing wallet PWA dark theme with balance card QR scanner bottom navigation,
both devices dark navy blue gold design language, photorealistic product photography
slight angle --ar 16:9 --v 6.1 --style raw
```

---

## 8. Core Hub ハードウェア (実物イメージ)

**用途**: `article.md` 技術スタック, LP 技術セクション

### DALL-E 3 / ChatGPT

```
A clean product photography shot of the Core Hub hardware setup on a white desk.
The setup consists of:
- A compact Mini PC (about the size of a thick book) with blue LED status light
- An AMD GPU (with red Radeon branding visible) connected via eGPU enclosure
- A small Mosquitto MQTT broker (symbolized by a tiny Raspberry Pi with antenna)
- 3 ESP32 sensor nodes scattered nearby (one with BME680, one with CO2 sensor,
  one camera module)
- Thin ethernet and USB cables connecting components cleanly

A small label reads "150W idle — 350W inference". The setup fits within an A4
paper outline drawn subtly on the desk surface. Studio lighting, clean white
background, technical product photography style, overhead angle.
```

### Midjourney

```
/imagine product photography Core Hub hardware on white desk, compact mini PC with
blue LED, AMD GPU in eGPU enclosure, 3 ESP32 sensor nodes with different sensors,
thin clean cabling, label "150W-350W", A4 paper outline showing compact footprint,
studio lighting clean white background overhead angle --ar 16:9 --v 6.1 --style raw
```

---

## スタイルガイドライン (共通)

### カラーパレット

プロンプトに含める色指定:

| 用途 | 色 | Hex |
|---|---|---|
| 背景 (ダーク) | ディープネイビー | `#0a1628` |
| アクセント (ゴールド) | ゴールド | `#FFD700` |
| テキスト / セカンダリ | ライトブルー | `#90CAF9` |
| プライマリ | ブルー | `#2196F3` |
| 成功 | グリーン | `#4CAF50` |
| 警告 | オレンジ | `#FF9800` |
| エラー / 緊急 | レッド | `#F44336` |

### トーン & ムード

- **都市知能**: 各建物が自律的に思考する、分散型AIのイメージ
- **ローカル優先**: クラウドの存在を示唆しない、空は常に澄んでいる
- **人間中心**: AIが支配するのではなく、人間と協働するイメージ
- **有機的**: 機械的な直線より、神経系のような曲線と光の粒子
- **温かみ**: 冷たいSFではなく、人間の生活に溶け込むテクノロジー

### 解像度

| 用途 | 推奨サイズ |
|---|---|
| スライド背景 | 1920 x 1080 (16:9) |
| 記事アイキャッチ | 1200 x 630 (OGP) |
| 記事内挿絵 | 1200 x 800 |
| ウェブサイトヒーロー | 1920 x 1080 |

### ネガティブプロンプト (共通)

Stable Diffusion 向け:
```
cartoon, anime, low quality, blurry, distorted faces, text, watermark,
signature, oversaturated, cloud computing symbols, AWS/Azure/GCP logos,
centralized server room, data center
```
