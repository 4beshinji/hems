import { useState } from 'react'
import { toast } from 'sonner'
import { Plus } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Select } from '@/components/ui/select'
import { createTask } from '@/lib/api'
import type { PreferredTimeSlot, TaskCreatePayload } from '@/lib/types'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaultSlot?: PreferredTimeSlot
}

const URGENCY_OPTIONS = [
  { value: 0, label: '超低' },
  { value: 1, label: '低' },
  { value: 2, label: '通常' },
  { value: 3, label: '高' },
  { value: 4, label: '緊急' },
]

const COGNITIVE_LOAD_OPTIONS = [
  { value: 0, label: '軽作業' },
  { value: 1, label: '中程度' },
  { value: 2, label: '集中' },
  { value: 3, label: '深集中' },
]

const SLOT_OPTIONS: { value: PreferredTimeSlot; label: string }[] = [
  { value: 'anytime', label: 'いつでも' },
  { value: 'morning', label: '朝 (5-11時)' },
  { value: 'afternoon', label: '昼 (11-17時)' },
  { value: 'evening', label: '夕 (17-22時)' },
  { value: 'deep_night', label: '深夜 (22時以降)' },
]

export default function CreateTaskModal({ open, onOpenChange, defaultSlot = 'anytime' }: Props) {
  const queryClient = useQueryClient()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [urgency, setUrgency] = useState(2)
  const [duration, setDuration] = useState(30)
  const [cognitiveLoad, setCognitiveLoad] = useState<number | ''>('')
  const [preferredSlot, setPreferredSlot] = useState<PreferredTimeSlot>(defaultSlot)
  const [deadline, setDeadline] = useState('')
  const [zone, setZone] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const reset = () => {
    setTitle('')
    setDescription('')
    setUrgency(2)
    setDuration(30)
    setCognitiveLoad('')
    setPreferredSlot(defaultSlot)
    setDeadline('')
    setZone('')
  }

  const handleSubmit = async () => {
    if (!title.trim()) {
      toast.error('タイトルを入力してください')
      return
    }
    setSubmitting(true)
    try {
      const payload: TaskCreatePayload = {
        title: title.trim(),
        description: description.trim() || undefined,
        urgency,
        estimated_duration: duration,
        preferred_time_slot: preferredSlot,
        source: 'user',
      }
      if (cognitiveLoad !== '') payload.cognitive_load = cognitiveLoad
      if (deadline) payload.deadline = new Date(deadline).toISOString()
      if (zone) payload.zone = zone
      await createTask(payload)
      toast.success('タスクを追加しました')
      reset()
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      queryClient.invalidateQueries({ queryKey: ['timeline', 'today'] })
      onOpenChange(false)
    } catch (err) {
      const msg = err instanceof Error ? err.message : '不明なエラー'
      toast.error(`タスク追加に失敗: ${msg}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Plus className="h-4 w-4" />タスクを追加
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
          <div>
            <label className="text-xs font-medium text-foreground">タイトル *</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="例: レポート提出"
              className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              maxLength={120}
              autoFocus
            />
          </div>

          <div>
            <label className="text-xs font-medium text-foreground">説明 (任意)</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-none"
              rows={2}
              maxLength={500}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-foreground">緊急度</label>
              <Select value={String(urgency)} onValueChange={(v) => setUrgency(Number(v))} className="mt-1">
                {URGENCY_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </Select>
            </div>
            <div>
              <label className="text-xs font-medium text-foreground">所要時間 (分)</label>
              <input
                type="number"
                value={duration}
                min={5}
                max={480}
                step={5}
                onChange={(e) => setDuration(Math.max(5, Math.min(480, Number(e.target.value) || 0)))}
                className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-foreground">認知負荷</label>
              <Select
                value={cognitiveLoad === '' ? '' : String(cognitiveLoad)}
                onValueChange={(v) => setCognitiveLoad(v === '' ? '' : Number(v))}
                className="mt-1"
              >
                <option value="">未設定</option>
                {COGNITIVE_LOAD_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </Select>
            </div>
            <div>
              <label className="text-xs font-medium text-foreground">時間帯</label>
              <Select
                value={preferredSlot}
                onValueChange={(v) => setPreferredSlot(v as PreferredTimeSlot)}
                className="mt-1"
              >
                {SLOT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </Select>
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-foreground">締切 (任意)</label>
            <input
              type="datetime-local"
              value={deadline}
              onChange={(e) => setDeadline(e.target.value)}
              className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          <div>
            <label className="text-xs font-medium text-foreground">ゾーン (任意)</label>
            <input
              type="text"
              value={zone}
              onChange={(e) => setZone(e.target.value)}
              placeholder="例: study / kitchen"
              className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              maxLength={40}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            キャンセル
          </Button>
          <Button onClick={handleSubmit} disabled={submitting || !title.trim()}>
            {submitting ? '追加中...' : '追加'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
