import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { createAutomation, updateAutomation } from '@/lib/api'
import type {
  AutomationMode,
  AutomationRule,
  AutomationRuleCreate,
  AutomationRuleUpdate,
  AutomationTriggerType,
  Device,
  SceneAction,
} from '@/lib/types'
import ActionRow from '@/components/scenes/ActionRow'
import TriggerConfigForm from './TriggerConfigForm'

interface Props {
  rule: AutomationRule | null
  devices: Device[]
  open: boolean
  onOpenChange: (open: boolean) => void
  onToast?: (msg: string, kind: 'success' | 'error') => void
}

export default function AutomationEditor({
  rule, devices, open, onOpenChange, onToast,
}: Props) {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [triggerType, setTriggerType] = useState<AutomationTriggerType>('sensor_threshold')
  const [triggerConfig, setTriggerConfig] = useState<Record<string, unknown>>({})
  const [actions, setActions] = useState<SceneAction[]>([])
  const [cooldown, setCooldown] = useState(3600)
  const [mode, setMode] = useState<AutomationMode>('direct')

  useEffect(() => {
    if (rule) {
      setName(rule.name)
      setDescription(rule.description ?? '')
      setEnabled(rule.enabled)
      setTriggerType(rule.trigger_type)
      setTriggerConfig(rule.trigger_config ?? {})
      setActions(rule.actions ?? [])
      setCooldown(rule.cooldown_s)
      setMode(rule.mode)
    } else {
      setName('')
      setDescription('')
      setEnabled(true)
      setTriggerType('sensor_threshold')
      setTriggerConfig({})
      setActions([])
      setCooldown(3600)
      setMode('direct')
    }
  }, [rule, open])

  const createMut = useMutation({
    mutationFn: (payload: AutomationRuleCreate) => createAutomation(payload),
    onSuccess: () => {
      onToast?.('ルール作成', 'success')
      queryClient.invalidateQueries({ queryKey: ['automations'] })
      onOpenChange(false)
    },
    onError: (err) => onToast?.(err instanceof Error ? err.message : '失敗', 'error'),
  })
  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: AutomationRuleUpdate }) =>
      updateAutomation(id, payload),
    onSuccess: () => {
      onToast?.('更新', 'success')
      queryClient.invalidateQueries({ queryKey: ['automations'] })
      onOpenChange(false)
    },
    onError: (err) => onToast?.(err instanceof Error ? err.message : '失敗', 'error'),
  })

  const submit = () => {
    if (!name.trim()) {
      onToast?.('名前は必須', 'error')
      return
    }
    if (cooldown < 60) {
      onToast?.('cooldown_s は 60 以上', 'error')
      return
    }
    const payload: AutomationRuleCreate = {
      name, description, enabled, trigger_type: triggerType,
      trigger_config: triggerConfig,
      actions, cooldown_s: cooldown, mode,
    }
    if (rule) {
      updateMut.mutate({ id: rule.id, payload })
    } else {
      createMut.mutate(payload)
    }
  }

  const addAction = () => {
    setActions((arr) => [
      ...arr,
      { device_id: '', action: 'on', params: {}, delay_s: 0 },
    ])
  }
  const updateAction = (idx: number, patch: Partial<SceneAction>) => {
    setActions((arr) => arr.map((a, i) => (i === idx ? { ...a, ...patch } : a)))
  }
  const moveAction = (idx: number, dir: -1 | 1) => {
    setActions((arr) => {
      const next = [...arr]
      const j = idx + dir
      if (j < 0 || j >= next.length) return arr
      ;[next[idx], next[j]] = [next[j], next[idx]]
      return next
    })
  }
  const removeAction = (idx: number) => {
    setActions((arr) => arr.filter((_, i) => i !== idx))
  }

  const pending = createMut.isPending || updateMut.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{rule ? '自動化ルール編集' : '新規ルール'}</DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">名前</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="土壌乾燥→水やり"
              className="w-full px-2 py-1.5 text-sm rounded border border-input bg-background"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">
              cooldown (秒)
            </label>
            <input
              type="number"
              min={60}
              value={cooldown}
              onChange={(e) => setCooldown(Number(e.target.value) || 60)}
              className="w-full px-2 py-1.5 text-sm rounded border border-input bg-background"
            />
          </div>
        </div>

        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">説明</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            className="w-full px-2 py-1.5 text-sm rounded border border-input bg-background resize-none"
          />
        </div>

        <div className="flex items-center gap-4 text-xs">
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            有効
          </label>
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">モード:</span>
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as AutomationMode)}
              className="h-7 rounded border border-input bg-background px-2 text-xs"
            >
              <option value="direct">direct (即実行)</option>
              <option value="llm_review">llm_review (LLMに判断委ねる)</option>
            </select>
          </div>
        </div>

        <div className="space-y-2">
          <h3 className="text-sm font-semibold">トリガー</h3>
          <select
            value={triggerType}
            onChange={(e) => {
              setTriggerType(e.target.value as AutomationTriggerType)
              setTriggerConfig({})
            }}
            className="h-8 rounded border border-input bg-background px-2 text-xs"
          >
            <option value="sensor_threshold">sensor_threshold (センサー閾値)</option>
            <option value="schedule">schedule (時刻)</option>
            <option value="event">event (イベント)</option>
            <option value="device_state">device_state (デバイス状態)</option>
          </select>
          <TriggerConfigForm
            type={triggerType}
            config={triggerConfig}
            devices={devices}
            onChange={setTriggerConfig}
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">アクション</h3>
            <Button size="sm" variant="outline" onClick={addAction} className="gap-1">
              <Plus className="h-3 w-3" />
              追加
            </Button>
          </div>
          {actions.length === 0 ? (
            <p className="text-xs text-muted-foreground italic">
              アクションを追加してください
            </p>
          ) : (
            <div className="space-y-1.5">
              {actions.map((a, i) => (
                <ActionRow
                  key={i}
                  index={i}
                  action={a}
                  devices={devices}
                  isFirst={i === 0}
                  isLast={i === actions.length - 1}
                  onChange={(patch) => updateAction(i, patch)}
                  onMoveUp={() => moveAction(i, -1)}
                  onMoveDown={() => moveAction(i, 1)}
                  onRemove={() => removeAction(i)}
                />
              ))}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            キャンセル
          </Button>
          <Button onClick={submit} disabled={pending}>
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
