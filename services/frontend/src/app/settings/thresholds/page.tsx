import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { SlidersHorizontal } from 'lucide-react'
import { decideProposal, fetchAdjustments, fetchProposals } from '@/lib/api/thresholds'
import ThresholdProposalCard from '@/components/thresholds/ThresholdProposalCard'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'

const METRIC_LABELS: Record<string, string> = {
  co2_high: 'CO2 上限',
  temp_high: '室温 上限',
  temp_low: '室温 下限',
  humidity_high: '湿度 上限',
  humidity_low: '湿度 下限',
  pm25_high: 'PM2.5 上限',
}

export default function ThresholdSettingsPage() {
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState<'all' | 'proposed'>('proposed')

  const proposalsQuery = useQuery({
    queryKey: ['threshold-proposals', filter],
    queryFn: () => fetchProposals(filter === 'proposed' ? 'proposed' : undefined),
    refetchInterval: 30000,
  })

  const adjustmentsQuery = useQuery({
    queryKey: ['threshold-adjustments'],
    queryFn: fetchAdjustments,
    refetchInterval: 30000,
  })

  const decideMutation = useMutation({
    mutationFn: ({ id, decision }: { id: number; decision: 'approve' | 'reject' }) =>
      decideProposal(id, { decision }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['threshold-proposals'] })
      queryClient.invalidateQueries({ queryKey: ['threshold-adjustments'] })
    },
  })

  const proposals = proposalsQuery.data ?? []
  const adjustments = adjustmentsQuery.data ?? []

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-4xl mx-auto">
      <div className="flex items-center gap-3">
        <SlidersHorizontal className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-xl font-semibold">閾値調整</h1>
          <p className="text-sm text-muted-foreground">
            センサーデータのドリフトに基づく閾値変更提案を確認・承認します。
          </p>
        </div>
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => setFilter('proposed')}
          className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
            filter === 'proposed'
              ? 'bg-primary text-primary-foreground border-primary'
              : 'bg-card text-muted-foreground border-border hover:bg-accent'
          }`}
        >
          提案中
        </button>
        <button
          onClick={() => setFilter('all')}
          className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
            filter === 'all'
              ? 'bg-primary text-primary-foreground border-primary'
              : 'bg-card text-muted-foreground border-border hover:bg-accent'
          }`}
        >
          全履歴
        </button>
      </div>

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
          変更提案
        </h2>
        {proposalsQuery.isLoading ? (
          <p className="text-sm text-muted-foreground">読み込み中…</p>
        ) : proposals.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              現在、閾値変更提案はありません。
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-3">
            {proposals.map((proposal) => (
              <ThresholdProposalCard
                key={proposal.id}
                proposal={proposal}
                disabled={decideMutation.isPending}
                onDecide={(id, decision) => decideMutation.mutate({ id, decision })}
              />
            ))}
          </div>
        )}
      </section>

      <Separator />

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
          適用済みオフセット
        </h2>
        {adjustmentsQuery.isLoading ? (
          <p className="text-sm text-muted-foreground">読み込み中…</p>
        ) : adjustments.length === 0 ? (
          <Card>
            <CardContent className="py-6 text-center text-sm text-muted-foreground">
              適用済みの閾値オフセットはありません。
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader className="pb-2" />
            <CardContent>
              <div className="divide-y divide-border">
                {adjustments.map((adj) => (
                  <div key={adj.id} className="py-3 flex items-center justify-between">
                    <div>
                      <p className="font-medium">
                        {METRIC_LABELS[adj.metric_key] ?? adj.metric_key}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        基準値 {adj.base_value} / 適用 {new Date(adj.applied_at).toLocaleString('ja-JP')}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant={adj.offset > 0 ? 'default' : 'secondary'}>
                        {adj.offset > 0 ? '+' : ''}{adj.offset}
                      </Badge>
                      <span className="text-xs text-muted-foreground">{adj.approved_by}</span>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </section>
    </div>
  )
}
