import { Check, X, TrendingUp, TrendingDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { ThresholdDriftLog } from '@/lib/types'

interface Props {
  proposal: ThresholdDriftLog
  onDecide: (id: number, decision: 'approve' | 'reject') => void
  disabled?: boolean
}

const METRIC_LABELS: Record<string, string> = {
  co2_high: 'CO2 上限',
  temp_high: '室温 上限',
  temp_low: '室温 下限',
  humidity_high: '湿度 上限',
  humidity_low: '湿度 下限',
  pm25_high: 'PM2.5 上限',
}

export default function ThresholdProposalCard({ proposal, onDecide, disabled }: Props) {
  const oldValue = proposal.old_value ?? '-'
  const proposedValue = proposal.proposed_value ?? '-'
  const direction =
    typeof proposal.proposed_value === 'number' && typeof proposal.old_value === 'number'
      ? proposal.proposed_value > proposal.old_value
        ? 'up'
        : 'down'
      : 'neutral'

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant="outline">{METRIC_LABELS[proposal.metric_key] ?? proposal.metric_key}</Badge>
              <Badge variant={proposal.status === 'proposed' ? 'default' : 'secondary'}>
                {proposal.status}
              </Badge>
            </div>
            <h3 className="mt-2 text-base font-semibold">
              閾値変更提案: {METRIC_LABELS[proposal.metric_key] ?? proposal.metric_key}
            </h3>
            <p className="text-sm text-muted-foreground">
              {new Date(proposal.detected_at).toLocaleString('ja-JP')}
            </p>
          </div>
          {direction === 'up' ? (
            <TrendingUp className="h-5 w-5 text-amber-500 shrink-0" />
          ) : direction === 'down' ? (
            <TrendingDown className="h-5 w-5 text-blue-500 shrink-0" />
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="pb-3">
        <div className="flex items-center gap-4 text-sm">
          <div className="flex-1 rounded-lg bg-muted p-3">
            <p className="text-muted-foreground">現在の閾値</p>
            <p className="text-lg font-medium">{oldValue}</p>
          </div>
          <div className="text-muted-foreground">→</div>
          <div className={cn(
            'flex-1 rounded-lg p-3',
            direction === 'up' && 'bg-amber-500/10',
            direction === 'down' && 'bg-blue-500/10',
            direction === 'neutral' && 'bg-muted'
          )}>
            <p className="text-muted-foreground">提案値</p>
            <p className="text-lg font-medium">{proposedValue}</p>
          </div>
        </div>
        {proposal.reason && (
          <p className="mt-3 text-sm text-muted-foreground">理由: {proposal.reason}</p>
        )}
      </CardContent>
      {proposal.status === 'proposed' && (
        <CardFooter className="flex gap-2 pt-0">
          <Button
            variant="outline"
            size="sm"
            className="flex-1"
            disabled={disabled}
            onClick={() => onDecide(proposal.id, 'reject')}
          >
            <X className="h-4 w-4 mr-1" />
            棄却
          </Button>
          <Button
            size="sm"
            className="flex-1"
            disabled={disabled}
            onClick={() => onDecide(proposal.id, 'approve')}
          >
            <Check className="h-4 w-4 mr-1" />
            承認
          </Button>
        </CardFooter>
      )}
    </Card>
  )
}
