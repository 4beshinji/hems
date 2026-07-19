# HEMS Distribution & Onboarding Roadmap

最終更新: 2026-06-17

2026-05-25 配布・オンボーディングの摩擦監査(git clone → 稼働 dashboard までの全工程)に基づく Phase 番号付きロードマップ。

現行導入はエンジニアでも厳しい。原因は思想ではなく **具体箇所に集中** している。解は「全部ワンクリック」ではなく **体験までの距離でレイヤを割る** こと — GPU passthrough / Zigbee USB / HA `network_mode: host` は本質的に手作業なので、ハード不要の core を即動かせる導線と、上級者向け導線を分離する。

**対象**(両睨み、選択肢をもたせる):
- ② 他エンジニア / 自作勢への OSS 配布 — clone せず `pull && up` で動く。
- ③ 非エンジニア向けプロダクト化 — CLI を触らず Web で設定。

**前提方針**:
- 簡単パスの既定 LLM は **ローカル Ollama**（quickstart 後に `docker compose --profile ollama up -d` で起動）。クラウド / GPU チューニングは上級導線(Phase 4)。mock LLM は開発用の代替。
- 正規 `infra/docker-compose.yml` を **配布正本**(`image:` 参照・source mount 無し)に反転し、build + source mount は dev overlay へ退避（Phase 0.2 TODO）。

**関連ドキュメント**:
- [`../README.md`](../README.md) Quick Start(Phase 1 で1コマンド化)
- [`IMPLEMENTATION_MAP.md`](IMPLEMENTATION_MAP.md) §1 サービス棚卸し / §9 env カバレッジ
- [`CLAUDE-bridges.md`](CLAUDE-bridges.md)(profile 別の詳細)
- Tier 3 setup ガイド群(Phase 4 で隔離・リンク): [`SMART_HOME_SETUP.md`](SMART_HOME_SETUP.md) / [`ha-isolation.md`](ha-isolation.md) / [`smartband-setup.md`](smartband-setup.md) / [`voisona-talk-setup.md`](voisona-talk-setup.md) / [`avatar-setup.md`](avatar-setup.md)

---

## 1. 現状の摩擦点(file:line で検証済)

| # | 摩擦 | 検証位置 | 影響 | 状態 |
|---|---|---|---|---|
| F1 | 事前ビルド済みイメージが無い。CI は build 検証のみで push しない | `.github/workflows/ci.yml:115,124`(`push: false`)、login-action / `permissions: packages` 無し | 全ユーザが base + 17 イメージをローカルで 10〜30 分ビルド | **TODO (Phase 0.1)** |
| F2 | base イメージが暗黙の前提 | `infra/base/Dockerfile`、全 Python service の `FROM hems-base:py3.11` | bootstrap 飛ばすと `image not found: hems-base:py3.11` で死ぬ | **TODO (Phase 0.2)** |
| F3 | `.env` 必須シークレットが hard-fail | `infra/docker-compose.yml` の `${MQTT_PASS:?}`(15 サービス参照)、`${POSTGRES_PASSWORD:?}` | 未設定だと bash 置換エラーで意味不明な死。default は検証されない `CHANGE_ME_BEFORE_USE` | **解消 (Phase 1.1)**。`make quickstart` が未存在時に安全な乱数値を生成 |
| F4 | 既定値が3層でバラバラ(zero-config が必ず壊れる) | TTS: `env.example`/`docker-compose.yml`/`provider_factory.py` はすべて `voicevox`（fallback `espeak`）。LLM: `env.example`/`docker-compose.yml`/`llm_client.py` は `ollama` / `gemma4:e4b-it-q8_0` に統一 | 起動直後に TTS / LLM エラー。「壊れてる」と誤認 | **解消 (Phase 1.2)**。zero-config = voicevox + Ollama(gemma4) |
| F5 | Ollama モデル pull が無言 10〜30 分 | `docker-compose.yml:497`(ollama-pull one-shot) | 「動いた」と思った頃にまだ DL 中。進捗不可視 | **TODO (Phase 4)**。上級導線へ隔離 |
| F6 | GPU 設定が Quick Start に未掲載 | `infra/scripts/gpu_setup.py` | GPU 持ちでも CPU 動作で「遅い」 | **TODO (Phase 4)**。上級導線へ隔離 |
| F7 | **source bind-mount が pull 配布を破壊** | `docker-compose.yml` の 14 本 `../services/<svc>/src:/app`(L100/138/204/303/340/397/430/562/596/630/694/730/766/804) | clone せず pull のみだと空ディレクトリがコードを上書きし即死。**overlay は volume 削除不可** のため dist overlay では解けない | **TODO (Phase 0.2)** |
| F8 | env 変数 205 個(必須は実質3)に tier 区分なし | `env.example`(397 行) | どれが必要か判別不能 | **TODO (Phase 2)** |

