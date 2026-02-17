import { useState, useEffect, useCallback } from 'react'
import { Volume2, VolumeX, Zap } from 'lucide-react'
import TaskCard from './components/TaskCard'
import StatusPanel from './components/StatusPanel'
import PCStatusPanel from './components/PCStatusPanel'
import ServiceStatusPanel from './components/ServiceStatusPanel'
import { useAudioQueue, AudioPriority } from './audio'

const API_BASE = '/api'

interface TaskData {
  id: number
  title: string
  description?: string
  location?: string
  xp_reward: number
  is_completed: boolean
  urgency: number
  zone?: string
  task_type?: string[]
  estimated_duration?: number
  announcement_audio_url?: string
  completion_audio_url?: string
  assigned_to?: number | null
  accepted_at?: string | null
  report_status?: string | null
  completion_note?: string | null
}

interface StatsData {
  total_xp: number
  tasks_completed: number
  tasks_created: number
  tasks_active: number
}

interface VoiceEvent {
  id: number
  message: string
  audio_url: string
  zone?: string
  tone: string
}

export interface EnvironmentData {
  temperature?: number | null
  humidity?: number | null
  co2?: number | null
  pressure?: number | null
  light?: number | null
  voc?: number | null
  last_update?: number | null
}

export interface ZoneData {
  zone_id: string
  environment: EnvironmentData
  occupancy: { count: number; last_update?: number | null }
  events: { type: string; description: string; severity: number; timestamp: number }[]
}

export interface ServiceStatusItem {
  name: string
  available: boolean
  unread_count: number
  summary: string
  last_check: number
  error?: string | null
}

export interface ServicesData {
  status?: string
  [key: string]: ServiceStatusItem | string | undefined
}

export interface PCMetrics {
  status?: string
  cpu?: { usage_percent: number; core_count: number; temp_c: number }
  memory?: { used_gb: number; total_gb: number; percent: number }
  gpu?: { usage_percent: number; vram_used_gb: number; vram_total_gb: number; temp_c: number }
  disk?: { mount: string; used_gb: number; total_gb: number; percent: number }[]
  top_processes?: { pid: number; name: string; cpu_percent: number; mem_mb: number }[]
  bridge_connected?: boolean
}

export default function App() {
  const [tasks, setTasks] = useState<TaskData[]>([])
  const [stats, setStats] = useState<StatsData | null>(null)
  const [zones, setZones] = useState<ZoneData[]>([])
  const [pcMetrics, setPcMetrics] = useState<PCMetrics | null>(null)
  const [servicesData, setServicesData] = useState<ServicesData | null>(null)
  const [audioEnabled, setAudioEnabled] = useState(false)
  const { enqueue, isEnabled } = useAudioQueue(audioEnabled)
  const [playedVoiceIds, setPlayedVoiceIds] = useState<Set<number>>(new Set())
  const [playedTaskIds, setPlayedTaskIds] = useState<Set<number>>(new Set())

  const fetchTasks = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/tasks/`)
      if (resp.ok) setTasks(await resp.json())
    } catch {}
  }, [])

  const fetchStats = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/tasks/stats`)
      if (resp.ok) setStats(await resp.json())
    } catch {}
  }, [])

  const fetchZones = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/zones/`)
      if (resp.ok) setZones(await resp.json())
    } catch {}
  }, [])

  const fetchPC = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/pc/`)
      if (resp.ok) setPcMetrics(await resp.json())
    } catch {}
  }, [])

  const fetchServices = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/services/`)
      if (resp.ok) setServicesData(await resp.json())
    } catch {}
  }, [])

  const fetchVoiceEvents = useCallback(async () => {
    if (!isEnabled) return
    try {
      const resp = await fetch(`${API_BASE}/voice-events/recent`)
      if (!resp.ok) return
      const events: VoiceEvent[] = await resp.json()
      for (const ev of events) {
        if (!playedVoiceIds.has(ev.id) && ev.audio_url) {
          enqueue(ev.audio_url, AudioPriority.VOICE_EVENT)
          setPlayedVoiceIds(prev => new Set(prev).add(ev.id))
        }
      }
    } catch {}
  }, [isEnabled, enqueue, playedVoiceIds])

  // Auto-play task announcements
  useEffect(() => {
    if (!isEnabled) return
    for (const task of tasks) {
      if (!task.is_completed && task.announcement_audio_url && !playedTaskIds.has(task.id)) {
        enqueue(task.announcement_audio_url, AudioPriority.ANNOUNCEMENT)
        setPlayedTaskIds(prev => new Set(prev).add(task.id))
      }
    }
  }, [tasks, isEnabled, enqueue, playedTaskIds])

  // Polling
  useEffect(() => {
    fetchTasks()
    fetchStats()
    fetchZones()
    fetchPC()
    fetchServices()
    const interval = setInterval(() => {
      fetchTasks()
      fetchStats()
      fetchZones()
      fetchPC()
      fetchServices()
      fetchVoiceEvents()
    }, 5000)
    return () => clearInterval(interval)
  }, [fetchTasks, fetchStats, fetchZones, fetchPC, fetchServices, fetchVoiceEvents])

  const activeTasks = tasks.filter(t => !t.is_completed)

  return (
    <div className="min-h-screen p-6">
      <header className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">HEMS Dashboard</h1>
          <p className="text-gray-500 mt-1">Home Environment Management System</p>
        </div>
        <div className="flex items-center gap-4">
          {stats && (
            <div className="flex items-center gap-2 bg-white rounded-lg px-4 py-2 elevation-1">
              <Zap className="w-5 h-5 text-purple-600" />
              <span className="font-bold text-purple-700">{stats.total_xp} XP</span>
              <span className="text-gray-400 mx-2">|</span>
              <span className="text-sm text-gray-600">{stats.tasks_completed} completed</span>
            </div>
          )}
          <button
            onClick={() => setAudioEnabled(!audioEnabled)}
            className={`p-3 rounded-full transition-all ${
              audioEnabled ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-500'
            }`}
          >
            {audioEnabled ? <Volume2 className="w-5 h-5" /> : <VolumeX className="w-5 h-5" />}
          </button>
        </div>
      </header>

      <StatusPanel zones={zones} />

      <PCStatusPanel pc={pcMetrics} />

      <ServiceStatusPanel services={servicesData} />

      <section className="mt-8">
        <h2 className="text-xl font-semibold text-gray-800 mb-4">
          Active Tasks ({activeTasks.length})
        </h2>
        {activeTasks.length === 0 ? (
          <div className="bg-white rounded-xl elevation-1 p-12 text-center text-gray-400">
            No active tasks
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {activeTasks.map(task => (
              <TaskCard
                key={task.id}
                task={task}
                onComplete={fetchTasks}
                enqueueAudio={enqueue}
                audioEnabled={isEnabled}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
