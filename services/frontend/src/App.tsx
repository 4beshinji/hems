import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Volume2, VolumeX, Zap } from 'lucide-react'
import TaskCard from './components/TaskCard'
import StatusPanel from './components/StatusPanel'
import PCStatusPanel from './components/PCStatusPanel'
import ServiceStatusPanel from './components/ServiceStatusPanel'
import KnowledgeStatusPanel from './components/KnowledgeStatusPanel'
import GASPanel from './components/GASPanel'
import BiometricPanel from './components/BiometricPanel'
import { useAudioQueue, AudioPriority } from './audio'
import {
  fetchTasks,
  fetchStats,
  fetchZones,
  fetchPC,
  fetchServices,
  fetchVoiceEvents,
  fetchKnowledge,
  fetchGAS,
  fetchBiometric,
} from './api'

export type { EnvironmentData, ZoneData, ServiceStatusItem, ServicesData, PCMetrics, KnowledgeData, GASData, BiometricData } from './api'

export default function App() {
  const queryClient = useQueryClient()
  const [audioEnabled, setAudioEnabled] = useState(false)
  const { enqueue, isEnabled } = useAudioQueue(audioEnabled)
  const [playedVoiceIds, setPlayedVoiceIds] = useState<Set<number>>(new Set())
  const [playedTaskIds, setPlayedTaskIds] = useState<Set<number>>(new Set())

  const tasksQuery = useQuery({
    queryKey: ['tasks'],
    queryFn: fetchTasks,
    refetchInterval: 5000,
  })

  const statsQuery = useQuery({
    queryKey: ['stats'],
    queryFn: fetchStats,
    refetchInterval: 10000,
  })

  const zonesQuery = useQuery({
    queryKey: ['zones'],
    queryFn: fetchZones,
    refetchInterval: 5000,
  })

  const pcQuery = useQuery({
    queryKey: ['pc'],
    queryFn: fetchPC,
    refetchInterval: 10000,
  })

  const servicesQuery = useQuery({
    queryKey: ['services'],
    queryFn: fetchServices,
    refetchInterval: 10000,
  })

  const knowledgeQuery = useQuery({
    queryKey: ['knowledge'],
    queryFn: fetchKnowledge,
    refetchInterval: 10000,
  })

  const gasQuery = useQuery({
    queryKey: ['gas'],
    queryFn: fetchGAS,
    refetchInterval: 10000,
  })

  const biometricQuery = useQuery({
    queryKey: ['biometric'],
    queryFn: fetchBiometric,
    refetchInterval: 5000,
  })

  const voiceEventsQuery = useQuery({
    queryKey: ['voiceEvents'],
    queryFn: fetchVoiceEvents,
    refetchInterval: 3000,
    enabled: isEnabled,
  })

  const tasks = tasksQuery.data ?? []
  const stats = statsQuery.data ?? null
  const zones = zonesQuery.data ?? []
  const pcMetrics = pcQuery.data ?? null
  const servicesData = servicesQuery.data ?? null
  const knowledgeData = knowledgeQuery.data ?? null
  const gasData = gasQuery.data ?? null
  const biometricData = biometricQuery.data ?? null

  // Play new voice events
  useEffect(() => {
    if (!isEnabled || !voiceEventsQuery.data) return
    for (const ev of voiceEventsQuery.data) {
      if (!playedVoiceIds.has(ev.id) && ev.audio_url) {
        enqueue(ev.audio_url, AudioPriority.VOICE_EVENT)
        setPlayedVoiceIds(prev => new Set(prev).add(ev.id))
      }
    }
  }, [voiceEventsQuery.data, isEnabled, enqueue, playedVoiceIds])

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

      <KnowledgeStatusPanel knowledge={knowledgeData} />

      <GASPanel gas={gasData} />

      <BiometricPanel biometric={biometricData} />

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
                onComplete={() => queryClient.invalidateQueries({ queryKey: ['tasks'] })}
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
