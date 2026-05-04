import { useMemo } from 'react'
import { Pencil, CircleDot, CircleOff, BatteryLow } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { formatAge } from '@/lib/formatters'
import type { Device } from '@/lib/types'
import { CHANNEL_UNITS, KIND_LABELS, VENDOR_LABELS, lookupCatalog } from './SensorCatalog'
import DeviceControlButtons from './DeviceControlButtons'

interface Props {
  devices: Device[]
  onEdit: (device: Device) => void
  onToast?: (msg: string, kind: 'success' | 'error') => void
}

function deviceStatus(device: Device): 'online' | 'stale' | 'offline' | 'unknown' {
  if (!device.last_seen) return 'unknown'
  const ageMs = Date.now() - new Date(device.last_seen).getTime()
  if (ageMs < 5 * 60_000) return 'online'
  if (ageMs < 30 * 60_000) return 'stale'
  return 'offline'
}

const STATUS_COLOR: Record<string, string> = {
  online: 'text-success',
  stale: 'text-warning',
  offline: 'text-destructive',
  unknown: 'text-muted-foreground',
}

function renderSensorValue(device: Device): string {
  const last = device.last_value as Record<string, number | string>
  if (!last || Object.keys(last).length === 0) return '—'
  const parts: string[] = []
  for (const key of Object.keys(last).slice(0, 3)) {
    const v = last[key]
    const unit = CHANNEL_UNITS[key] ?? ''
    if (typeof v === 'number') {
      parts.push(`${key}: ${v}${unit}`)
    } else if (v !== undefined && v !== null) {
      parts.push(`${key}: ${v}`)
    }
  }
  return parts.join(' / ')
}

function renderActuatorState(device: Device): string {
  const st = device.last_state as Record<string, unknown>
  if (!st || Object.keys(st).length === 0) return '—'
  const parts: string[] = []
  if (typeof st.on === 'boolean') parts.push(st.on ? 'ON' : 'OFF')
  if (typeof st.brightness === 'number') parts.push(`明:${st.brightness}`)
  if (typeof st.position === 'number') parts.push(`pos:${st.position}`)
  return parts.join(' / ') || '—'
}

export default function DeviceTable({ devices, onEdit, onToast }: Props) {
  const grouped = useMemo(() => {
    const map = new Map<string, Device[]>()
    for (const d of devices) {
      const zone = d.zone || '未分類'
      const list = map.get(zone) ?? []
      list.push(d)
      map.set(zone, list)
    }
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b))
  }, [devices])

  if (devices.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
        デバイスが登録されていません。<br />
        Brainが起動するとMQTTで観測されたデバイスが自動登録されます。
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {grouped.map(([zone, list]) => (
        <div key={zone} className="space-y-2">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            {zone}
            <span className="ml-2 font-normal normal-case">({list.length})</span>
          </h3>
          <div className="rounded-lg border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/40 text-xs text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left font-medium w-8"></th>
                  <th className="px-3 py-2 text-left font-medium">デバイス</th>
                  <th className="px-3 py-2 text-left font-medium">種別</th>
                  <th className="px-3 py-2 text-left font-medium">現在値 / 状態</th>
                  <th className="px-3 py-2 text-left font-medium">最終観測</th>
                  <th className="px-3 py-2 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {list.map((device) => {
                  const status = deviceStatus(device)
                  const catalog = lookupCatalog(device.device_class)
                  const lowBattery =
                    typeof device.battery_pct === 'number' && device.battery_pct < 20
                  return (
                    <tr
                      key={device.device_id}
                      className={cn(
                        'border-t border-border',
                        !device.is_enabled && 'opacity-50',
                      )}
                    >
                      <td className="px-3 py-2">
                        {status === 'online' ? (
                          <CircleDot className={cn('h-4 w-4', STATUS_COLOR[status])} />
                        ) : (
                          <CircleOff className={cn('h-4 w-4', STATUS_COLOR[status])} />
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-2">
                          <div>
                            <div className="font-medium">
                              {device.display_name || device.device_id.split('.').slice(1).join('.')}
                            </div>
                            <div className="text-xs text-muted-foreground font-mono">
                              {device.device_id}
                            </div>
                            {device.purpose && (
                              <div className="text-xs text-muted-foreground italic">
                                {device.purpose}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-3 py-2 text-xs">
                        <div className="flex flex-col gap-1">
                          <Badge variant="outline" className="w-fit">
                            {catalog?.label || device.device_class || KIND_LABELS[device.kind]}
                          </Badge>
                          <span className="text-muted-foreground">
                            {VENDOR_LABELS[device.vendor] ?? device.vendor}
                          </span>
                        </div>
                      </td>
                      <td className="px-3 py-2 text-xs">
                        {device.kind === 'sensor' || device.kind === 'both' ? (
                          <div>{renderSensorValue(device)}</div>
                        ) : null}
                        {device.kind === 'actuator' || device.kind === 'both' ? (
                          <div className="text-muted-foreground">
                            {renderActuatorState(device)}
                          </div>
                        ) : null}
                        {lowBattery && (
                          <div className="flex items-center gap-1 text-destructive mt-0.5">
                            <BatteryLow className="h-3 w-3" />
                            {device.battery_pct}%
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-2 text-xs text-muted-foreground">
                        {device.last_seen ? formatAge(device.last_seen) : '—'}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center justify-end gap-2">
                          <DeviceControlButtons device={device} onToast={onToast} />
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => onEdit(device)}
                            className="h-7 w-7"
                            aria-label="編集"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  )
}
