/**
 * Format an ISO datetime string or Unix timestamp as HH:mm (Japan locale).
 */
export function formatTime(value?: string | number | null): string {
  if (value == null || value === '') return ''
  try {
    const d = typeof value === 'number' ? new Date(value * 1000) : new Date(value)
    return d.toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

/**
 * Return a human-readable "age" for an ISO datetime or Unix timestamp (e.g. "3分前").
 */
export function formatAge(value?: string | number | null): string {
  if (value == null || value === '') return ''
  try {
    const ts = typeof value === 'number' ? value * 1000 : new Date(value).getTime()
    const diff = Date.now() - ts
    const minutes = Math.floor(diff / 60_000)
    if (minutes < 1) return 'たった今'
    if (minutes < 60) return `${minutes}分前`
    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `${hours}時間前`
    return `${Math.floor(hours / 24)}日前`
  } catch {
    return ''
  }
}

/**
 * Format sleep duration in minutes to a readable string (e.g. "7時間30分").
 */
export function formatSleepDuration(minutes?: number | null): string {
  if (minutes == null) return '-'
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  if (m === 0) return `${h}時間`
  return `${h}時間${m}分`
}

/**
 * Format duration in minutes to a readable string (e.g. "1時間30分" or "45分").
 */
export function formatDuration(minutes?: number | null): string {
  if (minutes == null) return '-'
  if (minutes < 60) return `${minutes}分`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m === 0 ? `${h}時間` : `${h}時間${m}分`
}

/**
 * Convert an HA entity_id like "light.living_room_ceiling" to a readable label.
 */
export function entityLabel(entityId: string): string {
  return entityId.replace(/^[^.]+\./, '').replace(/_/g, ' ')
}
