import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import QRCode from 'qrcode'
import { Plus, RefreshCw, Smartphone, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import LoadingState from '@/components/shared/LoadingState'
import ErrorState from '@/components/shared/ErrorState'
import {
  disableMobileDevice,
  fetchMobileDevices,
  registerMobileDevice,
} from '@/lib/api'
import type {
  MobileDevice,
  MobileDeviceRegisterResponse,
} from '@/lib/types'

export default function MobileDevicesPage() {
  const query = useQuery<MobileDevice[]>({
    queryKey: ['mobile-devices'],
    queryFn: fetchMobileDevices,
    refetchInterval: 15_000,
  })

  const [registerOpen, setRegisterOpen] = useState(false)
  const [qrTarget, setQrTarget] = useState<MobileDeviceRegisterResponse | null>(null)

  return (
    <div className="p-4 md:p-6 space-y-4 max-w-5xl mx-auto">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">モバイル端末</h1>
          <p className="text-sm text-muted-foreground">
            登録済みのコンパニオン端末と、新規ペアリング用 QR の発行
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => query.refetch()}
            disabled={query.isFetching}
          >
            <RefreshCw className="w-4 h-4 mr-1" />
            更新
          </Button>
          <Button size="sm" onClick={() => setRegisterOpen(true)}>
            <Plus className="w-4 h-4 mr-1" />
            新規ペアリング
          </Button>
        </div>
      </header>

      {query.isLoading && <LoadingState />}
      {query.isError && <ErrorState message={String(query.error)} />}

      {query.data && <DeviceTable devices={query.data} />}

      <RegisterDialog
        open={registerOpen}
        onOpenChange={setRegisterOpen}
        onRegistered={(resp) => {
          setRegisterOpen(false)
          setQrTarget(resp)
        }}
      />

      <QrDialog
        response={qrTarget}
        onClose={() => setQrTarget(null)}
      />
    </div>
  )
}

