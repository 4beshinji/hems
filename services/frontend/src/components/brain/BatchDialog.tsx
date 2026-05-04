import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Play, Loader2, Check } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { fetchOllamaModels, runBatch } from '@/lib/api'
import type { BatchTaskName, OllamaModel } from '@/lib/types'

interface TaskOption {
  id: BatchTaskName
  label: string
  description: string
}

const TASK_OPTIONS: TaskOption[] = [
  { id: 'news_briefing',    label: 'ニュース要約',    description: 'RSS から最新ニュースを取得して要約・発話' },
  { id: 'morning_greeting', label: '朝のあいさつ',    description: '天気・カレンダーを参照して挨拶を生成・発話' },
  { id: 'task_planning',    label: 'タスク詳細設計',  description: 'アクティブタスクの手順・所要時間を LLM で分析・発話' },
  { id: 'weather_report',   label: '天気レポート',    description: '現在の天気と予報を発話' },
]

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export default function BatchDialog({ open, onOpenChange }: Props) {
  const [selected, setSelected] = useState<Set<BatchTaskName>>(
    new Set(TASK_OPTIONS.map(t => t.id)),
  )
  const [model, setModel] = useState<string>('__current__')

  const modelsQuery = useQuery({
    queryKey: ['ollamaModels'],
    queryFn: fetchOllamaModels,
    enabled: open,
    staleTime: 60_000,
  })

  const runMut = useMutation({
    mutationFn: ({ tasks, model }: { tasks: BatchTaskName[]; model: string | null }) =>
      runBatch(tasks, model),
    onSuccess: (data) => {
      const labels = data.labels.join('・')
      toast.success(`バッチ実行を開始しました: ${labels}`)
      onOpenChange(false)
    },
    onError: (err) => {
      toast.error(`実行エラー: ${err instanceof Error ? err.message : String(err)}`)
    },
  })

  const toggleTask = (id: BatchTaskName) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const handleRun = () => {
    const tasks = TASK_OPTIONS.map(t => t.id).filter(id => selected.has(id))
    if (tasks.length === 0) {
      toast.warning('タスクを1つ以上選択してください')
      return
    }
    runMut.mutate({
      tasks,
      model: model === '__current__' ? null : model,
    })
  }

  const models: OllamaModel[] = modelsQuery.data?.models ?? []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Play className="h-4 w-4" />
            バッチ実行
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Task selection */}
          <div className="space-y-2">
            <p className="text-sm font-medium text-foreground">実行するタスク</p>
            <div className="space-y-1.5">
              {TASK_OPTIONS.map(task => {
                const isSelected = selected.has(task.id)
                return (
                  <button
                    key={task.id}
                    type="button"
                    onClick={() => toggleTask(task.id)}
                    className={cn(
                      'w-full flex items-start gap-3 px-3 py-2.5 rounded-lg border text-left transition-colors',
                      isSelected
                        ? 'border-primary bg-primary/5 text-foreground'
                        : 'border-border bg-transparent text-muted-foreground hover:bg-accent',
                    )}
                  >
                    <div className={cn(
                      'mt-0.5 h-4 w-4 shrink-0 rounded border flex items-center justify-center',
                      isSelected ? 'bg-primary border-primary' : 'border-muted-foreground/40',
                    )}>
                      {isSelected && <Check className="h-3 w-3 text-primary-foreground" />}
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium leading-none">{task.label}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">{task.description}</p>
                    </div>
                  </button>
                )
              })}
            </div>
          </div>

          {/* Model selection */}
          <div className="space-y-1.5">
            <p className="text-sm font-medium text-foreground">使用モデル</p>
            <Select
              value={model}
              onValueChange={setModel}
              disabled={modelsQuery.isLoading}
              className="w-full"
            >
              <option value="__current__">現在のモデルを使用</option>
              {models.map(m => (
                <option key={m.name} value={m.name}>
                  {m.name}{m.size_gb > 0 ? ` (${m.size_gb} GB)` : ''}
                </option>
              ))}
              {!modelsQuery.isLoading && models.length === 0 && (
                <option value="__none__" disabled>Ollama 未起動</option>
              )}
            </Select>
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={runMut.isPending}>
            キャンセル
          </Button>
          <Button onClick={handleRun} disabled={runMut.isPending || selected.size === 0}>
            {runMut.isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                実行中...
              </>
            ) : (
              <>
                <Play className="h-4 w-4 mr-2" />
                実行
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