---

## 2. Phase 計画

| Phase | 優先 | 主眼 | 状態 |
|---|---|---|---|
| Phase 0 — イメージ publish & compose 配布化 | P0 | ローカルビルド消滅(F1/F2/F7) | **未実装** |
| Phase 1 — ワンコマンド導入 + 既定修復 | P0 | 約2分で dashboard(F3/F4/F6) | **実装済み** |
| Phase 2 — プロファイル束 + env 再編 | P1 | tier 選択を平易化(F8) | **未実装** |
| Phase 3 — 非エンジニア向け初回ウィザード | P2 | CLI 不要化(対象③) | **未実装** |
| Phase 4 — 上級導線(GPU/Zigbee/HA)の隔離 | P2 | 簡単パスを汚さない(F5/F6) | **未実装** |

Phase 0 + 1 だけで「エンジニアでも厳しい」はほぼ解消する。

### Phase 0 — イメージ publish & compose 配布化(P0、全レイヤの土台) **【未実装】**

| # | 項目 | 工数 | 効果 | 状態 |
|---|---|---|---|---|
| 0.1 | `ci.yml` の `docker-build` job に `permissions: packages: write` + `docker/login-action@v3`(ghcr.io / `${{ github.actor }}` / `${{ secrets.GITHUB_TOKEN }}`)を追加し、両 `build-push-action`(base `:111` / service `:121`)を `push: true` 化。tags = `:latest` + `:${{ github.sha }}`。安定配布は git tag `v*` トリガで release publish(`:v*`)を推奨 | 1.5h | F1 解消。CI が GHCR に全イメージを publish | **未着手** |
| 0.2 | `infra/docker-compose.yml` を配布正本に反転。15 サービスの `build: ../services/<svc>` → `image: ghcr.io/4beshinji/hems-<svc>:${HEMS_VERSION:-latest}`。**source bind-mount 14 本を除去**。残す mount: `../config:/config:ro`、zigbee `../config/zigbee2mqtt`、`${OBSIDIAN_VAULT_PATH}`、`${KNOWLEDGE_SOURCE_PWS}`、mosquitto config、data volume | 2h | F2/F7 解消。`docker compose pull && up` が成立 | **未着手** |
| 0.3 | dev overlay(`infra/docker-compose.dev.yml`)を新設。14 サービスへ `build:` + source mount を移設。開発時は配布正本に overlay する | 1h | 開発時の live-reload を維持 | **未着手** |

base レイヤは各 service image に焼き込まれる(`FROM hems-base:py3.11`)ため、**end-user は base を別 pull する必要なし**。

```bash
# 検証(0.1 publish 後)
git tag v0.1.0 && git push origin v0.1.0     # release publish トリガ
docker pull ghcr.io/4beshinji/hems-brain:latest   # 認証なしで取得できる(public 設定後)

# 検証(0.2/0.3 配布化後 — clone した repo でも pull で動くこと)
cd infra && docker compose pull && docker compose up -d   # build せず起動
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build  # 開発時
```

### Phase 1 — ワンコマンド導入 + 既定修復(P0) **【実装済み】**

