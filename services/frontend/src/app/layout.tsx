import { useState, useEffect, useRef, useCallback, lazy, Suspense } from 'react'
import { Outlet } from 'react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import AppSidebar from '@/components/layout/AppSidebar'
import BottomNav from '@/components/layout/BottomNav'
import Header from '@/components/layout/Header'
import { useDarkMode } from '@/hooks/use-dark-mode'
import { useCharacterTheme } from '@/hooks/use-character-theme'
import { useAvatarMode } from '@/hooks/use-avatar-mode'
import { useSTTMode } from '@/hooks/use-stt-mode'
import { usePowerMode } from '@/hooks/use-power-mode'
import { useAudioQueue, AudioPriority } from '@/audio'
import { fetchZones, fetchVoiceEvents, fetchTasks } from '@/lib/api'
import type { VoiceEvent, TaskData } from '@/lib/types'
import type { STTMode } from '@/hooks/use-server-stt'
import BatchDialog from '@/components/brain/BatchDialog'

const AvatarContainer = lazy(() => import('@/components/vrm/AvatarContainer'))
const PsdTestPanel    = lazy(() => import('@/components/psd/PsdTestPanel').then(m => ({ default: m.PsdTestPanel })))

const MAX_PLAYED_IDS = 500
const TRIM_TO = 50

function useKioskMode() {
  const isKiosk = new URLSearchParams(window.location.search).has('kiosk')
  useEffect(() => {
    if (!isKiosk) return
    let wakeLock: WakeLockSentinel | null = null
    const acquire = async () => {
      try {
        wakeLock = await navigator.wakeLock.request('screen')
      } catch { /* not supported */ }
    }
    acquire()
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') acquire()
    })
    return () => { wakeLock?.release() }
  }, [isKiosk])
  return isKiosk
}

