import { useState, memo } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Blinds } from 'lucide-react'
import { toast } from 'sonner'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import { controlCover } from '@/lib/api'
import { entityLabel } from '@/lib/formatters'
import type { HomeCover } from '@/lib/types'

interface Props {
  entityId: string
  cover: HomeCover
}

const CoverCard = memo(function CoverCard({ entityId, cover }: Props) {
  const queryClient = useQueryClient()
  const [pos, setPos] = useState(cover.position)

  const actionMut = useMutation({
    mutationFn: (action: string) => controlCover(entityId, action),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['home'] }),
    onError: () => toast.error('カバーの操作に失敗しました'),
  })

  const posMut = useMutation({
    mutationFn: (p: number) => controlCover(entityId, undefined, p),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['home'] }),
    onError: () => toast.error('位置の変更に失敗しました'),
  })

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm font-medium text-foreground">
            <Blinds className={`h-4 w-4 ${cover.is_open ? 'text-info' : 'text-muted-foreground'}`} />
            {entityLabel(entityId)}
          </span>
          <span className="text-xs text-muted-foreground">{cover.position}%</span>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="flex-1"
            onClick={() => actionMut.mutate('open')}
            disabled={actionMut.isPending}
          >
            開
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="flex-1"
            onClick={() => actionMut.mutate('stop')}
            disabled={actionMut.isPending}
          >
            停止
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="flex-1"
            onClick={() => actionMut.mutate('close')}
            disabled={actionMut.isPending}
          >
            閉
          </Button>
        </div>
        <Slider
          min={0}
          max={100}
          value={pos}
          onValueChange={setPos}
          onValueCommit={(val) => posMut.mutate(val)}
        />
      </CardContent>
    </Card>
  )
})

export default CoverCard
