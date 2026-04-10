import { apiFetch } from '@/lib/api-client'
import type { ShoppingItem, ShoppingStats } from '@/lib/types'

export const fetchShopping = (includePurchased = false): Promise<ShoppingItem[]> =>
  apiFetch(`/shopping/?include_purchased=${includePurchased}`)

export const fetchShoppingStats = (): Promise<ShoppingStats> =>
  apiFetch('/shopping/stats')

export const addShoppingItem = (data: {
  name: string
  category?: string
  store?: string
  quantity?: number
  unit?: string
  price?: number
  priority?: number
  notes?: string
  is_recurring?: boolean
  recurrence_days?: number
}): Promise<ShoppingItem> =>
  apiFetch('/shopping/', {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const purchaseShoppingItem = (itemId: number): Promise<ShoppingItem> =>
  apiFetch(`/shopping/${itemId}/purchase`, { method: 'PUT' })

export const deleteShoppingItem = (itemId: number): Promise<{ success: boolean }> =>
  apiFetch(`/shopping/${itemId}`, { method: 'DELETE' })

export const createShareLink = (): Promise<{ share_url: string; token: string }> =>
  apiFetch('/shopping/0/share', { method: 'POST' })
