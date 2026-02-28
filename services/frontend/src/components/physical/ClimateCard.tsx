import { memo } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Thermometer } from 'lucide-react'
import { toast } from 'sonner'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { controlClimate } from '@/lib/api'
import { entityLabel } from '@/lib/formatters'
import { CLIMATE_MODES } from '@/lib/constants'
import { cn } from '@/lib/utils'
import type { HomeClimate } from '@/lib/types'

interface Props {
  entityId: string
  climate: HomeClimate
}

const ClimateCard = memo(function ClimateCard({ entityId, climate }: Props) {
  const queryClient = useQueryClient()

  const modeMut = useMutation({
    mutationFn: (mode: string) => controlClimate(entityId, mode, climate.target_temp),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['home'] }),
    onError: () => toast.error('空調モードの変更に失敗しました'),
  })

  const tempMut = useMutation({
    mutationFn: (temp: number) => controlClimate(entityId, climate.mode, temp),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['home'] }),
    onError: () => toast.error('温度の変更に失敗しました'),
  })

  const isOn = climate.mode !== 'off'

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm font-medium text-foreground">
            <Thermometer className={`h-4 w-4 ${isOn ? 'text-chart-blue' : 'text-muted-foreground'}`} />
            {entityLabel(entityId)}
          </span>
          <span className="text-xs text-muted-foreground">
            現在 {climate.current_temp}°C
          </span>
        </div>
        <div className="flex gap-1">
          {CLIMATE_MODES.map((m) => (
            <Button
              key={m}
              variant={climate.mode === m ? 'default' : 'outline'}
              size="sm"
              className="flex-1 text-xs"
              onClick={() => modeMut.mutate(m)}
              disabled={modeMut.isPending}
            >
              {m}
            </Button>
          ))}
        </div>
        {isOn && (
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8"
              onClick={() => tempMut.mutate(climate.target_temp - 1)}
              disabled={tempMut.isPending || climate.target_temp <= 16}
            >
              -
            </Button>
            <span className={cn('text-lg font-bold flex-1 text-center', isOn && 'text-chart-blue')}>
              {climate.target_temp}°C
            </span>
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8"
              onClick={() => tempMut.mutate(climate.target_temp + 1)}
              disabled={tempMut.isPending || climate.target_temp >= 30}
            >
              +
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
})

export default ClimateCard