export default function AppLayout() {
  const queryClient = useQueryClient()
  const [audioEnabled, setAudioEnabled] = useState(false)
  const { enqueue, isEnabled } = useAudioQueue(audioEnabled)
  const { mode: avatarMode, cycle: cycleAvatarMode, setMode: setAvatarMode } = useAvatarMode()
  const { mode: sttMode, cycle: cycleSTTMode, setMode: setSTTMode, language: sttLanguage, setLanguage: setSTTLanguage, autoSend: sttAutoSend, toggleAutoSend: toggleSTTAutoSend } = useSTTMode()
  const { mode: powerMode, cycleMode: cyclePowerMode, isPending: powerModePending } = usePowerMode()
  const [batchOpen, setBatchOpen] = useState(false)
  useKioskMode()

  // Track played IDs with useRef to avoid re-renders
  const playedVoiceIds = useRef(new Set<number>())
  const playedTaskIds = useRef(new Set<number>())

  // Zones query for dark mode sensor
  const zonesQuery = useQuery({
    queryKey: ['zones'],
    queryFn: fetchZones,
    refetchInterval: 10000,
  })

  const tasksQuery = useQuery({
    queryKey: ['tasks'],
    queryFn: fetchTasks,
    refetchInterval: 5000,
  })

  const voiceEventsQuery = useQuery({
    queryKey: ['voiceEvents'],
    queryFn: fetchVoiceEvents,
    refetchInterval: 3000,
    enabled: isEnabled,
  })

  // Determine primary zone light level for dark mode
  const primaryZone = zonesQuery.data?.[0]
  const currentLux = primaryZone?.environment?.light
  const { preference: darkModePreference, cycle: cycleDarkMode } = useDarkMode(currentLux)
  const { cycleTheme: cycleCharacterTheme, isSecretActive, activeConfig } = useCharacterTheme()

  // Play new voice events
  useEffect(() => {
    if (!isEnabled || !voiceEventsQuery.data) return
    for (const ev of voiceEventsQuery.data) {
      if (!playedVoiceIds.current.has(ev.id) && ev.audio_url) {
        enqueue(ev.audio_url, AudioPriority.VOICE_EVENT, ev.tone, ev.motion_id ?? undefined)
        playedVoiceIds.current.add(ev.id)
      }
    }
    // Trim if too large
    if (playedVoiceIds.current.size > MAX_PLAYED_IDS) {
      const arr = [...playedVoiceIds.current]
      playedVoiceIds.current = new Set(arr.slice(-TRIM_TO))
    }
  }, [voiceEventsQuery.data, isEnabled, enqueue])

  // Auto-play task announcements
  useEffect(() => {
    if (!isEnabled || !tasksQuery.data) return
    for (const task of tasksQuery.data) {
      if (!task.is_completed && task.announcement_audio_url && !playedTaskIds.current.has(task.id)) {
        enqueue(task.announcement_audio_url, AudioPriority.ANNOUNCEMENT)
        playedTaskIds.current.add(task.id)
      }
    }
    if (playedTaskIds.current.size > MAX_PLAYED_IDS) {
      const arr = [...playedTaskIds.current]
      playedTaskIds.current = new Set(arr.slice(-TRIM_TO))
    }
  }, [tasksQuery.data, isEnabled, enqueue])

  const activeTasks = tasksQuery.data?.filter((t: TaskData) => !t.is_completed).length ?? 0

  const toggleAudio = useCallback(() => setAudioEnabled(v => !v), [])
  const hideAvatar = useCallback(() => setAvatarMode('hidden'), [setAvatarMode])

  return (
    <div className="flex min-h-screen bg-background">
      <AppSidebar
        audioEnabled={audioEnabled}
        onToggleAudio={toggleAudio}
        darkModePreference={darkModePreference}
        onCycleDarkMode={cycleDarkMode}
        secretThemeActive={isSecretActive}
        secretThemeConfig={activeConfig}
        onCycleSecretTheme={cycleCharacterTheme}
        avatarMode={avatarMode}
        onCycleAvatarMode={cycleAvatarMode}
        sttMode={sttMode}
        onCycleSTTMode={cycleSTTMode}
        sttLanguage={sttLanguage}
        onSetSTTLanguage={setSTTLanguage}
        powerMode={powerMode}
        onCyclePowerMode={cyclePowerMode}
        powerModePending={powerModePending}
        onOpenBatch={() => setBatchOpen(true)}
      />
      <div className="flex-1 flex flex-col min-w-0">
        <Header
          audioEnabled={audioEnabled}
          onToggleAudio={toggleAudio}
          darkModePreference={darkModePreference}
          onCycleDarkMode={cycleDarkMode}
          secretThemeActive={isSecretActive}
          secretThemeConfig={activeConfig}
          avatarMode={avatarMode}
          onCycleAvatarMode={cycleAvatarMode}
          sttMode={sttMode}
          onCycleSTTMode={cycleSTTMode}
          powerMode={powerMode}
          onCyclePowerMode={cyclePowerMode}
          powerModePending={powerModePending}
          environment={primaryZone?.environment}
        />
        <main className="flex-1 flex flex-col p-4 lg:p-6 pb-20 lg:pb-6 min-h-0">
          <Outlet context={{
            audioEnabled: isEnabled,
            enqueueAudio: enqueue,
            queryClient,
            voiceEvents: voiceEventsQuery.data as VoiceEvent[] | undefined,
            avatarMode,
            sttMode,
            setSTTMode,
            sttLanguage,
            setSTTLanguage,
            sttAutoSend,
            toggleSTTAutoSend,
          }} />
        </main>
      </div>
      <BottomNav activeTasks={activeTasks} />
      {avatarMode !== 'hidden' && (
        <Suspense fallback={null}>
          <AvatarContainer mode={avatarMode} onClose={hideAvatar} />
        </Suspense>
      )}
      <BatchDialog open={batchOpen} onOpenChange={setBatchOpen} />
      <Toaster position="bottom-right" richColors />
      {import.meta.env.DEV && (
        <Suspense fallback={null}>
          <PsdTestPanel />
        </Suspense>
      )}
    </div>
  )
}

// Typed hook for outlet context
import { useOutletContext } from 'react-router'
import type { QueryClient } from '@tanstack/react-query'

import type { AvatarMode } from '@/hooks/use-avatar-mode'

interface AppContext {
  audioEnabled: boolean
  enqueueAudio: (url: string, priority: AudioPriority, tone?: string) => void
  queryClient: QueryClient
  voiceEvents?: VoiceEvent[]
  avatarMode: AvatarMode
  sttMode: STTMode
  setSTTMode: (mode: STTMode) => void
  sttLanguage: string
  setSTTLanguage: (lang: string) => void
  sttAutoSend: boolean
  toggleSTTAutoSend: () => void
}

export function useAppContext() {
  return useOutletContext<AppContext>()
}
