# Home Assistant — 運用隔離ガイド

## なぜこのガイドが必要か

HEMS の `ha` プロファイルは Home Assistant を Docker コンテナ内で動かすため、
以下のような **ホスト全体に影響する権限** を必要とする:

```yaml
privileged: true
network_mode: host
volumes:
  - /run/dbus:/run/dbus:ro
```

Matter-Server や Zigbee のような USB パススルーと Bluetooth/mDNS のホスト共有には
`network_mode: host` が必須であるため、これらの設定を完全に回避することはできない。

**リスク**: Matter-Server や HA のコンポーネントに脆弱性が発見された場合、
コンテナ脱出からホスト侵害に直結する。

---

## 推奨: HA を別ホスト / VLAN に隔離する

### 構成例 A — HA を別ホスト (Raspberry Pi 等) で動かす

```
[HEMS host]  ←HTTP/WS→  [HA host (192.168.1.x)]
  ha-bridge                Home Assistant OS
```

- HA 側で長期アクセストークンを発行し、`HA_TOKEN` に設定する
- `ha-bridge` は `privileged: true` / `network_mode: host` 不要になる
- HA ホストは HEMS 以外のネットワークアクセスを制限可能

### 構成例 B — 専用 VLAN / サブネット分離

```
VLAN 10: HEMS (192.168.10.0/24)
VLAN 20: IoT / HA (192.168.20.0/24)

HEMS host → ha-bridge → HA (192.168.20.x:8123)
            (firewall: HEMS → HA のみ許可)
```

---

## どうしても同一ホストで動かす場合のチェックリスト

- [ ] HA を最新バージョンに常時アップデートする (`watchdog` 自動更新 ON)
- [ ] Matter-Server / Bluetooth 統合が不要であれば `network_mode: host` を削除し
      `network_mode: bridge` に戻す (ポートマッピングで代替)
- [ ] `/run/dbus` は Bluetooth 統合が不要なら外す
- [ ] HA の UI ポート (8123) を LAN 外に公開しない (リバースプロキシ + TLS + 認証推奨)
- [ ] `privileged: true` が本当に必要かを HA リリースノートで毎回確認する

---

## HEMS における `ha` プロファイルのデフォルト off について

`ha` プロファイルはデフォルトで無効 (`profiles: ["ha"]`) であるため、
`docker compose up -d` だけでは起動しない。
明示的に `--profile ha` を指定した場合のみ起動する。

HA を利用する場合は本ガイドを読んだうえで運用方針を決定すること。

---

## 参考

- [Home Assistant — Running in Docker](https://www.home-assistant.io/installation/linux#install-home-assistant-container)
- [Matter-Server — Architecture](https://github.com/home-assistant-libs/python-matter-server)
- CVE 情報: `https://www.home-assistant.io/changelogs/` の Security セクションを参照
