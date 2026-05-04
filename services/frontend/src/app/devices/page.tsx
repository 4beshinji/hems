import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Link } from 'react-router'
import { RefreshCw, Search, Layers, Zap, Radio, Home } from 'lucide-react'
import { Button } from '@/components/ui/button'
import LoadingState from '@/components/shared/LoadingState'
import ErrorState from '@/components/shared/ErrorState'
import ZoneEnvironmentCard from '@/components/physical/ZoneEnvironmentCard'
import LightCard from '@/components/physical/LightCard'
import ClimateCard from '@/components/physical/ClimateCard'
import CoverCard from '@/components/physical/CoverCard'
import EnergyPanel from '@/components/physical/EnergyPanel'
import PerceptionPanel from '@/components/physical/PerceptionPanel'
import DeviceTable from '@/components/devices/DeviceTable'
import DeviceEditModal from '@/components/devices/DeviceEditModal'
import { fetchZones, fetchHome, fetchDevices, zigbeePermitJoin } from '@/lib/api'
import type { Device, DeviceKind, DeviceVendor, HomeData } from '@/lib/types'
import { VENDOR_LABELS } from '@/components/devices/SensorCatalog'

type KindFilter = 'all' | DeviceKind

export default function DevicesPage() {
  /* ── Physical Space queries ────────────────────────────────────────── */
  const zonesQuery = useQuery({
    queryKey: ['zones'],
    queryFn: fetchZones,
    refetchInterval: 5000,
  })

  const homeQuery = useQuery<HomeData>({
    queryKey: ['home'],
    queryFn: fetchHome,
    refetchInterval: 5000,
  })

  const zones = zonesQuery.data ?? []
  const home = homeQuery.data
  const hasHome = home && home.status !== 'no_data' && home.bridge_connected
  const lights = hasHome && home.lights ? Object.entries(home.lights) : []
  const climates = hasHome && home.climates ? Object.entries(home.climates) : []
  const covers = hasHome && home.covers ? Object.entries(home.covers) : []
  const energySensors = hasHome && home.energy_sensors ? home.energy_sensors : {}
  const hasEnergy = Object.keys(energySensors).length > 0
  const hasSmartHome = lights.length > 0 || climates.length > 0 || covers.length > 0

  /* ── Devices query + state ─────────────────────────────────────────── */
  const [kindFilter, setKindFilter] = useState<KindFilter>('all')
  const [vendorFilter, setVendorFilter] = useState<DeviceVendor | 'all'>('all')
  const [search, setSearch] = useState('')
  const [editTarget, setEditTarget] = useState<Device | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [pairSecondsLeft, setPairSecondsLeft] = useState(0)
  const [pairBusy, setPairBusy] = useState(false)

  const devicesQuery = useQuery<Device[]>({
    queryKey: ['devices'],
    queryFn: () => fetchDevices(),
    refetchInterval: 5000,
  })

  const filtered = useMemo(() => {
    const list = devicesQuery.data ?? []
    return list.filter((d) => {
      if (kindFilter !== 'all' && d.kind !== kindFilter) return false
      if (vendorFilter !== 'all' && d.vendor !== vendorFilter) return false
      if (search) {
        const s = search.toLowerCase()
        const hay = [d.device_id, d.display_name, d.zone, d.location, d.purpose, d.notes, d.device_class]
          .filter(Boolean)
          .join(' ')
          .toLowerCase()
        if (!hay.includes(s)) return false
      }
      return true
    })
  }, [devicesQuery.data, kindFilter, vendorFilter, search])

  const summary = useMemo(() => {
    const list = devicesQuery.data ?? []
    const now = Date.now()
    let online = 0
    let offline = 0
    let lowBattery = 0
    for (const d of list) {
      if (!d.is_enabled) continue
      if (d.last_seen) {
        const age = now - new Date(d.last_seen).getTime()
        if (age < 5 * 60_000) online++
        else if (age > 30 * 60_000) offline++
      } else {
        offline++
      }
      if (typeof d.battery_pct === 'number' && d.battery_pct < 20) lowBattery++
    }
    return { total: list.length, online, offline, lowBattery }
  }, [devicesQuery.data])

  useEffect(() => {
    if (pairSecondsLeft <= 0) return
    const t = setTimeout(() => setPairSecondsLeft((s) => s - 1), 1000)
    return () => clearTimeout(t)
  }, [pairSecondsLeft])

  const handlePermitJoin = async (enable: boolean) => {
    setPairBusy(true)
    try {
      const duration = enable ? 120 : 0
      const res = await zigbeePermitJoin(enable, duration)
      if (res.success) {
        toast.success(enable ? `Zigbee ペアリング開始 (${duration}秒)` : 'Zigbee ペアリング終了')
        setPairSecondsLeft(enable ? duration : 0)
      } else {
        toast.error(res.error ?? 'permit_join 失敗')
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    } finally {
      setPairBusy(false)
    }
  }

  const handleToast = (msg: string, kind: 'success' | 'error') => {
    if (kind === 'success') toast.success(msg)
    else toast.error(msg)
  }

  if (zonesQuery.isLoading && devicesQuery.isLoading) return <LoadingState />
  if (zonesQuery.isError && devicesQuery.isError) return <ErrorState onRetry={() => { zonesQuery.refetch(); devicesQuery.refetch() }} />

  const vendors: DeviceVendor[] = ['zigbee', 'switchbot', 'tapo', 'ha', 'mcp', 'ir_via_hub']

  return (
    <div className="space-y-6">
      {/* ═══ Physical Space Summary ═══════════════════════════════════ */}

      {/* Zone Environment */}
      {zones.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-foreground mb-3">Environment</h2>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {zones.map((zone) => (
              <ZoneEnvironmentCard key={zone.zone_id} zone={zone} />
            ))}
          </div>
        </section>
      )}

      {/* Smart Home Controls */}
      {hasSmartHome && (
        <section>
          <h2 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
            <Home className="h-4 w-4 text-warning" />
            Smart Home
          </h2>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {lights.map(([id, light]) => (
              <LightCard key={id} entityId={id} light={light} />
            ))}
            {climates.map(([id, climate]) => (
              <ClimateCard key={id} entityId={id} climate={climate} />
            ))}
            {covers.map(([id, cover]) => (
              <CoverCard key={id} entityId={id} cover={cover} />
            ))}
          </div>
        </section>
      )}

      {/* Energy Dashboard */}
      {hasEnergy && (
        <section>
          <EnergyPanel sensors={energySensors} />
        </section>
      )}

      {/* Perception */}
      <section>
        <PerceptionPanel />
      </section>

      {/* ═══ Devices Registry ════════════════════════════════════════ */}

      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-foreground">Devices</h2>
            <p className="text-xs text-muted-foreground">
              用途と設置場所はLLMが参照します
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            <Button
              variant={pairSecondsLeft > 0 ? 'destructive' : 'outline'}
              size="sm"
              className="gap-1"
              disabled={pairBusy}
              onClick={() => handlePermitJoin(pairSecondsLeft <= 0)}
              title="Zigbee coordinator の新規ペアリングモードを開始/終了します"
            >
              <Radio className="h-3.5 w-3.5" />
              {pairSecondsLeft > 0 ? `ペアリング中 (${pairSecondsLeft}s)` : 'Zigbee ペアリング'}
            </Button>
            <Link to="/devices/scenes">
              <Button variant="outline" size="sm" className="gap-1">
                <Layers className="h-3.5 w-3.5" />
                シーン
              </Button>
            </Link>
            <Link to="/devices/automations">
              <Button variant="outline" size="sm" className="gap-1">
                <Zap className="h-3.5 w-3.5" />
                自動化
              </Button>
            </Link>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => devicesQuery.refetch()}
              aria-label="更新"
            >
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-3">
          <SummaryCard label="総数" value={summary.total} />
          <SummaryCard label="オンライン" value={summary.online} color="success" />
          <SummaryCard label="オフライン" value={summary.offline} color="destructive" />
          <SummaryCard label="低バッテリー" value={summary.lowBattery} color="warning" />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center rounded-md border border-input">
            {(['all', 'sensor', 'actuator', 'both'] as KindFilter[]).map((k) => (
              <button
                key={k}
                onClick={() => setKindFilter(k)}
                className={`px-3 py-1.5 text-xs font-medium first:rounded-l-md last:rounded-r-md ${
                  kindFilter === k
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-accent'
                }`}
              >
                {k === 'all' ? '全て' : k === 'sensor' ? 'センサー' : k === 'actuator' ? 'アクチュエータ' : '両方'}
              </button>
            ))}
          </div>
          <select
            value={vendorFilter}
            onChange={(e) => setVendorFilter(e.target.value as DeviceVendor | 'all')}
            className="h-8 rounded-md border border-input bg-background px-2 text-xs"
          >
            <option value="all">全ベンダー</option>
            {vendors.map((v) => (
              <option key={v} value={v}>
                {VENDOR_LABELS[v] ?? v}
              </option>
            ))}
          </select>
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="device_id / 用途 / ゾーンで検索..."
              className="w-full h-8 pl-7 pr-2 rounded-md border border-input bg-background text-xs"
            />
          </div>
        </div>

        <DeviceTable devices={filtered} onEdit={(d) => { setEditTarget(d); setModalOpen(true) }} onToast={handleToast} />

        <DeviceEditModal
          device={editTarget}
          open={modalOpen}
          onOpenChange={setModalOpen}
          onToast={handleToast}
        />
      </section>
    </div>
  )
}

function SummaryCard({
  label,
  value,
  color,
}: {
  label: string
  value: number
  color?: 'success' | 'destructive' | 'warning'
}) {
  const colorClass =
    color === 'success'
      ? 'text-success'
      : color === 'destructive'
      ? 'text-destructive'
      : color === 'warning'
      ? 'text-warning'
      : 'text-foreground'
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`text-2xl font-semibold ${colorClass}`}>{value}</div>
    </div>
  )
}
