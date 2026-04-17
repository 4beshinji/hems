import { memo } from 'react'
import { Link } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Cpu, Mail, Heart, Footprints, Activity } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { fetchPC, fetchServices, fetchBiometric } from '@/lib/api'
import type { ServiceStatusItem } from '@/lib/types'

function MetricRow({
  to,
  icon: Icon,
  iconColor,
  label,
  value,
  sub,
}: {
  to: string
  icon: React.ComponentType<{ className?: string }>
  iconColor: string
  label: string
  value: string
  sub?: string
}) {
  return (
    <Link to={to} className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted/50 transition-colors">
      <Icon className={`h-3.5 w-3.5 shrink-0 ${iconColor}`} />
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-sm font-semibold text-foreground ml-auto">{value}</span>
      {sub && <span className="text-[10px] text-muted-foreground">{sub}</span>}
    </Link>
  )
}

const KeyMetricsSummary = memo(function KeyMetricsSummary() {
  const { data: pc } = useQuery({ queryKey: ['pc'], queryFn: fetchPC, refetchInterval: 10000 })
  const { data: services } = useQuery({ queryKey: ['services'], queryFn: fetchServices, refetchInterval: 10000 })
  const { data: bio } = useQuery({ queryKey: ['biometric'], queryFn: fetchBiometric, refetchInterval: 10000 })

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

  const hasData = cpuUsage != null || unreadCount > 0 || hr != null || steps != null

  if (!hasData) {
    return (
      <Card>
        <CardContent className="flex items-center gap-3 p-3">
          <Activity className="h-4 w-4 text-muted-foreground" />
          <p className="text-xs text-muted-foreground">データ接続待ち...</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardContent className="p-1">
        {cpuUsage != null && (
          <MetricRow
            to="/digital"
            icon={Cpu}
            iconColor="text-chart-blue"
            label="CPU"
            value={`${cpuUsage.toFixed(0)}%`}
            sub={unreadCount > 0 ? `${unreadCount}通` : undefined}
          />
        )}
        {unreadCount > 0 && cpuUsage == null && (
          <MetricRow
            to="/digital"
            icon={Mail}
            iconColor="text-chart-red"
            label="Gmail"
            value={`${unreadCount} 未読`}
          />
        )}
        {hr != null && (
          <MetricRow
            to="/user"
            icon={Heart}
            iconColor="text-chart-red"
            label="HR"
            value={`${hr} bpm`}
            sub={fatigue != null ? `疲労${fatigue}` : undefined}
          />
        )}
        {steps != null && (
          <MetricRow
            to="/user"
            icon={Footprints}
            iconColor="text-chart-green"
            label="歩数"
            value={steps.toLocaleString()}
          />
        )}
      </CardContent>
    </Card>
  )
})

export default KeyMetricsSummary
