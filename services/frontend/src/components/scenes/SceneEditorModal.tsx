import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { createScene, updateScene } from '@/lib/api'
import type { Device, Scene, SceneAction, SceneCreate, SceneUpdate } from '@/lib/types'
import ActionRow from './ActionRow'

interface Props {
  scene: Scene | null  // null = create mode
  devices: Device[]
  open: boolean
  onOpenChange: (open: boolean) => void
  onToast?: (msg: string, kind: 'success' | 'error') => void
}

export default function SceneEditorModal({
  scene, devices, open, onOpenChange, onToast,
}: Props) {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [description, setDescription] = useState('')
  const [actions, setActions] = useState<SceneAction[]>([])
  const [isEnabled, setIsEnabled] = useState(true)

  useEffect(() => {
    if (scene) {
      setName(scene.name)
      setDisplayName(scene.display_name)
      setDescription(scene.description ?? '')
      setActions(scene.actions)
      setIsEnabled(scene.is_enabled)
    } else {
      setName('')
      setDisplayName('')
      setDescription('')
      setActions([])
      setIsEnabled(true)
    }
  }, [scene, open])

  const createMutation = useMutation({
    mutationFn: (payload: SceneCreate) => createScene(payload),
    onSuccess: () => {
      onToast?.('シーンを作成しました', 'success')
      queryClient.invalidateQueries({ queryKey: ['scenes'] })
      onOpenChange(false)
    },
    onError: (err) => onToast?.(err instanceof Error ? err.message : '作成失敗', 'error'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: SceneUpdate }) =>
      updateScene(id, payload),
    onSuccess: () => {
      onToast?.('更新しました', 'success')
      queryClient.invalidateQueries({ queryKey: ['scenes'] })
      onOpenChange(false)
    },
    onError: (err) => onToast?.(err instanceof Error ? err.message : '更新失敗', 'error'),
  })

  const submit = () => {
    if (!displayName.trim()) {
      onToast?.('表示名は必須です', 'error')
      return
    }
    if (!scene && !/^[a-z_][a-z0-9_]*$/.test(name)) {
      onToast?.('name は小文字スネークケース (例: wake_up)', 'error')
      return
    }
    const payload: SceneCreate | SceneUpdate = scene
      ? { display_name: displayName, description, actions, is_enabled: isEnabled }
      : { name, display_name: displayName, description, actions, is_enabled: isEnabled }

    if (scene) {
      updateMutation.mutate({ id: scene.id, payload: payload as SceneUpdate })
    } else {
      createMutation.mutate(payload as SceneCreate)
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

  const pending = createMutation.isPending || updateMutation.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{scene ? 'シーンを編集' : '新規シーン'}</DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">
              name (programmatic ID)
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={!!scene}
              placeholder="wake_up"
              className="w-full px-2 py-1.5 text-sm rounded border border-input bg-background font-mono disabled:opacity-60"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">表示名</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="起床シーン"
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

        <div className="flex items-center gap-2 text-xs">
          <input
            id="scene-enabled"
            type="checkbox"
            checked={isEnabled}
            onChange={(e) => setIsEnabled(e.target.checked)}
          />
          <label htmlFor="scene-enabled" className="cursor-pointer select-none">
            有効
          </label>
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
