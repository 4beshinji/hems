import type {
  ZoneSnapshot,
  TaskData,
  TaskCreatePayload,
  TimelineData,
  VoiceEvent,
  SystemStatsResponse,
  PCMetrics,
  ServicesData,
  KnowledgeData,
  GASData,
  BiometricData,
  PerceptionData,
  HomeData,
  WeatherData,
  NewsData,
  DeviceActionEvent,
  TimeSeriesPoint,
  ShoppingItem,
  ShoppingStats,
  PurchaseHistoryItem,
  ChatResponse,
  BrainStatus,
  OllamaModel,
  PowerMode,
  BatchTaskName,
  Device,
  DeviceCreate,
  DeviceUpdate,
  DeviceControlRequest,
  DeviceControlResponse,
  Scene,
  SceneCreate,
  SceneUpdate,
  SceneExecuteResponse,
  AutomationRule,
  AutomationRuleCreate,
  AutomationRuleUpdate,
  AutomationTestResponse,
  FrequentPlace,
  FrequentPlaceCreate,
  FrequentPlaceUpdate,
  MobileDevice,
  MobileDeviceRegisterRequest,
  MobileDeviceRegisterResponse,
} from './types'

// In production, nginx proxies /api/ → backend (with auth header injected).
// In dev, set VITE_BACKEND_URL to point at the backend directly (e.g. http://localhost:8010).
// Same variable is used by vite.config.ts as the dev proxy target.
const BASE = (import.meta.env.VITE_BACKEND_URL as string | undefined) ?? '/api'

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

export function createTask(payload: TaskCreatePayload): Promise<TaskData> {
  return post('/tasks/', payload)
}

export function dismissTask(id: number, reason?: string): Promise<TaskData> {
  return post(`/tasks/${id}/dismiss`, { reason: reason ?? null })
}

export function lockTask(id: number, lockedStart: string): Promise<TaskData> {
  return post(`/tasks/${id}/lock`, { locked_start: lockedStart })
}

// ─── Timeline ────────────────────────────────────────────────────────────────
export function fetchTimelineToday(): Promise<TimelineData> {
  return get('/timeline/today')
}

export function fetchTimelineDay(date: string): Promise<TimelineData> {
  return get(`/timeline/day?date=${date}`)
}

// ─── Voice Events ─────────────────────────────────────────────────────────────
export function fetchVoiceEvents(): Promise<VoiceEvent[]> {
  return get('/voice-events/recent')
}

