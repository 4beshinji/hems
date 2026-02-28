import { useQuery } from '@tanstack/react-query'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts'
import { fetchTimeSeries } from '@/lib/api'

interface Props {
  metric: string
  zone?: string
  hours?: number
  label?: string
  color?: string
  unit?: string
  compact?: boolean
}

export default function TimeSeriesChart({
  metric,
  zone,
  hours = 24,
  label,
  color = '#6366f1',
  unit = '',
  compact = false,
}: Props) {
  const { data } = useQuery({
    queryKey: ['timeseries', metric, zone, hours],
    queryFn: () => fetchTimeSeries(metric, zone, hours),
    refetchInterval: 60000,
  })

  if (!data || data.length === 0) return null

  const chartData = data.map((p) => ({
    time: new Date(p.recorded_at).getTime(),
    value: p.value,
  }))

  const height = compact ? 60 : 200

  if (compact) {
    return (
      <div className="w-full" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData}>
            <Line
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    )
  }

  const formatTime = (ts: number) => {
    const d = new Date(ts)
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
  }

  return (
    <div>
      {label && <p className="text-xs text-muted-foreground mb-1">{label}</p>}
      <div style={{ width: '100%', height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis
              dataKey="time"
              type="number"
              domain={['dataMin', 'dataMax']}
              tickFormatter={formatTime}
              tick={{ fontSize: 10 }}
            />
            <YAxis tick={{ fontSize: 10 }} width={40} />
            <Tooltip
              labelFormatter={(v) => formatTime(v as number)}
              formatter={(v: number | undefined) => [`${(v ?? 0).toFixed(1)}${unit}`, label || metric]}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
