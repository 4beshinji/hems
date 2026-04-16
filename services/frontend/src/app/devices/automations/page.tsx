import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ArrowLeft, Plus, Pencil, Trash2, FlaskConical } from 'lucide-react'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import LoadingState from '@/components/shared/LoadingState'
import ErrorState from '@/components/shared/ErrorState'
import AutomationEditor from '@/components/automations/AutomationEditor'
import {
  deleteAutomation,
  fetchAutomations,
  fetchDevices,
  testAutomation,
} from '@/lib/api'
import type { AutomationRule, Device } from '@/lib/types'
import { formatAge } from '@/lib/formatters'

function summarizeTrigger(rule: AutomationRule): string {
  const t = rule.trigger_config
  switch (rule.trigger_type) {
    case 'sensor_threshold':
      return `${t.device_id}.${t.channel} ${t.op} ${t.value}${t.sustain_s ? ` (${t.sustain_s}s継続)` : ''}`
    case 'schedule':
      return t.time ? `毎日 ${t.time}` : t.cron ? `cron: ${t.cron}` : '(未設定)'
    case 'event':
      return `event: ${t.event ?? '?'}`
    case 'device_state':
      return `${t.device_id}.${t.state_key} == ${String(t.equals)}`
  }
}

export default function AutomationsPage() {
  const queryClient = useQueryClient()
  const [editTarget, setEditTarget] = useState<AutomationRule | null>(null)
  const [modalOpen, setModalOpen] = useState(false)

  const rulesQuery = useQuery<AutomationRule[]>({
    queryKey: ['automations'],
    queryFn: () => fetchAutomations(),
    refetchInterval: 10_000,
  })

  const devicesQuery = useQuery<Device[]>({
    queryKey: ['devices'],
    queryFn: () => fetchDevices({ enabled_only: true }),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteAutomation(id),
    onSuccess: () => {
      toast.success('削除')
      queryClient.invalidateQueries({ queryKey: ['automations'] })
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : '失敗'),
  })

  const testMut = useMutation({
    mutationFn: (id: number) => testAutomation(id),
    onSuccess: (data) => {
      if (data.would_fire) {
        toast.success(`発火条件成立: ${data.reason}`)
      } else {
        toast.message(`発火しない: ${data.reason}`)
      }
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : '失敗'),
  })

  if (rulesQuery.isLoading) return <LoadingState />
  if (rulesQuery.isError) return <ErrorState onRetry={() => rulesQuery.refetch()} />

  const rules = rulesQuery.data ?? []
  const devices = devicesQuery.data ?? []

  const openCreate = () => {
    setEditTarget(null)
    setModalOpen(true)
  }
  const openEdit = (rule: AutomationRule) => {
    setEditTarget(rule)
    setModalOpen(true)
  }

  const handleToast = (msg: string, kind: 'success' | 'error') =>
    kind === 'success' ? toast.success(msg) : toast.error(msg)

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Link
          to="/devices"
          className="text-muted-foreground hover:text-foreground"
          aria-label="戻る"
        >
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="flex-1">
          <h1 className="text-xl font-semibold">自動化ルール</h1>
          <p className="text-sm text-muted-foreground">
            センサー閾値 / スケジュール / イベント / デバイス状態 を条件に自動実行
          </p>
        </div>
        <Button onClick={openCreate} className="gap-1">
          <Plus className="h-4 w-4" /> 新規
        </Button>
      </div>

      {rules.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          ルールが登録されていません。[+新規] から作成してください。<br />
          例: 土壌水分 &lt; 20 が 5 分継続 → 水ポンプ pulse 30秒 (mode: llm_review)
        </div>
      ) : (
        <div className="space-y-3">
          {rules.map((rule) => (
            <div
              key={rule.id}
              className="rounded-lg border border-border bg-card"
            >
              <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{rule.name}</span>
                    <Badge variant={rule.enabled ? 'default' : 'secondary'}>
                      {rule.enabled ? '有効' : '無効'}
                    </Badge>
                    <Badge
                      variant={rule.mode === 'llm_review' ? 'info' : 'outline'}
                    >
                      {rule.mode}
                    </Badge>
                  </div>
                  {rule.description && (
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {rule.description}
                    </p>
                  )}
                  <div className="text-xs text-muted-foreground mt-1 flex flex-wrap gap-3">
                    <span>Trigger: {summarizeTrigger(rule)}</span>
                    <span>Cooldown: {rule.cooldown_s}s</span>
                    {rule.fire_count > 0 && <span>発火 {rule.fire_count} 回</span>}
                    {rule.last_fired_at && (
                      <span>直近発火: {formatAge(rule.last_fired_at)}</span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => testMut.mutate(rule.id)}
                    disabled={testMut.isPending}
                    className="gap-1"
                    title="ドライラン: トリガー条件を評価 (アクション実行しない)"
                  >
                    <FlaskConical className="h-3.5 w-3.5" />
                    Test
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => openEdit(rule)}
                    className="h-8 w-8"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => {
                      if (confirm(`ルール "${rule.name}" を削除しますか?`)) {
                        deleteMut.mutate(rule.id)
                      }
                    }}
                    className="h-8 w-8 text-destructive"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
              <ol className="px-4 py-2 space-y-1 text-xs">
                {rule.actions.map((a, i) => (
                  <li key={i} className="flex items-baseline gap-2">
                    <span className="text-muted-foreground font-mono w-6">
                      {i + 1}.
                    </span>
                    <span className="font-mono text-muted-foreground">
                      {a.device_id}
                    </span>
                    <span>を</span>
                    <span className="font-medium">{a.action}</span>
                    {a.params && Object.keys(a.params).length > 0 && (
                      <span className="text-muted-foreground">
                        {JSON.stringify(a.params)}
                      </span>
                    )}
                    {a.delay_s > 0 && (
                      <span className="text-muted-foreground">+{a.delay_s}s</span>
                    )}
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </div>
      )}

      <AutomationEditor
        rule={editTarget}
        devices={devices}
        open={modalOpen}
        onOpenChange={setModalOpen}
        onToast={handleToast}
      />
    </div>
  )
}
