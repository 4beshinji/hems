import { Trash2, ArrowDown, ArrowUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { Device, DeviceAction, SceneAction } from '@/lib/types'

interface Props {
  index: number
  action: SceneAction
  devices: Device[]
  isFirst: boolean
  isLast: boolean
  onChange: (patch: Partial<SceneAction>) => void
  onMoveUp: () => void
  onMoveDown: () => void
  onRemove: () => void
}

const ACTIONS: DeviceAction[] = [
  'on', 'off', 'toggle', 'set_brightness', 'set_color_temp',
  'set_position', 'set_temperature', 'pulse', 'ir_send',
]

export default function ActionRow({
  index, action, devices, isFirst, isLast,
  onChange, onMoveUp, onMoveDown, onRemove,
}: Props) {
  const needsValue = ['set_brightness', 'set_color_temp', 'set_position', 'set_temperature'].includes(action.action)
  const needsDuration = action.action === 'pulse'
  const needsIrCommand = action.action === 'ir_send'

  const setParam = (key: string, val: unknown) => {
    const params = { ...(action.params ?? {}) }
    if (val === '' || val === undefined || val === null) delete params[key]
    else params[key] = val
    onChange({ params })
  }

  return (
    <div className="grid grid-cols-[auto_1.5fr_1fr_1fr_auto_auto] items-center gap-2 rounded-md border border-border bg-card/50 px-2 py-1.5">
      <span className="text-xs text-muted-foreground font-mono w-6 text-center">
        {index + 1}.
      </span>

      <select
        value={action.device_id}
        onChange={(e) => onChange({ device_id: e.target.value })}
        className="h-8 rounded border border-input bg-background px-1.5 text-xs"
      >
        <option value="">デバイス選択...</option>
        {devices.map((d) => (
          <option key={d.device_id} value={d.device_id}>
            {d.display_name || d.device_id} ({d.zone || 'unknown'})
          </option>
        ))}
      </select>

      <select
        value={action.action}
        onChange={(e) => onChange({ action: e.target.value as DeviceAction })}
        className="h-8 rounded border border-input bg-background px-1.5 text-xs"
      >
        {ACTIONS.map((a) => (
          <option key={a} value={a}>{a}</option>
        ))}
      </select>

      <div className="flex items-center gap-1">
        {needsValue && (
          <input
            type="number"
            value={(action.params?.value as number | undefined) ?? ''}
            onChange={(e) => setParam('value', e.target.value ? Number(e.target.value) : undefined)}
            placeholder="value"
            className="h-8 w-20 rounded border border-input bg-background px-1.5 text-xs"
          />
        )}
        {needsDuration && (
          <input
            type="number"
            value={(action.params?.duration_s as number | undefined) ?? ''}
            onChange={(e) => setParam('duration_s', e.target.value ? Number(e.target.value) : undefined)}
            placeholder="秒"
            min={1}
            max={600}
            className="h-8 w-20 rounded border border-input bg-background px-1.5 text-xs"
          />
        )}
        {needsIrCommand && (
          <input
            type="text"
            value={(action.params?.command as string | undefined) ?? ''}
            onChange={(e) => setParam('command', e.target.value || undefined)}
            placeholder="IR cmd"
            className="h-8 w-24 rounded border border-input bg-background px-1.5 text-xs"
          />
        )}
        <input
          type="number"
          value={action.delay_s ?? 0}
          onChange={(e) => onChange({ delay_s: Number(e.target.value) || 0 })}
          placeholder="+秒"
          min={0}
          className="h-8 w-16 rounded border border-input bg-background px-1.5 text-xs"
          title="delay_s — シーン開始からの遅延秒数"
        />
      </div>

      <div className="flex items-center gap-0.5">
        <Button
          variant="ghost"
          size="icon"
          disabled={isFirst}
          onClick={onMoveUp}
          aria-label="上へ"
          className="h-6 w-6"
        >
          <ArrowUp className="h-3 w-3" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          disabled={isLast}
          onClick={onMoveDown}
          aria-label="下へ"
          className="h-6 w-6"
        >
          <ArrowDown className="h-3 w-3" />
        </Button>
      </div>

      <Button
        variant="ghost"
        size="icon"
        onClick={onRemove}
        className="h-6 w-6 text-destructive"
        aria-label="削除"
      >
        <Trash2 className="h-3 w-3" />
      </Button>
    </div>
  )
}
