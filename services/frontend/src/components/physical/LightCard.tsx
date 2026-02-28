import { useState, memo } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Lightbulb } from 'lucide-react'
import { toast } from 'sonner'
import { Card, CardContent } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import { controlLight } from '@/lib/api'
import { entityLabel } from '@/lib/formatters'
import type { HomeLight } from '@/lib/types'

interface Props {
  entityId: string
  light: HomeLight
}

const LightCard = memo(function LightCard({ entityId, light }: Props) {
  const queryClient = useQueryClient()
  const [brightness, setBrightness] = useState(light.brightness)

  const toggleMut = useMutation({
    mutationFn: () => controlLight(entityId, !light.on, brightness),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['home'] }),
    onError: () => toast.error('照明の操作に失敗しました'),
  })

  const brightMut = useMutation({
    mutationFn: (val: number) => controlLight(entityId, true, val),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['home'] }),
    onError: () => toast.error('明るさの変更に失敗しました'),
  })

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm font-medium text-foreground">
            <Lightbulb className={`h-4 w-4 ${light.on ? 'text-chart-yellow' : 'text-muted-foreground'}`} />
            {entityLabel(entityId)}
          </span>
          <Switch
            checked={light.on}
            onCheckedChange={() => toggleMut.mutate()}
            disabled={toggleMut.isPending}
          />
        </div>
        {light.on && (
          <div>
            <label className="text-xs text-muted-foreground">明るさ: {brightness}</label>
            <Slider
              min={0}
              max={255}
              value={brightness}
              onValueChange={setBrightness}
              onValueCommit={(val) => brightMut.mutate(val)}
            />
          </div>
        )}
      </CardContent>
    </Card>
  )
})

export default LightCard
