// ─── Shopping List ───────────────────────────────────────────────────────────
export interface ShoppingItem {
  id: number
  name: string
  category?: string | null
  quantity: number
  unit?: string | null
  store?: string | null
  store_category?: string | null   // brain classifier output (drugstore/supermarket/...)
  price?: number | null
  is_purchased: boolean
  is_recurring: boolean
  recurrence_days?: number | null
  last_purchased_at?: string | null
  next_purchase_at?: string | null
  notes?: string | null
  priority: number
  created_at?: string | null
  purchased_at?: string | null
  created_by: string
  share_token?: string | null
}

export interface ShoppingStats {
  total_items: number
  purchased_items: number
  pending_items: number
  total_spent_this_month: number
  category_breakdown: Record<string, number>
}

export interface PurchaseHistoryItem {
  id: number
  item_name: string
  category?: string | null
  store?: string | null
  price?: number | null
  quantity: number
  purchased_at?: string | null
}
