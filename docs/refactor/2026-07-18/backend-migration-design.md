# P0.3 Backend versioned migration design

調査日: 2026-07-18  
対象: `services/backend` の `public` schemaのみ。コード変更はこのnoteの対象外。

## 決定

Backendには **Alembicを採用**し、起動前に`upgrade head`を実行して失敗時はAPI processを開始しない。
独自revision runnerは採用しない。最初のrevisionだけは既存のunversioned DBを安全に取り込むための
schema introspectionを持たせ、それ以後は通常の決定的なAlembic revisionとする。

Brainのevent store (`events` schema) は今回のmigration対象に含めない。BackendとBrainはComposeでは同じ
`DATABASE_URL`を共有するが、所有schemaとDDL実装が異なる。Backend Alembicが`events.*`を作成・stamp・変更しては
ならない。Brain側の手製DDL/ALTERのversioningは独立rowで行う。

## 現状の証拠と問題

- `services/backend/main.py::lifespan` は最初に`Base.metadata.create_all`を実行し、その後20個の列追加を
  `_add_column_if_missing`で1列1 transactionとして実行する。DDL失敗はwarningで継続するため、APIは不完全な
  schemaでもreadyになり得る。
- 20列は `voice_events.motion_id`、`tasks`の10列、`shopping_items.store_category`、`devices`の4列、
  `automation_rules`の4列である。特に`deadline` / `dismissed_at` / `locked_start` /
  `last_seen_reported`には生SQL型`DATETIME`を使っている。SQLiteでは通るがPostgreSQLの型ではないため、
  既存PostgreSQL DBへの追加は失敗し得る（fresh DBはORMの`create_all`で列が作られるので表面化しない）。
- `services/backend/models.py`には現在30個の`Base` modelがある。`create_all`は新規tableを作れても既存tableの
  column/type/index/constraintを更新しない。
- `services/backend/database.py`の既定は`postgresql+asyncpg`、ComposeのbackendはhealthyなPostgreSQLを待つ。
  SQLite-lite overrideはbackend/brainを別volume上の`/app/data/hems.db`へ向け、PostgreSQLをdisabled profileへ移す。
- Backend imageの現行CMDは直接`uvicorn main:app`であり、migration専用entrypointはない。
- `.github/workflows/ci.yml::test-backend`にはPostgreSQL serviceがなく、現行testは実質SQLite gateである。
- `infra/scripts/migrate_sqlite_to_pg.py`はDB製品間の**データ移送**であり、application schema revision runnerではない。
  `_BACKEND_TABLE_ORDER`も現行30 modelのうちapproval/feedback/adaptive-threshold系を含まず、将来schema migrationの
  SoTとして再利用してはいけない。
- Brain `event_store.database::init_db`は`events` schema（SQLite時はBrain専用file）をraw DDLと追加ALTERで管理する。
  PostgreSQL分岐には例外を丸ごと無視する箇所もあるが、P0.3で同時修正すると所有境界とrollback範囲が広がる。

## Alembicとcustom runnerの比較

| 観点 | Alembic | custom revision table/runner |
|---|---|---|
| PostgreSQL/SQLite | SQLAlchemy dialectと`batch_alter_table`を利用可能 | 型・DDL差分を毎回自前分岐 |
| version/head検証 | revision graph、current/head、複数head検出が既成 | 線形ID、整合性、checksumを自作 |
| fail-fast/transaction | 標準commandの非zero終了、revision transaction | 実装可能だがエラー分類とtransaction境界を自作 |
| autogenerate/check | metadata差分をレビュー用に利用可能 | なし |
| downgrade/offline SQL | 標準機能あり | 自作 |
| 初期変更量 | config、env、2 initial revisions、依存追加 | runner自体は小さい |
| 長期負債 | 一般的な運用知識に寄せられる | HEMS固有frameworkを保守 |

旧計画`docs/db-improvement-plan.md` §6はPhase 0の最小依存を理由にcustom runnerを推奨している。しかし現在は
PostgreSQLが既定で、modelが30まで増え、型・FK・indexを両dialectで扱う必要がある。短期の行数差より、独自migration
frameworkを増やさないことを優先する。

## 初回導入とlegacy baseline

revision chainは次の2本から開始する。

1. `0001_backend_baseline`: 現行30 tableのうち20追加列を除いたschemaを、**revision内に固定した明示DDL**で表す。
   fresh DBでは全tableを作る。unversioned DBではinspectorでtable/columnの存在と互換型を確認し、存在しないtableだけを
   FK順に作る。既存tableにbaseline必須列が欠ける、または型が非互換なら推測修復せず失敗する。liveな
   `Base.metadata.create_all`をrevisionから呼ばない（将来model変更で過去revisionが変質するため）。
2. `0002_legacy_additive_columns`: 現行手製listの20列をSQLAlchemy型で追加する。既存列は型/nullable互換を確認してskipし、
   欠落列だけを追加する。日時4列は`DateTime(timezone=True)`を使い、PostgreSQLではTIMESTAMPTZ、SQLiteでは互換な
   DateTimeとして生成する。全列は既存rowを壊さないnullable追加とする。

bootstrap wrapperは`alembic_version`がない場合だけ次のfingerprintを取る。

- Backend tableが0件: `upgrade head`（0001→0002）を実行する。
- 30 tableとhead必須columnが全て存在し、互換型である: 既存データ件数を変更せず`stamp 0002`する。これが現在の
  `create_all + 20列` DBのbaseline stampingである。
