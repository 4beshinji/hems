import type {
  ZoneSnapshot,
  TaskData,
  VoiceEvent,
  SystemStatsResponse,
  PCMetrics,
  ServicesData,
  KnowledgeData,
  GASData,
  BiometricData,
  PerceptionData,
  HomeData,
  TimeSeriesPoint,
  ShoppingItem,
  ShoppingStats,
  PurchaseHistoryItem,
  ChatResponse,
} from './types'

// In production, nginx proxies /api/ → backend (with auth header injected).
// In dev, set VITE_API_BASE to point at the backend directly (e.g. http://localhost:8010).
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

async function put<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

// ─── Zones ────────────────────────────────────────────────────────────────────
export function fetchZones(): Promise<ZoneSnapshot[]> {
  return get('/zones/')
}

// ─── Tasks ────────────────────────────────────────────────────────────────────
export function fetchTasks(): Promise<TaskData[]> {
  return get('/tasks/')
}

export function fetchStats(): Promise<SystemStatsResponse> {
  return get('/tasks/stats')
}

export function completeTask(
  id: number,
  reportStatus?: string,
  completionNote?: string,
): Promise<TaskData> {
  return put(`/tasks/${id}/complete`, {
    report_status: reportStatus ?? null,
    completion_note: completionNote ?? null,
  })
}

// ─── Voice Events ─────────────────────────────────────────────────────────────
export function fetchVoiceEvents(): Promise<VoiceEvent[]> {
  return get('/voice-events/recent')
}

// ─── PC Metrics ───────────────────────────────────────────────────────────────
export function fetchPC(): Promise<PCMetrics> {
  return get('/pc/')
}

// ─── Services ─────────────────────────────────────────────────────────────────
export function fetchServices(): Promise<ServicesData> {
  return get('/services/')
}

// ─── Knowledge ────────────────────────────────────────────────────────────────
export function fetchKnowledge(): Promise<KnowledgeData> {
  return get('/knowledge/')
}

// ─── GAS ──────────────────────────────────────────────────────────────────────
export function fetchGAS(): Promise<GASData> {
  return get('/gas/')
}

// ─── Biometrics ───────────────────────────────────────────────────────────────
export function fetchBiometric(): Promise<BiometricData> {
  return get('/biometric/')
}

// ─── Perception ───────────────────────────────────────────────────────────────
export function fetchPerception(): Promise<PerceptionData> {
  return get('/perception/')
}

// ─── Home Assistant ───────────────────────────────────────────────────────────
export function fetchHome(): Promise<HomeData> {
  return get('/home/')
}

export function controlLight(
  entityId: string,
  on: boolean,
  brightness?: number,
): Promise<{ success: boolean; result: string }> {
  return post('/home/light/control', { entity_id: entityId, on, brightness })
}

export function controlClimate(
  entityId: string,
  mode?: string,
  temperature?: number,
): Promise<{ success: boolean; result: string }> {
  return post('/home/climate/control', { entity_id: entityId, mode, temperature })
}

/** action: 'open' | 'close' | 'stop' */
export function controlCover(
  entityId: string,
  action?: string,
  position?: number,
): Promise<{ success: boolean; result: string }> {
  return post('/home/cover/control', { entity_id: entityId, action, position })
}

// ─── Time Series ──────────────────────────────────────────────────────────────
export function fetchTimeSeries(
  metric: string,
  zone?: string,
  hours = 24,
): Promise<TimeSeriesPoint[]> {
  const params = new URLSearchParams({ metric, hours: String(hours) })
  if (zone) params.set('zone', zone)
  return get(`/timeseries/?${params}`)
}

// ─── Shopping ────────────────────────────────────────────────────────────────
export function fetchShopping(params?: {
  category?: string
  store?: string
  include_purchased?: boolean
}): Promise<ShoppingItem[]> {
  const qs = new URLSearchParams()
  if (params?.category) qs.set('category', params.category)
  if (params?.store) qs.set('store', params.store)
  if (params?.include_purchased) qs.set('include_purchased', 'true')
  const q = qs.toString()
  return get(`/shopping/${q ? `?${q}` : ''}`)
}

export function addShoppingItem(item: {
  name: string
  category?: string
  quantity?: number
  unit?: string
  store?: string
  price?: number
  is_recurring?: boolean
  recurrence_days?: number
  notes?: string
  priority?: number
}): Promise<ShoppingItem> {
  return post('/shopping/', item)
}

export function updateShoppingItem(
  id: number,
  updates: Partial<ShoppingItem>,
): Promise<ShoppingItem> {
  return put(`/shopping/${id}`, updates)
}

export function purchaseShoppingItem(id: number): Promise<ShoppingItem> {
  return put(`/shopping/${id}/purchase`)
}

export function deleteShoppingItem(
  id: number,
): Promise<{ success: boolean }> {
  return del(`/shopping/${id}`)
}

export function fetchShoppingStats(): Promise<ShoppingStats> {
  return get('/shopping/stats')
}

export function fetchShoppingCategories(): Promise<string[]> {
  return get('/shopping/categories')
}

export function fetchShoppingStores(): Promise<string[]> {
  return get('/shopping/stores')
}

export function fetchPurchaseHistory(
  days?: number,
): Promise<PurchaseHistoryItem[]> {
  return get(`/shopping/history${days ? `?days=${days}` : ''}`)
}

export function createShareLink(): Promise<{
  share_url: string
  token: string
}> {
  return post('/shopping/0/share', {})
}

// ─── Character ──────────────────────────────────────────────────────────────
export function fetchCharacter(): Promise<Record<string, unknown>> {
  return get('/character/')
}

// ─── Chat ───────────────────────────────────────────────────────────────────
export function sendChatMessage(
  content: string,
  conversationId?: number,
): Promise<ChatResponse> {
  return post('/chat/', { content, conversation_id: conversationId ?? null })
}
