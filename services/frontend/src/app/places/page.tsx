import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus, RefreshCw, Trash2 } from 'lucide-react'
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
  createFrequentPlace,
  deleteFrequentPlace,
  fetchFrequentPlaces,
  updateFrequentPlace,
} from '@/lib/api'
import type {
  FrequentPlace,
  FrequentPlaceCategory,
  FrequentPlaceCreate,
} from '@/lib/types'

const CATEGORY_OPTIONS: { value: FrequentPlaceCategory; label: string }[] = [
  { value: 'drugstore', label: 'ドラッグストア' },
  { value: 'supermarket', label: 'スーパー' },
  { value: 'convenience', label: 'コンビニ' },
  { value: 'home_center', label: 'ホームセンター' },
  { value: 'other', label: 'その他' },
]

const BLANK: FrequentPlaceCreate = {
  label: '',
  category: 'supermarket',
  lat: 0,
  lon: 0,
  radius_m: 200,
  enabled: true,
  cooldown_min: 60,
}

export default function FrequentPlacesPage() {
  const query = useQuery<FrequentPlace[]>({
    queryKey: ['frequent-places'],
    queryFn: () => fetchFrequentPlaces(),
    refetchInterval: 30_000,
  })

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<FrequentPlace | null>(null)

  const openNew = () => {
    setEditing(null)
    setDialogOpen(true)
  }

  const openEdit = (place: FrequentPlace) => {
    setEditing(place)
    setDialogOpen(true)
  }

  return (
    <div className="p-4 md:p-6 space-y-4 max-w-5xl mx-auto">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">よく行く場所</h1>
          <p className="text-sm text-muted-foreground">
            モバイルコンパニオンの geofence リマインド用の登録地点
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
          <Button size="sm" onClick={openNew}>
            <Plus className="w-4 h-4 mr-1" />
            追加
          </Button>
        </div>
      </header>

      {query.isLoading && <LoadingState />}
      {query.isError && <ErrorState message={String(query.error)} />}

      {query.data && (
        <PlacesTable places={query.data} onEdit={openEdit} />
      )}

      <PlaceEditDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        place={editing}
      />
    </div>
  )
}