export function fetchAlertHistory(hours = 168): Promise<VoiceEvent[]> {
  return get(`/voice-events/alerts?hours=${hours}`)
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

// ─── Weather ──────────────────────────────────────────────────────────────────
export function fetchWeather(): Promise<WeatherData> {
  return get('/weather/')
}

// ─── News ─────────────────────────────────────────────────────────────────────
export function fetchNews(): Promise<NewsData> {
  return get('/news/')
}

// ─── Device actions log ──────────────────────────────────────────────────────
export function fetchDeviceActions(params?: {
  hours?: number
  device_id?: string
  limit?: number
}): Promise<{ actions: DeviceActionEvent[] }> {
  const qs = new URLSearchParams()
  if (params?.hours) qs.set('hours', String(params.hours))
  if (params?.device_id) qs.set('device_id', params.device_id)
  if (params?.limit) qs.set('limit', String(params.limit))
  const q = qs.toString()
  return get(`/device-actions/${q ? `?${q}` : ''}`)
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

// ─── Brain / Power mode ───────────────────────────────────────────────────────
export function fetchBrainStatus(): Promise<BrainStatus> {
  return get('/brain/power-mode')
}

export function setPowerMode(mode: PowerMode): Promise<{ ok: boolean; mode: PowerMode }> {
  return post('/brain/power-mode', { mode })
}

export function fetchOllamaModels(): Promise<{ models: OllamaModel[] }> {
  return get('/brain/ollama/models')
}

export function runBatch(
  tasks: BatchTaskName[],
  model: string | null,
): Promise<{ ok: boolean; tasks: string[]; labels: string[]; model: string | null }> {
  return post('/brain/batch', { tasks, model })
}

// ─── Character ──────────────────────────────────────────────────────────────
export function fetchCharacter(): Promise<Record<string, unknown>> {
  return get('/character/')
}

// ─── Chat ───────────────────────────────────────────────────────────────────
export function sendChatMessage(
  content: string,
  conversationId?: number,
  tts?: boolean,
): Promise<ChatResponse> {
  return post('/chat/', {
    content,
    conversation_id: conversationId ?? null,
    tts: tts ?? null,
  })
}

// ─── Devices ────────────────────────────────────────────────────────────────
export function fetchDevices(params?: {
  kind?: string
  vendor?: string
  zone?: string
  enabled_only?: boolean
}): Promise<Device[]> {
  const query = new URLSearchParams()
  if (params?.kind) query.set('kind', params.kind)
  if (params?.vendor) query.set('vendor', params.vendor)
  if (params?.zone) query.set('zone', params.zone)
  if (params?.enabled_only) query.set('enabled_only', 'true')
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return get(`/devices/${suffix}`)
}

export function fetchDevice(deviceId: string): Promise<Device> {
  return get(`/devices/${encodeURIComponent(deviceId)}`)
}

export function createDevice(payload: DeviceCreate): Promise<Device> {
  return post('/devices/', payload)
}

export function updateDevice(deviceId: string, payload: DeviceUpdate): Promise<Device> {
  return put(`/devices/${encodeURIComponent(deviceId)}`, payload)
}

export function deleteDevice(deviceId: string): Promise<{ success: boolean }> {
  return del(`/devices/${encodeURIComponent(deviceId)}`)
}

export function controlDevice(
  deviceId: string,
  payload: DeviceControlRequest,
): Promise<DeviceControlResponse> {
  return post(`/devices/${encodeURIComponent(deviceId)}/control`, payload)
}

export function zigbeePermitJoin(
  enable: boolean,
  durationS: number = 60,
): Promise<DeviceControlResponse> {
  return post('/devices/zigbee/permit_join', { enable, duration_s: durationS })
}

// ─── Scenes ─────────────────────────────────────────────────────────────────
export function fetchScenes(enabledOnly = false): Promise<Scene[]> {
  return get(`/scenes/${enabledOnly ? '?enabled_only=true' : ''}`)
}

export function createScene(payload: SceneCreate): Promise<Scene> {
  return post('/scenes/', payload)
}

export function updateScene(id: number, payload: SceneUpdate): Promise<Scene> {
  return put(`/scenes/${id}`, payload)
}

export function deleteScene(id: number): Promise<{ success: boolean }> {
  return del(`/scenes/${id}`)
}

export function executeScene(id: number): Promise<SceneExecuteResponse> {
  return post(`/scenes/${id}/execute`, {})
}

// ─── Automation rules ──────────────────────────────────────────────────────
export function fetchAutomations(enabledOnly = false): Promise<AutomationRule[]> {
  return get(`/automations/${enabledOnly ? '?enabled_only=true' : ''}`)
}

export function createAutomation(payload: AutomationRuleCreate): Promise<AutomationRule> {
  return post('/automations/', payload)
}

export function updateAutomation(
  id: number,
  payload: AutomationRuleUpdate,
): Promise<AutomationRule> {
  return put(`/automations/${id}`, payload)
}

export function deleteAutomation(id: number): Promise<{ success: boolean }> {
  return del(`/automations/${id}`)
}

export function testAutomation(id: number): Promise<AutomationTestResponse> {
  return post(`/automations/${id}/test`, {})
}

// ─── Frequent Places ────────────────────────────────────────────────────────
export function fetchFrequentPlaces(enabledOnly = false): Promise<FrequentPlace[]> {
  return get(`/frequent-places/${enabledOnly ? '?enabled_only=true' : ''}`)
}

export function createFrequentPlace(payload: FrequentPlaceCreate): Promise<FrequentPlace> {
  return post('/frequent-places/', payload)
}

export function updateFrequentPlace(
  id: number,
  payload: FrequentPlaceUpdate,
): Promise<FrequentPlace> {
  return put(`/frequent-places/${id}`, payload)
}

export function deleteFrequentPlace(id: number): Promise<{ deleted: boolean }> {
  return del(`/frequent-places/${id}`)
}

// ─── Mobile devices ─────────────────────────────────────────────────────────
export function fetchMobileDevices(): Promise<MobileDevice[]> {
  return get('/mobile/devices')
}

export function registerMobileDevice(
  payload: MobileDeviceRegisterRequest,
): Promise<MobileDeviceRegisterResponse> {
  return post('/mobile/register', payload)
}

export function disableMobileDevice(id: number): Promise<{ disabled: boolean }> {
  return del(`/mobile/devices/${id}`)
}
