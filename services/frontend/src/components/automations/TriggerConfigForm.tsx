import type { AutomationTriggerType, Device } from '@/lib/types'

interface Props {
  type: AutomationTriggerType
  config: Record<string, unknown>
  devices: Device[]
  onChange: (cfg: Record<string, unknown>) => void
}

const OPS = ['<', '>', '<=', '>=', '==', '!='] as const

export default function TriggerConfigForm({ type, config, devices, onChange }: Props) {
  const set = (patch: Record<string, unknown>) => onChange({ ...config, ...patch })

  if (type === 'sensor_threshold') {
    const sensorDevices = devices.filter((d) => d.kind === 'sensor' || d.kind === 'both')
    const selectedDevice = sensorDevices.find((d) => d.device_id === config.device_id)
    const channels = selectedDevice?.channels ?? []

    return (
      <div className="grid grid-cols-[1.5fr_1fr_auto_1fr_1fr] items-end gap-2">
        <FieldWrap label="センサーデバイス">
          <select
            value={(config.device_id as string) ?? ''}
            onChange={(e) => set({ device_id: e.target.value })}
            className="h-8 w-full rounded border border-input bg-background px-2 text-xs"
          >
            <option value="">センサー選択...</option>
            {sensorDevices.map((d) => (
              <option key={d.device_id} value={d.device_id}>
                {d.display_name || d.device_id}
              </option>
            ))}
          </select>
        </FieldWrap>
        <FieldWrap label="チャンネル">
          <select
            value={(config.channel as string) ?? ''}
            onChange={(e) => set({ channel: e.target.value })}
            className="h-8 w-full rounded border border-input bg-background px-2 text-xs"
          >
            <option value="">選択...</option>
            {channels.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </FieldWrap>
        <FieldWrap label="op">
          <select
            value={(config.op as string) ?? '<'}
            onChange={(e) => set({ op: e.target.value })}
            className="h-8 rounded border border-input bg-background px-1.5 text-xs"
          >
            {OPS.map((o) => (
              <option key={o} value={o}>{o}</option>
            ))}
          </select>
        </FieldWrap>
        <FieldWrap label="値">
          <input
            type="number"
            step="any"
            value={(config.value as number | undefined) ?? ''}
            onChange={(e) => set({ value: e.target.value ? Number(e.target.value) : null })}
            className="h-8 w-full rounded border border-input bg-background px-2 text-xs"
          />
        </FieldWrap>
        <FieldWrap label="継続秒数 (sustain_s)">
          <input
            type="number"
            min={0}
            value={(config.sustain_s as number | undefined) ?? 0}
            onChange={(e) => set({ sustain_s: Number(e.target.value) || 0 })}
            className="h-8 w-full rounded border border-input bg-background px-2 text-xs"
          />
        </FieldWrap>
      </div>
    )
  }

  if (type === 'schedule') {
    return (
      <div className="grid grid-cols-2 gap-2">
        <FieldWrap label="時刻 (HH:MM)">
          <input
            type="time"
            value={(config.time as string) ?? ''}
            onChange={(e) => set({ time: e.target.value, cron: undefined })}
            className="h-8 w-full rounded border border-input bg-background px-2 text-xs"
          />
        </FieldWrap>
        <FieldWrap label="または cron (M H * * *)">
          <input
            type="text"
            value={(config.cron as string) ?? ''}
            onChange={(e) => set({ cron: e.target.value, time: undefined })}
            placeholder="0 7 * * *"
            className="h-8 w-full rounded border border-input bg-background px-2 text-xs font-mono"
          />
        </FieldWrap>
      </div>
    )
  }

  if (type === 'event') {
    return (
      <FieldWrap label="イベント名">
        <select
          value={(config.event as string) ?? ''}
          onChange={(e) => set({ event: e.target.value })}
          className="h-8 w-full rounded border border-input bg-background px-2 text-xs"
        >
          <option value="">選択...</option>
          <option value="wake_up">wake_up (起床)</option>
          <option value="arrival">arrival (帰宅)</option>
          <option value="departure">departure (外出)</option>
        </select>
      </FieldWrap>
    )
  }

  if (type === 'device_state') {
    const actuators = devices.filter((d) => d.kind === 'actuator' || d.kind === 'both')
    return (
      <div className="grid grid-cols-3 gap-2">
        <FieldWrap label="デバイス">
          <select
            value={(config.device_id as string) ?? ''}
            onChange={(e) => set({ device_id: e.target.value })}
            className="h-8 w-full rounded border border-input bg-background px-2 text-xs"
          >
            <option value="">選択...</option>
            {actuators.map((d) => (
              <option key={d.device_id} value={d.device_id}>
                {d.display_name || d.device_id}
              </option>
            ))}
          </select>
        </FieldWrap>
        <FieldWrap label="state_key">
          <input
            type="text"
            value={(config.state_key as string) ?? 'on'}
            onChange={(e) => set({ state_key: e.target.value })}
            className="h-8 w-full rounded border border-input bg-background px-2 text-xs font-mono"
          />
        </FieldWrap>
        <FieldWrap label="equals">
          <select
            value={String(config.equals ?? 'true')}
            onChange={(e) => set({ equals: e.target.value === 'true' })}
            className="h-8 w-full rounded border border-input bg-background px-2 text-xs"
          >
            <option value="true">true</option>
            <option value="false">false</option>
          </select>
        </FieldWrap>
      </div>
    )
  }

  return null
}

function FieldWrap({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      {children}
    </div>
  )
}
