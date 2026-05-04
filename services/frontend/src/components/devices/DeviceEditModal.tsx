import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { updateDevice, deleteDevice } from '@/lib/api'
import type { Device, DeviceUpdate } from '@/lib/types'

interface Props {
  device: Device | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onToast?: (msg: string, kind: 'success' | 'error') => void
}

export default function DeviceEditModal({ device, open, onOpenChange, onToast }: Props) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<DeviceUpdate>({})
  const [confirmDelete, setConfirmDelete] = useState(false)

  useEffect(() => {
    if (device) {
      setForm({
        display_name: device.display_name ?? '',
        zone: device.zone ?? '',
        location: device.location ?? '',
        purpose: device.purpose ?? '',
        description: device.description ?? '',
        notes: device.notes ?? '',
        is_enabled: device.is_enabled,
        kind: device.kind,
        device_class: device.device_class ?? '',
      })
      setConfirmDelete(false)
    }
  }, [device, open])

  const saveMutation = useMutation({
    mutationFn: async (payload: DeviceUpdate) => {
      if (!device) throw new Error('No device')
      return updateDevice(device.device_id, payload)
    },
    onSuccess: () => {
      onToast?.('更新しました', 'success')
      queryClient.invalidateQueries({ queryKey: ['devices'] })
      onOpenChange(false)
    },
    onError: (err) => {
      onToast?.(err instanceof Error ? err.message : '保存失敗', 'error')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async () => {
      if (!device) throw new Error('No device')
      return deleteDevice(device.device_id)
    },
    onSuccess: () => {
      onToast?.('削除しました', 'success')
      queryClient.invalidateQueries({ queryKey: ['devices'] })
      onOpenChange(false)
    },
    onError: (err) => {
      onToast?.(err instanceof Error ? err.message : '削除失敗', 'error')
    },
  })

  if (!device) return null

  const field = (name: keyof DeviceUpdate, label: string, placeholder?: string,
                 type: 'input' | 'textarea' = 'input') => (
    <div className="space-y-1">
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      {type === 'textarea' ? (
        <textarea
          value={(form[name] as string | undefined) ?? ''}
          onChange={(e) => setForm((f) => ({ ...f, [name]: e.target.value }))}
          placeholder={placeholder}
          rows={2}
          className="w-full px-2 py-1.5 text-sm rounded border border-input bg-background resize-none"
        />
      ) : (
        <input
          type="text"
          value={(form[name] as string | undefined) ?? ''}
          onChange={(e) => setForm((f) => ({ ...f, [name]: e.target.value }))}
          placeholder={placeholder}
          className="w-full px-2 py-1.5 text-sm rounded border border-input bg-background"
        />
      )}
    </div>
  )

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>
            <span className="font-mono text-sm text-muted-foreground mr-2">
              {device.device_id}
            </span>
            {device.display_name || ''}
          </DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3">
          {field('display_name', '表示名', '寝室デスクライト')}
          {field('zone', 'ゾーン', 'bedroom')}
          {field('location', '設置場所', '机の右奥')}
          {field('device_class', 'Device Class', 'plug / light / pump')}
        </div>

        {field('purpose', '用途 (LLM context)', '起床補助デスクライト / 電力計測', 'textarea')}
        {field('description', '説明', '', 'textarea')}
        {field('notes', 'メモ', '', 'textarea')}

        <div className="flex items-center gap-2 text-xs">
          <input
            id="dev-enabled"
            type="checkbox"
            checked={form.is_enabled ?? true}
            onChange={(e) => setForm((f) => ({ ...f, is_enabled: e.target.checked }))}
          />
          <label htmlFor="dev-enabled" className="cursor-pointer select-none">
            有効（LLMと自動化に参照される）
          </label>
        </div>

        <div className="text-xs text-muted-foreground space-y-0.5">
          <div>
            vendor: <span className="font-mono">{device.vendor}</span>
            {device.vendor_ref && (
              <> / ref: <span className="font-mono">{device.vendor_ref}</span></>
            )}
          </div>
          <div>
            capabilities: {device.capabilities?.join(', ') || 'なし'}
            {device.channels?.length ? ` / channels: ${device.channels.join(', ')}` : ''}
          </div>
          {device.last_seen && (
            <div>最終観測: {new Date(device.last_seen).toLocaleString('ja-JP')}</div>
          )}
        </div>

        <DialogFooter className="gap-2">
          {confirmDelete ? (
            <div className="flex gap-2 mr-auto">
              <Button
                variant="destructive"
                size="sm"
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
              >
                本当に削除
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(false)}>
                キャンセル
              </Button>
            </div>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setConfirmDelete(true)}
              className="text-destructive mr-auto"
            >
              削除
            </Button>
          )}
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            キャンセル
          </Button>
          <Button
            onClick={() => saveMutation.mutate(form)}
            disabled={saveMutation.isPending}
          >
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
