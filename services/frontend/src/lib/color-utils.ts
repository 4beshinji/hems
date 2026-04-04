/**
 * CO2 level classification.
 */
export function co2Level(ppm?: number | null): { label: string; color: string } {
  if (ppm == null) return { label: '', color: '' }
  if (ppm < 800) return { label: '良好', color: 'bg-success' }
  if (ppm < 1000) return { label: '普通', color: 'bg-warning' }
  if (ppm < 1500) return { label: '注意', color: 'bg-warning' }
  return { label: '危険', color: 'bg-destructive' }
}

/**
 * CO2 progress bar width (0–100 %).
 */
export function co2Width(ppm?: number | null): number {
  if (ppm == null) return 0
  return Math.min(100, (ppm / 2000) * 100)
}

/**
 * Temperature color class.
 */
export function tempColor(celsius: number): string {
  if (celsius < 18) return 'text-chart-blue'
  if (celsius < 26) return 'text-success'
  if (celsius < 30) return 'text-warning'
  return 'text-destructive'
}

/**
 * Heart rate zone thresholds and labels.
 */
export const hrZoneLabels: Record<string, string> = {
  rest: '安静',
  fat_burn: '脂肪燃焼',
  cardio: '有酸素',
  peak: 'ピーク',
}

export const hrZoneColors: Record<string, string> = {
  rest: 'text-chart-blue',
  fat_burn: 'text-chart-green',
  cardio: 'text-warning',
  peak: 'text-destructive',
}

/**
 * Stress category labels and colors.
 */
export const stressCategoryLabels: Record<string, string> = {
  low: '低',
  medium: '中',
  high: '高',
  very_high: '非常に高い',
}

export const stressCategoryColors: Record<string, string> = {
  low: 'text-success',
  medium: 'text-warning',
  high: 'text-destructive',
  very_high: 'text-destructive',
}

/**
 * Return true if an ISO datetime string is within the next 30 minutes.
 */
export function isEventSoon(isoString?: string | null): boolean {
  if (!isoString) return false
  const diff = new Date(isoString).getTime() - Date.now()
  return diff >= 0 && diff <= 30 * 60 * 1000
}

/**
 * Color class for activity level (0.0 – 1.0).
 */
export function activityColor(level?: number | null): string {
  if (level == null) return 'text-muted-foreground'
  if (level < 0.3) return 'text-muted-foreground'
  if (level < 0.6) return 'text-chart-green'
  if (level < 0.85) return 'text-warning'
  return 'text-destructive'
}
