import { apiFetch } from '@/lib/api-client'
import type { TimeSeriesPoint } from '@/lib/types'

export const fetchTimeSeries = (
  metric: string,
  zone?: string,
  hours: number = 24
): Promise<TimeSeriesPoint[]> => {
  const params = new URLSearchParams({ metric, hours: String(hours) })
  if (zone) params.set('zone', zone)
  return apiFetch(`/timeseries/?${params}`)
}