| # | 項目 | 効果 | 状態 |
|---|---|---|---|
| 1.1 | `make quickstart`: `.env` 未存在時に `cp env.example .env` → `python infra/scripts/init_env.py` で安全な乱数値を生成(`POSTGRES_PASSWORD` / `MQTT_PASS` / `HEMS_INTERNAL_TOKEN` / `BACKEND_API_KEY`)→ `docker compose up -d --build` → core 起動。SQLite 軽量版は `make quickstart-sqlite` | F3 解消。clone から約2分で稼働 | **done**。`Makefile` / `infra/scripts/init_env.py` で実装済み |
| 1.2 | **既定値3層整合(zero-config = espeak + mock)**。`env.example` / `docker-compose.yml` / service code を1ストーリーに揃える | F4 解消。起動直後にエラーが出ない | **done** |
| 1.3 | `Makefile` に `up` / `down` / `logs` / `ps` を追加(`.PHONY:1` 更新、既存と衝突なし) | orchestration を make に統一 | **done** |
| 1.4 | `README.md` Quick Start(L8-19)を1コマンドへ書換え。mock 既定の旨とクラウドキー導線を明記 | 入口を平易化 | **done** |

**1.2 既定値の touch-points**(3層すべて変えないと不整合が残る):

| 層 | TTS | LLM |
|---|---|---|
| `env.example` | `:76` espeak、`:78` TTS_FALLBACK | `:40` LLM_PROVIDER、`:46` LLM_API_URL、`:47` LLM_MODEL |
| `infra/docker-compose.yml` | voice `:188` `:-espeak`、`:189` | brain `:57-59`、voice `:197-198` |
| service code | `services/voice/src/provider_factory.py:45`(espeak) | `services/brain/src/llm_client.py:23`(openai)/`:28`(mock-llm url 既定済)/`:29`(gpt-4o-mini) |

> zero-config の目標形: **TTS=espeak**(`services/voice/src/providers/espeak.py`、外部 URL/認証ゼロ)+ **LLM=mock**(`--profile mock` の `infra/mock_llm/`、OpenAI 互換・鍵不要)。クラウド利用時は `.env` に API キーを置けば上書きされる。

```bash
# 検証(clean clone から)
git clone <repo> hems && cd hems
make quickstart
# → 約2分後 http://localhost:8080 が表示
docker compose logs voice-service brain | grep -iE 'error|traceback'   # 既定で空であること
```

**PostgreSQL 既定化 / SQLite 軽量モード**:
- `make quickstart` は PostgreSQL _profile_ を含む完全版を起動する。
- `make quickstart-sqlite` は file-based SQLite で動作する軽量モード。Raspberry Pi や検証用に適している。
- いずれも `infra/scripts/init_env.py` が初回のみ `.env` を生成し、必須シークレットを埋める。
- いずれもBackend containerはAlembic `upgrade head`成功後だけAPIを起動する。upgrade前にPostgreSQL backupまたは
  SQLite DB file copyを取得し、失敗時はAPIを公開せずschema不整合を修正してforward-fixする。

### Phase 2 — プロファイル束 + env 再編(P1) **【未実装】**

| # | 項目 | 工数 | 効果 | 状態 |
|---|---|---|---|---|
| 2.1 | 名前付き tier `core` / `home`(HA/SwitchBot/Tapo)/ `ai`(ollama/perception/stt)/ `all`。依存自動解決(`news`→`ollama`、perception VLM→`ollama`、`stt` LLM rewrite→LLM)。compose profile 別名 or make target or `hems` CLI wrapper | 3h | F8 緩和。組合せ知識が不要に | **未着手** |
| 2.2 | `env.example` 再編。冒頭に REQUIRED ブロック(必須3)、残りを profile 別セクションへ折り畳み | 1.5h | 必須/任意の判別が一目で付く | **未着手** |
| 2.3 | `IMPLEMENTATION_MAP.md` §9 へ `HEMS_VERSION` / 新 tier profile を追記 | 30m | SoT 整合 | **未着手** |

```bash
# 検証(将来形)
make core      # ハード不要・即動
make ai        # ollama + perception + stt(依存解決込み)
docker compose --profile news up -d   # ollama 未起動なら警告 or 自動 pull
```

### Phase 3 — 非エンジニア向け初回ウィザード(P2) **【未実装】**

現状 frontend に初回設定画面は **皆無**(backend 稼働を前提に即ロード)。

