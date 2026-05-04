import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Power, PowerOff, Zap, Sliders } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import { controlDevice } from '@/lib/api'
import type { Device, DeviceAction, DeviceControlRequest } from '@/lib/types'

interface Props {
  device: Device
  onToast?: (msg: string, kind: 'success' | 'error') => void
}

export default function DeviceControlButtons({ device, onToast }: Props) {
  const queryClient = useQueryClient()
  const [pulseSec, setPulseSec] = useState(30)
  const [brightness, setBrightness] = useState(
    (device.last_state?.brightness as number | undefined) ?? 128,
  )

  const caps = device.capabilities ?? []
  const hasOnOff = caps.includes('on_off')
  const hasBrightness = caps.includes('brightness')
  const hasPulse = caps.includes('pulse')

  const onState = Boolean(device.last_state?.on)

  const mutation = useMutation({
    mutationFn: async (payload: DeviceControlRequest) => {
      return controlDevice(device.device_id, payload)
    },
    onSuccess: (result) => {
      if (result.success) {
        onToast?.(result.result ?? '実行しました', 'success')
        queryClient.invalidateQueries({ queryKey: ['devices'] })
      } else {
        onToast?.(result.error ?? '失敗', 'error')
      }
    },
    onError: (err) => {
      onToast?.(err instanceof Error ? err.message : 'エラー', 'error')
    },
  })

  const act = (action: DeviceAction, params?: Record<string, unknown>) => {
    mutation.mutate({ action, params })
  }

  if (device.kind === 'sensor') return null

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {hasOnOff && (
        <>
          <Button
            variant={onState ? 'default' : 'outline'}
            size="sm"
            onClick={() => act('on')}
            disabled={mutation.isPending}
            className="h-7 gap-1 px-2 text-xs"
          >
            <Power className="h-3 w-3" />
            ON
          </Button>
          <Button
            variant={!onState ? 'default' : 'outline'}
            size="sm"
            onClick={() => act('off')}
            disabled={mutation.isPending}
            className="h-7 gap-1 px-2 text-xs"
          >
            <PowerOff className="h-3 w-3" />
            OFF
          </Button>
        </>
      )}
      {hasBrightness && (
        <div className="flex items-center gap-1.5 min-w-[140px]">
          <Sliders className="h-3 w-3 text-muted-foreground" />
          <Slider
            value={brightness}
            onValueChange={(v) => setBrightness(v)}
            onValueCommit={(v) => act('set_brightness', { value: v })}
            min={0}
            max={255}
            step={1}
            className="flex-1"
          />
          <span className="text-xs text-muted-foreground w-8 text-right">
            {brightness}
          </span>
        </div>
      )}
      {hasPulse && (
        <div className="flex items-center gap-1">
          <input
            type="number"
            min={1}
            max={600}
            value={pulseSec}
            onChange={(e) => setPulseSec(Math.max(1, Math.min(600, Number(e.target.value) || 0)))}
            className="w-14 h-7 px-1.5 text-xs rounded border border-input bg-background"
            aria-label="pulse秒数"
          />
          <Button
            variant="outline"
            size="sm"
            onClick={() => act('pulse', { duration_s: pulseSec })}
            disabled={mutation.isPending}
            className="h-7 gap-1 px-2 text-xs"
          >
            <Zap className="h-3 w-3" />
            Pulse
          </Button>
        </div>
      )}
    </div>
  )
}
