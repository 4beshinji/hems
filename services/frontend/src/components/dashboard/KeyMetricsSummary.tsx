import { memo } from 'react'
import { Link } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Thermometer, Wind, Cpu, Mail, Heart, Footprints, Activity } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { fetchZones, fetchPC, fetchServices, fetchBiometric } from '@/lib/api'
import { co2Level } from '@/lib/color-utils'
import type { ServiceStatusItem } from '@/lib/types'

function MetricCard({
  to,
  icon: Icon,
  iconColor,
  label,
  value,
  sub,
}: {
  to: string
  icon: React.ElementType
  iconColor: string
  label: string
  value: string
  sub?: string
}) {
  return (
    <Link to={to}>
      <Card className="hover:shadow-md transition-shadow cursor-pointer">
        <CardContent className="flex items-center gap-3 p-4">
          <div className={`shrink-0 rounded-lg p-2 ${iconColor}`}>
            <Icon className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className="text-lg font-bold text-foreground">{value}</p>
            {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}

const KeyMetricsSummary = memo(function KeyMetricsSummary() {
  const { data: zones } = useQuery({ queryKey: ['zones'], queryFn: fetchZones, refetchInterval: 10000 })
  const { data: pc } = useQuery({ queryKey: ['pc'], queryFn: fetchPC, refetchInterval: 10000 })
  const { data: services } = useQuery({ queryKey: ['services'], queryFn: fetchServices, refetchInterval: 10000 })
  const { data: bio } = useQuery({ queryKey: ['biometric'], queryFn: fetchBiometric, refetchInterval: 10000 })

  const primaryZone = zones?.[0]
  const temp = primaryZone?.environment?.temperature
  const co2 = primaryZone?.environment?.co2
  const cpuUsage = pc?.cpu?.usage_percent

  // Gmail unread from services
  const serviceItems = services
    ? Object.values(services).filter((v): v is ServiceStatusItem => typeof v === 'object' && v !== null && 'name' in v)
    : []
  const gmail = serviceItems.find((s) => s.name === 'gmail')
  const unreadCount = gmail?.unread_count ?? 0

  const hr = bio?.heart_rate?.bpm
  const fatigue = bio?.fatigue?.score
  const steps = bio?.activity?.steps

  return (
    <div className="grid gap-3 grid-cols-2 lg:grid-cols-1">
      {temp != null && (
        <MetricCard
          to="/physical"
          icon={Thermometer}
          iconColor="bg-chart-red/15 text-chart-red"
          label="温度"
          value={`${temp.toFixed(1)}°C`}
          sub={co2 != null ? `CO2 ${Math.round(co2)}ppm ${co2Level(co2).label}` : undefined}
        />
      )}
      {co2 != null && temp == null && (
        <MetricCard
          to="/physical"
          icon={Wind}
          iconColor="bg-muted text-muted-foreground"
          label="CO2"
          value={`${Math.round(co2)}ppm`}
          sub={co2Level(co2).label}
        />
      )}
      {cpuUsage != null && (
        <MetricCard
          to="/digital"
          icon={Cpu}
          iconColor="bg-chart-blue/15 text-chart-blue"
          label="CPU"
          value={`${cpuUsage.toFixed(0)}%`}
          sub={unreadCount > 0 ? `Gmail ${unreadCount} 未読` : undefined}
        />
      )}
      {unreadCount > 0 && cpuUsage == null && (
        <MetricCard
          to="/digital"
          icon={Mail}
          iconColor="bg-chart-red/15 text-chart-red"
          label="Gmail"
          value={`${unreadCount} 未読`}
        />
      )}
      {hr != null && (
        <MetricCard
          to="/user"
          icon={Heart}
          iconColor="bg-chart-red/15 text-chart-red"
          label="心拍数"
          value={`${hr} bpm`}
          sub={fatigue != null ? `疲労度 ${fatigue}` : undefined}
        />
      )}
      {steps != null && (
        <MetricCard
          to="/user"
          icon={Footprints}
          iconColor="bg-chart-green/15 text-chart-green"
          label="歩数"
          value={steps.toLocaleString()}
        />
      )}
      {/* Fallback when no data available */}
      {!temp && !cpuUsage && !hr && !steps && unreadCount === 0 && (
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <Activity className="h-5 w-5 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">データ接続待ち...</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
})

export default KeyMetricsSummary
