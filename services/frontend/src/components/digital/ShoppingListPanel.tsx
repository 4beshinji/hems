import { memo, useState, useCallback } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ShoppingCart, Plus, Trash2, Share2, Tag, Store, RotateCcw, ChevronUp } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { ShoppingItem, ShoppingStats } from '@/lib/types'
import {
  addShoppingItem,
  purchaseShoppingItem,
  deleteShoppingItem,
  createShareLink,
} from '@/lib/api'

interface Props {
  items: ShoppingItem[] | null
  stats: ShoppingStats | null
}

const CATEGORY_COLORS: Record<string, string> = {
  '食品': 'bg-green-500/20 text-green-400',
  '日用品': 'bg-blue-500/20 text-blue-400',
  '消耗品': 'bg-yellow-500/20 text-yellow-400',
  '飲料': 'bg-cyan-500/20 text-cyan-400',
  '調味料': 'bg-orange-500/20 text-orange-400',
  '文具': 'bg-purple-500/20 text-purple-400',
}

const PRIORITY_CLASS: Record<number, string> = {
  0: 'text-muted-foreground',
  1: 'text-foreground',
  2: 'text-destructive font-medium',
}

const ShoppingListPanel = memo(function ShoppingListPanel({ items, stats }: Props) {
  const queryClient = useQueryClient()
  const [newItemName, setNewItemName] = useState('')
  const [newItemCategory, setNewItemCategory] = useState('')
  const [newItemStore, setNewItemStore] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)
  const [filterStore, setFilterStore] = useState<string | null>(null)
  const [shareUrl, setShareUrl] = useState<string | null>(null)

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['shopping'] })
    queryClient.invalidateQueries({ queryKey: ['shopping-stats'] })
  }, [queryClient])

  const addMutation = useMutation({
    mutationFn: addShoppingItem,
    onSuccess: invalidate,
  })

  const purchaseMutation = useMutation({
    mutationFn: purchaseShoppingItem,
    onSuccess: invalidate,
  })

  const deleteMutation = useMutation({
    mutationFn: deleteShoppingItem,
    onSuccess: invalidate,
  })

  const handleAdd = useCallback(() => {
    if (!newItemName.trim()) return
    addMutation.mutate({
      name: newItemName.trim(),
      category: newItemCategory || undefined,
      store: newItemStore || undefined,
    })
    setNewItemName('')
    setNewItemCategory('')
    setNewItemStore('')
    setShowAddForm(false)
  }, [newItemName, newItemCategory, newItemStore, addMutation])

  const handleShare = useCallback(async () => {
    try {
      const result = await createShareLink()
      setShareUrl(result.share_url)
      await navigator.clipboard.writeText(result.share_url)
    } catch {
      /* ignore */
    }
  }, [])

  const pending = items?.filter(i => !i.is_purchased) ?? []
  const stores = [...new Set(pending.map(i => i.store).filter(Boolean))] as string[]
  const filtered = filterStore ? pending.filter(i => i.store === filterStore) : pending

  // Group by category
  const grouped = filtered.reduce<Record<string, ShoppingItem[]>>((acc, item) => {
    const cat = item.category || '未分類'
    if (!acc[cat]) acc[cat] = []
    acc[cat].push(item)
    return acc
  }, {})

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <ShoppingCart className="h-4 w-4 text-chart-blue" />
            買い物リスト
            {stats && stats.pending_items > 0 && (
              <Badge variant="secondary" className="text-[10px] px-1.5">
                {stats.pending_items}
              </Badge>
            )}
          </CardTitle>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={handleShare}
              title="共有リンク作成"
            >
              <Share2 className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => setShowAddForm(!showAddForm)}
            >
              {showAddForm ? (
                <ChevronUp className="h-3.5 w-3.5" />
              ) : (
                <Plus className="h-3.5 w-3.5" />
              )}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Share URL notification */}
        {shareUrl && (
          <div className="text-xs text-muted-foreground bg-muted/50 rounded p-2">
            共有リンクをコピーしました
          </div>
        )}

        {/* Add form */}
        {showAddForm && (
          <div className="space-y-2 pb-2 border-b border-border">
            <input
              type="text"
              placeholder="アイテム名"
              value={newItemName}
              onChange={e => setNewItemName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleAdd()}
              className="w-full h-8 px-2 text-xs rounded border border-border bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="カテゴリ"
                value={newItemCategory}
                onChange={e => setNewItemCategory(e.target.value)}
                className="flex-1 h-8 px-2 text-xs rounded border border-border bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              />
              <input
                type="text"
                placeholder="店舗"
                value={newItemStore}
                onChange={e => setNewItemStore(e.target.value)}
                className="flex-1 h-8 px-2 text-xs rounded border border-border bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </div>
            <Button
              size="sm"
              onClick={handleAdd}
              disabled={!newItemName.trim()}
              className="w-full h-7 text-xs"
            >
              追加
            </Button>
          </div>
        )}

        {/* Store filter */}
        {stores.length > 0 && (
          <div className="flex gap-1 flex-wrap">
            <button
              className={`text-[10px] px-2 py-0.5 rounded-full transition-colors ${
                !filterStore
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-muted/80'
              }`}
              onClick={() => setFilterStore(null)}
            >
              全店舗
            </button>
            {stores.map(s => (
              <button
                key={s}
                className={`text-[10px] px-2 py-0.5 rounded-full transition-colors ${
                  filterStore === s
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-muted-foreground hover:bg-muted/80'
                }`}
                onClick={() => setFilterStore(filterStore === s ? null : s)}
              >
                <Store className="inline h-2.5 w-2.5 mr-0.5" />
                {s}
              </button>
            ))}
          </div>
        )}

        {/* Item groups */}
        {Object.keys(grouped).length === 0 ? (
          <p className="text-xs text-muted-foreground py-4 text-center">
            リストは空です
          </p>
        ) : (
          Object.entries(grouped).map(([category, categoryItems]) => (
            <div key={category}>
              <div className="flex items-center gap-1.5 mb-1">
                <Tag className="h-3 w-3 text-muted-foreground" />
                <span
                  className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                    CATEGORY_COLORS[category] || 'bg-muted text-muted-foreground'
                  }`}
                >
                  {category}
                </span>
                <span className="text-[10px] text-muted-foreground">
                  {categoryItems.length}
                </span>
              </div>
              {categoryItems.map(item => (
                <div key={item.id} className="flex items-center gap-2 py-1 group">
                  <input
                    type="checkbox"
                    className="h-3.5 w-3.5 rounded border-border accent-primary cursor-pointer"
                    checked={false}
                    onChange={() => purchaseMutation.mutate(item.id)}
                  />
                  <span
                    className={`text-xs flex-1 truncate ${PRIORITY_CLASS[item.priority] || ''}`}
                  >
                    {item.name}
                    {item.quantity > 1 && (
                      <span className="text-muted-foreground ml-1">
                        x{item.quantity}
                        {item.unit || ''}
                      </span>
                    )}
                    {item.quantity === 1 && item.unit && (
                      <span className="text-muted-foreground ml-1">{item.unit}</span>
                    )}
                  </span>
                  {item.is_recurring && (
                    <span title={`${item.recurrence_days}日ごと`}>
                      <RotateCcw className="h-3 w-3 text-muted-foreground" />
                    </span>
                  )}
                  {item.store && (
                    <span className="text-[9px] text-muted-foreground bg-muted px-1 rounded">
                      {item.store}
                    </span>
                  )}
                  {item.price != null && (
                    <span className="text-[10px] text-muted-foreground">
                      ¥{item.price}
                    </span>
                  )}
                  <button
                    className="opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={() => deleteMutation.mutate(item.id)}
                  >
                    <Trash2 className="h-3 w-3 text-muted-foreground hover:text-destructive" />
                  </button>
                </div>
              ))}
            </div>
          ))
        )}

        {/* Stats footer */}
        {stats && stats.total_spent_this_month > 0 && (
          <div className="pt-2 border-t border-border flex justify-between text-[10px] text-muted-foreground">
            <span>今月の支出</span>
            <span className="font-medium">
              ¥{stats.total_spent_this_month.toLocaleString()}
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  )
})

export default ShoppingListPanel