function DeviceTable({ devices }: { devices: MobileDevice[] }) {
  const queryClient = useQueryClient()
  const disableMutation = useMutation({
    mutationFn: (id: number) => disableMobileDevice(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mobile-devices'] })
      toast.success('無効化しました')
    },
    onError: (err) => toast.error(`失敗: ${String(err)}`),
  })

  if (devices.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
        端末が未登録です。「新規ペアリング」で最初の1台を登録してください。
      </div>
    )
  }
  return (
    <div className="overflow-hidden border rounded-lg">
      <table className="w-full text-sm">
        <thead className="bg-muted/50">
          <tr className="text-left">
            <th className="px-3 py-2 font-medium">ラベル</th>
            <th className="px-3 py-2 font-medium">プラットフォーム</th>
            <th className="px-3 py-2 font-medium">登録日時</th>
            <th className="px-3 py-2 font-medium">最終通信</th>
            <th className="px-3 py-2 font-medium">有効</th>
            <th className="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {devices.map((d) => (
            <tr key={d.id} className="border-t">
              <td className="px-3 py-2 flex items-center gap-2">
                <Smartphone className="w-4 h-4 text-muted-foreground" />
                {d.device_label}
              </td>
              <td className="px-3 py-2">{d.platform ?? '—'}</td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {d.registered_at ? new Date(d.registered_at).toLocaleString('ja-JP') : '—'}
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {d.last_seen_at ? new Date(d.last_seen_at).toLocaleString('ja-JP') : '—'}
              </td>
              <td className="px-3 py-2">{d.enabled ? '✓' : '✕'}</td>
              <td className="px-3 py-2 text-right">
                {d.enabled && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      if (confirm(`"${d.device_label}" を無効化しますか？`)) {
                        disableMutation.mutate(d.id)
                      }
                    }}
                    disabled={disableMutation.isPending}
                  >
                    <Trash2 className="w-3 h-3 mr-1" />
                    無効化
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RegisterDialog({
  open,
  onOpenChange,
  onRegistered,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onRegistered: (resp: MobileDeviceRegisterResponse) => void
}) {
  const queryClient = useQueryClient()
  const [label, setLabel] = useState('')
  const [platform, setPlatform] = useState<'android' | 'ios'>('android')

  useEffect(() => {
    if (open) {
      setLabel('')
      setPlatform('android')
    }
  }, [open])

  const registerMutation = useMutation({
    mutationFn: () => registerMobileDevice({ device_label: label, platform }),
    onSuccess: (resp) => {
      queryClient.invalidateQueries({ queryKey: ['mobile-devices'] })
      toast.success(`登録しました (device_id=${resp.device_id})`)
      onRegistered(resp)
    },
    onError: (err) => toast.error(`登録失敗: ${String(err)}`),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>新規端末のペアリング</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <label className="block">
            <span className="text-xs text-muted-foreground">ラベル (任意の識別子)</span>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="mt-1 w-full border rounded-md px-3 py-1.5 text-sm"
              placeholder="Pixel 9"
              autoFocus
            />
          </label>
          <label className="block">
            <span className="text-xs text-muted-foreground">OS</span>
            <select
              value={platform}
              onChange={(e) => setPlatform(e.target.value as 'android' | 'ios')}
              className="mt-1 w-full border rounded-md px-3 py-1.5 text-sm"
            >
              <option value="android">Android</option>
              <option value="ios">iOS</option>
            </select>
          </label>
          <p className="text-xs text-muted-foreground">
            発行されたシークレットは一度だけ表示されます。そのまま端末で QR を読み取ってください。
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            キャンセル
          </Button>
          <Button
            size="sm"
            onClick={() => registerMutation.mutate()}
            disabled={!label.trim() || registerMutation.isPending}
          >
            発行する
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function QrDialog({
  response,
  onClose,
}: {
  response: MobileDeviceRegisterResponse | null
  onClose: () => void
}) {
  const [dataUrl, setDataUrl] = useState<string | null>(null)

  const payload = useMemo(() => {
    if (!response) return null
    return {
      device_id: response.device_id,
      device_key: response.device_key,
      hmac_secret: response.hmac_secret,
      backend_url: response.backend_url ?? window.location.origin,
      character_version: response.character_version ?? null,
    }
  }, [response])

  useEffect(() => {
    if (!payload) {
      setDataUrl(null)
      return
    }
    const json = JSON.stringify(payload)
    QRCode.toDataURL(json, { width: 320, margin: 1, errorCorrectionLevel: 'M' })
      .then(setDataUrl)
      .catch(() => setDataUrl(null))
  }, [payload])

  return (
    <Dialog
      open={response !== null}
      onOpenChange={(v) => {
        if (!v) onClose()
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>ペアリング QR</DialogTitle>
        </DialogHeader>
        {response && (
          <div className="space-y-3">
            <div className="flex justify-center">
              {dataUrl ? (
                <img src={dataUrl} alt="pairing QR" className="rounded-md border" />
              ) : (
                <div className="w-[320px] h-[320px] bg-muted animate-pulse rounded-md" />
              )}
            </div>
            <div className="text-xs space-y-1">
              <div>
                <span className="text-muted-foreground">device_id:</span>{' '}
                <span className="font-mono">{response.device_id}</span>
              </div>
              <div>
                <span className="text-muted-foreground">backend_url:</span>{' '}
                <span className="font-mono break-all">
                  {response.backend_url ?? '(frontend origin)'}
                </span>
              </div>
              <p className="text-muted-foreground pt-2">
                この画面を閉じると secret は再表示できません。QR を端末で読み取るか、
                この JSON をコピーしてください:
              </p>
              <pre className="rounded bg-muted p-2 overflow-x-auto">
                {JSON.stringify(payload, null, 2)}
              </pre>
            </div>
          </div>
        )}
        <DialogFooter>
          <Button size="sm" onClick={onClose}>閉じる</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
