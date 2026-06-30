import { useState } from 'react'
import { Loader2, RefreshCw, Shield } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useApprovals, useDecideApproval } from '@/hooks/queries/use-approvals'
import ApprovalCard from './ApprovalCard'
import type { ApprovalDecision } from '@/lib/types'

export default function ApprovalQueue() {
  const [filter, setFilter] = useState<string>('pending')
  const { data: approvals, isLoading, error, refetch } = useApprovals(filter === 'all' ? undefined : filter)
  const decide = useDecideApproval()

  const handleDecide = (id: string, decision: ApprovalDecision, reason?: string) => {
    decide.mutate({
      id,
      decision: {
        decision,
        reason: reason || undefined,
        reviewer_id: 'frontend-user',
      },
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Shield className="h-5 w-5 text-primary" />
          <h2 className="text-lg font-semibold">承認キュー</h2>
        </div>
        <Button variant="ghost" size="sm" onClick={() => refetch()} disabled={isLoading}>
          <RefreshCw className={cn('h-4 w-4', isLoading && 'animate-spin')} />
        </Button>
      </div>

      <Tabs value={filter} onValueChange={setFilter}>
        <TabsList>
          <TabsTrigger value="pending">保留</TabsTrigger>
          <TabsTrigger value="approved">承認済</TabsTrigger>
          <TabsTrigger value="rejected">棄却</TabsTrigger>
          <TabsTrigger value="all">全て</TabsTrigger>
        </TabsList>
      </Tabs>

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/20 bg-destructive/10 p-4 text-sm text-destructive">
          承認一覧の取得に失敗しました: {error.message}
        </div>
      )}

      {!isLoading && !error && (!approvals || approvals.length === 0) && (
        <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          該当する承認リクエストはありません
        </div>
      )}

      <div className="grid gap-4">
        {approvals?.map((approval) => (
          <ApprovalCard
            key={approval.id}
            approval={approval}
            onDecide={handleDecide}
            disabled={decide.isPending}
          />
        ))}
      </div>
    </div>
  )
}
