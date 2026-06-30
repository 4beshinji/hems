import { useState } from 'react'
import { Check, X, PenLine, AlertTriangle, ShieldAlert, ShieldCheck, ShieldX, Clock } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { FeedbackButtons } from '@/components/feedback/FeedbackButtons'
import type { Approval, ApprovalDecision, RiskTier } from '@/lib/types'

interface ApprovalCardProps {
  approval: Approval
  onDecide: (id: string, decision: ApprovalDecision, reason?: string, modifiedPayload?: Record<string, unknown>) => void
  disabled?: boolean
}

const RISK_CONFIG: Record<RiskTier, { label: string; color: string; icon: typeof ShieldCheck }> = {
  safe: { label: '安全', color: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20', icon: ShieldCheck },
  low: { label: '低', color: 'bg-blue-500/10 text-blue-600 border-blue-500/20', icon: ShieldCheck },
  medium: { label: '中', color: 'bg-amber-500/10 text-amber-600 border-amber-500/20', icon: AlertTriangle },
  high: { label: '高', color: 'bg-orange-500/10 text-orange-600 border-orange-500/20', icon: ShieldAlert },
  critical: { label: '重大', color: 'bg-destructive/10 text-destructive border-destructive/20', icon: ShieldX },
}

export default function ApprovalCard({ approval, onDecide, disabled }: ApprovalCardProps) {
  const [reason, setReason] = useState('')
  const [showModify, setShowModify] = useState(false)
  const [jsonError, setJsonError] = useState<string | null>(null)
  const risk = RISK_CONFIG[approval.risk_tier]
  const RiskIcon = risk.icon

  const isPending = approval.status === 'pending' || approval.status === 'proposed'
  const expiresAt = approval.expires_at ? new Date(approval.expires_at) : null

  return (
    <Card className={cn('overflow-hidden', !isPending && 'opacity-80')}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant="outline" className={cn('gap-1 font-medium', risk.color)}>
                <RiskIcon className="h-3 w-3" />
                {risk.label}リスク
              </Badge>
              <Badge variant="outline">{approval.reversibility}</Badge>
              <Badge variant={isPending ? 'default' : 'secondary'}>{approval.status}</Badge>
              {!isPending && (
                <FeedbackButtons targetType="approval" targetId={approval.id} showCancel showRerun />
              )}
            </div>
            <h3 className="mt-2 text-base font-semibold truncate">
              {approval.action_type === 'rule'
                ? `ルール実行: ${(approval.context?.rule_name as string) ?? approval.context?.rule_id ?? 'unknown'}`
                : approval.action_type}
            </h3>
            <p className="text-sm text-muted-foreground">
              {approval.requested_at && new Date(approval.requested_at).toLocaleString('ja-JP')}
              {expiresAt && (
                <span className="ml-2 inline-flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  期限: {expiresAt.toLocaleTimeString('ja-JP')}
                </span>
              )}
            </p>
          </div>
        </div>
      </CardHeader>

      <CardContent className="pb-3">
        <div className="rounded-md bg-muted p-3 text-sm font-mono whitespace-pre-wrap break-all">
          {JSON.stringify(approval.proposed_payload, null, 2)}
        </div>
        {approval.context && Object.keys(approval.context).length > 0 && (
          <div className="mt-2 text-xs text-muted-foreground">
            {'zone' in approval.context && approval.context.zone != null && (
              <span className="mr-3">zone: {String(approval.context.zone)}</span>
            )}
            {'rule_name' in approval.context && approval.context.rule_name != null && (
              <span>rule: {String(approval.context.rule_name)}</span>
            )}
          </div>
        )}

        {isPending && (
          <div className="mt-3">
            <label htmlFor={`reason-${approval.id}`} className="text-xs text-muted-foreground">
              理由（任意）
            </label>
            <input
              id={`reason-${approval.id}`}
              type="text"
              value={reason}
              onChange={(e) => {
                setReason(e.target.value)
                setJsonError(null)
              }}
              placeholder={showModify ? '修正内容を JSON またはテキストで記述' : '承認/棄却理由'}
              disabled={disabled}
              className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
            {jsonError && <p className="mt-1 text-xs text-destructive">{jsonError}</p>}
          </div>
        )}
      </CardContent>

      {isPending && (
        <CardFooter className="flex flex-wrap gap-2 pt-0">
          <Button
            variant="default"
            size="sm"
            className="flex-1 min-w-[72px]"
            disabled={disabled}
            onClick={() => onDecide(approval.id, 'approve', reason)}
          >
            <Check className="h-4 w-4 mr-1" />
            承認
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="flex-1 min-w-[72px]"
            disabled={disabled}
            onClick={() => {
              if (showModify) {
                try {
                  const parsed = JSON.parse(reason)
                  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                    setJsonError(null)
                    onDecide(approval.id, 'modify', reason, parsed as Record<string, unknown>)
                  } else {
                    setJsonError('修正内容は JSON オブジェクト形式で入力してください')
                  }
                } catch {
                  setJsonError('無効な JSON です。修正内容を確認してください')
                }
              } else {
                setShowModify(true)
              }
            }}
          >
            <PenLine className="h-4 w-4 mr-1" />
            {showModify ? '修正適用' : '修正'}
          </Button>
          {showModify && (
            <Button
              variant="ghost"
              size="sm"
              className="shrink-0"
              disabled={disabled}
              onClick={() => {
                setShowModify(false)
                setReason('')
                setJsonError(null)
              }}
            >
              キャンセル
            </Button>
          )}
          <Button
            variant="destructive"
            size="sm"
            className="flex-1 min-w-[72px]"
            disabled={disabled}
            onClick={() => onDecide(approval.id, 'reject', reason)}
          >
            <X className="h-4 w-4 mr-1" />
            棄却
          </Button>
        </CardFooter>
      )}
    </Card>
  )
}