| # | 項目 | 工数 | 効果 | 状態 |
|---|---|---|---|---|
| 3.1 | backend `/setup` router + 「設定済み」フラグ。未設定時に frontend をウィザードへ誘導 | 4h | CLI を触らず設定可能に | **未着手** |
| 3.2 | frontend 初回ウィザード(キャラ選択 / LLM=クラウド鍵貼付 or デモ / TTS / ルーム名)→ runtime config 保存 | 8h | 対象③ への入口 | **未着手** |
| 3.3 | 配布形態(Docker Desktop ランチャ / Tailscale 配布)| TBD | GUI 起動。最後段(重い) | **未着手** |

### Phase 4 — 上級導線(GPU/Zigbee/HA)の隔離(P2) **【未実装】**

| # | 項目 | 工数 | 効果 | 状態 |
|---|---|---|---|---|
| 4.1 | GPU(`infra/scripts/gpu_setup.py`)・Zigbee USB passthrough・HA `network_mode: host`+`privileged` を `make ai` / `make zigbee` + 本 doc「Advanced setup」節へ隔離。簡単パスから完全分離 | 2h | F5/F6 を簡単パスから切離し | **未着手** |
| 4.2 | 既存 Tier 3 setup docs(`SMART_HOME_SETUP.md` / `ha-isolation.md` / `smartband-setup.md` / `voisona-talk-setup.md` / `avatar-setup.md`)へリンク。内容は重複させない | 30m | doc グラフ整合 | **未着手** |

---

## 3. GHCR イメージ命名

- 形式: `ghcr.io/4beshinji/hems-<svc>`(`brain` / `backend` / `frontend` / `voice` / 各 bridge / `perception` / `stt`)。container_name の `hems-<svc>` パターンと一致。
- tag: `:latest`(main push)+ `:${{ github.sha }}`(追跡用)+ release 時 `:v*`(配布の pin 対象)。`docker-compose.yml` は `${HEMS_VERSION:-latest}`。
- **heavy(perception / stt)は torch で巨大** → core(brain/backend/frontend/voice/bridges)と分離して pull。簡単パスは core のみ即取得。
- 初回 publish 後、GHCR package を **public** に設定(認証なし pull のため)。

> **現状**: GHCR への publish は Phase 0.1 で計画しているが **未着手**である。現時点ではすべてローカルビルドが必要。

---

## 4. 依存関係

```
Phase 0 (publish + 配布化) ──┬──> Phase 1 (quickstart + 既定修復)
                             │
                             └──> Phase 2 (tier 束 + env 再編)   ※0 後に 1 と並行可

Phase 1 ──> Phase 3 (Web ウィザード)

Phase 4 (上級導線隔離) ── 独立(いつでも可、ただし 2 の tier 定義と整合)
```

Phase 0 が全レイヤの前提。1 と 2 は 0 完了後に並行可能。3 は 1 の後。4 は独立。
現時点では **Phase 1 のみ完了** しており、Phase 0/2/3/4 は未着手。

---

## 5. 既知のリスク

1. **perception/stt イメージ巨大** — GHCR pull が重い。heavy を別 tag にし、簡単パスは core のみ pull させる(§3)。
2. **dev overlay の切替忘れ** — 開発者が dev overlay を使わず配布正本だけで起動すると、ソース変更が反映されず混乱。README / 本 doc で開発用コマンドを明示し、配布正本は image 固定である旨を周知。
3. **mock LLM 既定化の誤解** — 「本物の AI が動かない」と受け取られる。quickstart の URL 表示時に「デモ応答である / クラウド鍵 or `make ai` で本番 LLM」を明記。
4. **`HEMS_VERSION` pin と `latest` の整合** — release 運用と `:latest` の同時提供。pin 推奨を doc 化。
5. **GHCR 公開設定** — 初回は private 既定。public 化を忘れると外部 pull が 401。

---

## 6. スコープ外

- `services/mobile-android/` — scaffold のみ(QR 登録 API は `services/backend/routers/mobile.py` で稼働だがアプリ未完成)。配布対象外。
- SQLite→PostgreSQLのデータ移送は [`infra/scripts/migrate_sqlite_to_pg.py`](../infra/scripts/migrate_sqlite_to_pg.py) で対応。`--check` / `--dry-run` / `--execute` を使い、実行前に SQLite の自動バックアップを作成する。移送先schemaはBackend Alembic head適用後であること。
- `docs/lite/`(lite 版)— 別管理([`lite/refinement-plan.md`](lite/refinement-plan.md))。