- table/20列が部分的: baseから`upgrade head`する。0001/0002の存在checkにより欠落だけを加算する。
- 未知tableは保持する。既知tableの不整合、複数head、version tableの未知revisionはfatalとし、自動stampしない。

stamp前後でtable/column fingerprintと各table row countをlogする。revision適用とstampはいずれも同一DB内で行い、
SQLite fileは事前copy、PostgreSQLは運用backupをrelease手順の必須条件とする。revision fileを適用済み後に編集しない。

## 起動方式とfail-fast

- `alembic`を`services/backend/requirements.txt`にpin範囲付きで追加し、async templateの`env.py`から
  `DATABASE_URL`を読む。secretを含むURLはlogしない。
- Backend containerに小さなentrypointを置き、`alembic upgrade head`成功後にのみ`exec uvicorn ...`する。
  ComposeのPostgreSQL health dependencyは維持する。migration失敗時はentrypointが非zeroで終了し、health endpointを
  公開しない。`restart: always`による再試行はあり得るため、同じfatal errorを明瞭にlogする。
- `main.py::lifespan`から`create_all`、20列loop、`_add_column_if_missing`を削除する。migration後のruntimeでDDLを混在
  させない。ローカル起動手順も`alembic upgrade head`を先行させる。
- 複数replicaへ拡張するまでは単一backend containerが前提。将来replica化する場合はrelease jobでmigrationを一度だけ
  実行し、各web processからmigrationを外す。

## 段階実装

1. Alembic config/async env、bootstrap command、0001/0002 revisionを追加する。revisionに現在のschemaを固定し、生成後に
   autogenerate差分を人手レビューする。
2. fresh/完全legacy/部分legacyのSQLite testsを追加する。特に4 datetime列と残り16列、二度実行、row保持を確認する。
3. CIに隔離したPostgreSQL migration jobを追加し、同じfixtureを実DBで検証する。
4. container entrypointをmigration-firstへ切り替える。その後にlifespanのruntime DDLを削除する（同一commit内で切替え、
   DDL経路がゼロまたは二重になる中間状態を残さない）。
5. docsとplan/ledgerを同期し、SQLite→PostgreSQLデータ移送scriptはschemaがheadになった後にのみ実行するよう更新する。

## Test gate

- SQLite fresh: 空file→head、30 table、`alembic current=head`、二度目no-op。
- SQLite legacy: baseline fixtureへsentinel rowを入れ、完全20列DBはstampのみ、部分DBは欠落列のみ追加、row/PK/FKを保持。
- PostgreSQL fresh/legacy: GitHub Actions service containerで同じ検査を行う。`public`だけが変化し、`events` schemaのtable数・
  fingerprintが不変であることもassertする。
- Failure: 非互換型、未知revision、意図的に失敗するrevisionでcommand非zeroかつUvicorn未起動を確認する。
- Drift: `alembic check`（またはMigrationContext compare）でmodel metadataとhead schemaに未生成差分がないことをCI gateにする。
- 通常gate: `make lint`と全non-integration pytest。migration testはsubprocess/一時DBでmodule import時のglobal engineと隔離する。

## Rollback方針

P0.3のschema変更は既存20列の加算とversion table追加だけで、runtimeの旧版とも後方互換にする。deploy rollbackは旧imageへ
戻し、DBはheadのままforward-fixする。初期revisionの`downgrade base`で30 tableをdropする実装は置かず、明示的に拒否する。
将来revisionのdowngradeは安全に可逆なDDLだけ実装し、data lossを伴うdrop/type縮小はbackup restoreまたはforward migrationを
runbookにする。PostgreSQL DDL transaction失敗はそのrevisionをrollbackする。SQLiteはDDL制約があるためmigration前file copyを
自動作成し、失敗時はprocess停止後にfileを戻す。

## Doc sync

実装完了時に、参照したplanning docsを次の順で同期する。

1. `docs/refactor/2026-07-18/PLAN.md` P0.3と`LEDGER.md`をDone/commit/test結果へ更新。
2. `docs/IMPLEMENTATION_MAP.md`へBackend revision owner、起動順、Brain `events`非対象を記載。
3. `services/backend/CLAUDE.md`、root `CLAUDE.md`へmigration commandとfail-fast運用を記載。
4. `docs/db-improvement-plan.md` §6のcustom runner推奨をAlembic実装済みへ訂正し、§7 Brain課題は未対応のまま分離。
5. `docs/distribution.md` / README quickstartへ自動migration、backup、rollback注意を追記。
6. schema/interface変更として`CHANGELOG.md`へupgrade noteを追加する。

## 実装時に先に確認する点

- 30 model全体のrevisionを固定する前に、現在のmodelと実運用PostgreSQL/SQLite schema dumpを比較する。ここで列型やconstraintの
  既存差が見つかった場合は0001で黙って矯正せず、対応する明示revisionまたは運用手順を追加する。
- `infra/scripts/migrate_sqlite_to_pg.py::_BACKEND_TABLE_ORDER`が現行model集合より古い点は別修正として扱う。P0.3に混ぜる場合も
  migration revisionを参照してDDL生成してはならず、データ移送table順だけを更新する。
- Alembicの具体versionでSQLite batch mode、`Uuid`、asyncpg URLがCIと同じPython 3.11で動くことをfocused spikeで確認してから
  dependency versionを確定する。