function PlacesTable({
  places,
  onEdit,
}: {
  places: FrequentPlace[]
  onEdit: (p: FrequentPlace) => void
}) {
  if (places.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
        場所が登録されていません。「追加」から最初の1件を登録してください。
      </div>
    )
  }
  return (
    <div className="overflow-hidden border rounded-lg">
      <table className="w-full text-sm">
        <thead className="bg-muted/50">
          <tr className="text-left">
            <th className="px-3 py-2 font-medium">ラベル</th>
            <th className="px-3 py-2 font-medium">カテゴリ</th>
            <th className="px-3 py-2 font-medium">座標</th>
            <th className="px-3 py-2 font-medium">半径 / cooldown</th>
            <th className="px-3 py-2 font-medium">有効</th>
          </tr>
        </thead>
        <tbody>
          {places.map((p) => (
            <tr
              key={p.id}
              className="border-t cursor-pointer hover:bg-muted/30"
              onClick={() => onEdit(p)}
            >
              <td className="px-3 py-2">{p.label}</td>
              <td className="px-3 py-2">
                {CATEGORY_OPTIONS.find((c) => c.value === p.category)?.label ?? p.category}
              </td>
              <td className="px-3 py-2 font-mono text-xs">
                {p.lat.toFixed(5)}, {p.lon.toFixed(5)}
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {p.radius_m}m / {p.cooldown_min}min
              </td>
              <td className="px-3 py-2">{p.enabled ? '✓' : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function PlaceEditDialog({
  open,
  onOpenChange,
  place,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  place: FrequentPlace | null
}) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<FrequentPlaceCreate>(BLANK)
  const [confirmDelete, setConfirmDelete] = useState(false)

  useEffect(() => {
    if (!open) return
    if (place) {
      setForm({
        label: place.label,
        category: place.category,
        lat: place.lat,
        lon: place.lon,
        radius_m: place.radius_m,
        enabled: place.enabled,
        cooldown_min: place.cooldown_min,
      })
    } else {
      setForm(BLANK)
    }
    setConfirmDelete(false)
  }, [open, place])

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (place) {
        return updateFrequentPlace(place.id, form)
      }
      return createFrequentPlace(form)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['frequent-places'] })
      toast.success(place ? '更新しました' : '追加しました')
      onOpenChange(false)
    },
    onError: (err) => toast.error(`保存失敗: ${String(err)}`),
  })

  const deleteMutation = useMutation({
    mutationFn: async () => {
      if (!place) throw new Error('No place')
      return deleteFrequentPlace(place.id)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['frequent-places'] })
      toast.success('削除しました')
      onOpenChange(false)
    },
    onError: (err) => toast.error(`削除失敗: ${String(err)}`),
  })

  const valid = useMemo(() => {
    if (!form.label.trim()) return false
    if (Number.isNaN(form.lat) || Number.isNaN(form.lon)) return false
    if (Math.abs(form.lat) > 90 || Math.abs(form.lon) > 180) return false
    if ((form.radius_m ?? 0) <= 0) return false
    return true
  }, [form])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{place ? '場所を編集' : '場所を追加'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <Field label="ラベル">
            <input
              type="text"
              value={form.label}
              onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
              className="w-full border rounded-md px-3 py-1.5 text-sm"
              placeholder="近所のスギ薬局"
            />
          </Field>
          <Field label="カテゴリ">
            <select
              value={form.category}
              onChange={(e) =>
                setForm((f) => ({ ...f, category: e.target.value as FrequentPlaceCategory }))
              }
              className="w-full border rounded-md px-3 py-1.5 text-sm"
            >
              {CATEGORY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="緯度 (lat)">
              <input
                type="number"
                step="0.000001"
                value={form.lat}
                onChange={(e) =>
                  setForm((f) => ({ ...f, lat: parseFloat(e.target.value) }))
                }
                className="w-full border rounded-md px-3 py-1.5 text-sm"
              />
            </Field>
            <Field label="経度 (lon)">
              <input
                type="number"
                step="0.000001"
                value={form.lon}
                onChange={(e) =>
                  setForm((f) => ({ ...f, lon: parseFloat(e.target.value) }))
                }
                className="w-full border rounded-md px-3 py-1.5 text-sm"
              />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="半径 (m)">
              <input
                type="number"
                min={50}
                max={2000}
                value={form.radius_m ?? 200}
                onChange={(e) =>
                  setForm((f) => ({ ...f, radius_m: parseInt(e.target.value) || 200 }))
                }
                className="w-full border rounded-md px-3 py-1.5 text-sm"
              />
            </Field>
            <Field label="クールダウン (分)">
              <input
                type="number"
                min={1}
                max={1440}
                value={form.cooldown_min ?? 60}
                onChange={(e) =>
                  setForm((f) => ({ ...f, cooldown_min: parseInt(e.target.value) || 60 }))
                }
                className="w-full border rounded-md px-3 py-1.5 text-sm"
              />
            </Field>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.enabled ?? true}
              onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
            />
            有効化
          </label>
        </div>

        <DialogFooter className="gap-2">
          {place && (
            confirmDelete ? (
              <Button
                variant="destructive"
                size="sm"
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
              >
                <Trash2 className="w-4 h-4 mr-1" />
                本当に削除
              </Button>
            ) : (
              <Button variant="outline" size="sm" onClick={() => setConfirmDelete(true)}>
                <Trash2 className="w-4 h-4 mr-1" />
                削除
              </Button>
            )
          )}
          <div className="flex-1" />
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            キャンセル
          </Button>
          <Button
            size="sm"
            onClick={() => saveMutation.mutate()}
            disabled={!valid || saveMutation.isPending}
          >
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-xs text-muted-foreground">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  )
}
