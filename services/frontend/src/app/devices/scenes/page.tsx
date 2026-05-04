import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ArrowLeft, Play, Plus, Pencil, Trash2 } from 'lucide-react'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import LoadingState from '@/components/shared/LoadingState'
import ErrorState from '@/components/shared/ErrorState'
import SceneEditorModal from '@/components/scenes/SceneEditorModal'
import {
  deleteScene,
  executeScene,
  fetchDevices,
  fetchScenes,
} from '@/lib/api'
import type { Device, Scene } from '@/lib/types'
import { formatAge } from '@/lib/formatters'

export default function ScenesPage() {
  const queryClient = useQueryClient()
  const [editTarget, setEditTarget] = useState<Scene | null>(null)
  const [modalOpen, setModalOpen] = useState(false)

  const scenesQuery = useQuery<Scene[]>({
    queryKey: ['scenes'],
    queryFn: () => fetchScenes(),
    refetchInterval: 10_000,
  })

  const devicesQuery = useQuery<Device[]>({
    queryKey: ['devices'],
    queryFn: () => fetchDevices({ enabled_only: true }),
  })

  const executeMutation = useMutation({
    mutationFn: (id: number) => executeScene(id),
    onSuccess: (result, id) => {
      if (result.success) {
        toast.success(`実行完了 (${result.executed} アクション)`)
      } else {
        toast.error(`一部失敗: ${result.errors.join('; ')}`)
      }
      queryClient.invalidateQueries({ queryKey: ['scenes'] })
      void id
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : '実行失敗'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteScene(id),
    onSuccess: () => {
      toast.success('削除しました')
      queryClient.invalidateQueries({ queryKey: ['scenes'] })
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : '削除失敗'),
  })

  if (scenesQuery.isLoading) return <LoadingState />
  if (scenesQuery.isError) return <ErrorState onRetry={() => scenesQuery.refetch()} />

  const scenes = scenesQuery.data ?? []
  const devices = devicesQuery.data ?? []

  const openCreate = () => {
    setEditTarget(null)
    setModalOpen(true)
  }
  const openEdit = (scene: Scene) => {
    setEditTarget(scene)
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
          <h1 className="text-xl font-semibold">シーン</h1>
          <p className="text-sm text-muted-foreground">
            複数デバイスの一括操作 (delay_s 順次実行) — 起床/就寝など
          </p>
        </div>
        <Button onClick={openCreate} className="gap-1">
          <Plus className="h-4 w-4" /> 新規
        </Button>
      </div>

      {scenes.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          シーンが登録されていません。[+新規] から作成してください。
        </div>
      ) : (
        <div className="space-y-3">
          {scenes.map((scene) => {
            const deviceMap = new Map(devices.map((d) => [d.device_id, d]))
            return (
              <div
                key={scene.id}
                className="rounded-lg border border-border bg-card"
              >
                <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                  <div className="flex items-center gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold">{scene.display_name}</span>
                        <span className="font-mono text-xs text-muted-foreground">
                          {scene.name}
                        </span>
                        {!scene.is_enabled && (
                          <Badge variant="secondary">無効</Badge>
                        )}
                      </div>
                      {scene.description && (
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {scene.description}
                        </p>
                      )}
                      <div className="text-xs text-muted-foreground mt-1 flex gap-3">
                        <span>{scene.actions.length} アクション</span>
                        {scene.execution_count > 0 && (
                          <span>実行 {scene.execution_count} 回</span>
                        )}
                        {scene.last_executed_at && (
                          <span>直近: {formatAge(scene.last_executed_at)}</span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => executeMutation.mutate(scene.id)}
                      disabled={!scene.is_enabled || executeMutation.isPending}
                      className="gap-1"
                    >
                      <Play className="h-3.5 w-3.5" />
                      実行
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => openEdit(scene)}
                      className="h-8 w-8"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => {
                        if (confirm(`シーン "${scene.display_name}" を削除しますか?`)) {
                          deleteMutation.mutate(scene.id)
                        }
                      }}
                      className="h-8 w-8 text-destructive"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
                <ol className="px-4 py-2 space-y-1 text-xs">
                  {scene.actions.map((a, i) => {
                    const dev = deviceMap.get(a.device_id)
                    const valueDisplay =
                      a.params && Object.keys(a.params).length > 0
                        ? JSON.stringify(a.params)
                        : ''
                    return (
                      <li key={i} className="flex items-baseline gap-2">
                        <span className="text-muted-foreground font-mono w-6">
                          {i + 1}.
                        </span>
                        <span className="font-mono text-muted-foreground">
                          {a.device_id}
                        </span>
                        {dev?.display_name && (
                          <span className="text-muted-foreground italic">
                            ({dev.display_name})
                          </span>
                        )}
                        <span>を</span>
                        <span className="font-medium">{a.action}</span>
                        {valueDisplay && (
                          <span className="text-muted-foreground">{valueDisplay}</span>
                        )}
                        {a.delay_s > 0 && (
                          <span className="text-muted-foreground">+{a.delay_s}s</span>
                        )}
                      </li>
                    )
                  })}
                </ol>
              </div>
            )
          })}
        </div>
      )}

      <SceneEditorModal
        scene={editTarget}
        devices={devices}
        open={modalOpen}
        onOpenChange={setModalOpen}
        onToast={handleToast}
      />
    </div>
  )
}
