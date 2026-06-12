import { useState, useEffect, useRef, lazy, Suspense } from 'react'
import { Outlet } from 'react-router'
import { Toaster } from 'sonner'
import AppSidebar from '@/components/layout/AppSidebar'
import BottomNav from '@/components/layout/BottomNav'
import Header from '@/components/layout/Header'
import { useZones } from '@/hooks/queries/use-zones'
import { useVoiceEvents } from '@/hooks/queries/use-voice-events'
import { useTasks } from '@/hooks/queries/use-tasks'
import { AudioPriority } from '@/audio'
import type { TaskData } from '@/lib/types'
import BatchDialog from '@/components/brain/BatchDialog'
import {
  AudioProvider,
  AvatarProvider,
  SttProvider,
  PowerProvider,
  AppUiProvider,
  useAudioContext,
  useAvatarContext,
} from '@/contexts'

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

// Inner layout: consumes contexts, handles audio playback side-effects
function AppLayoutInner() {
  const { isEnabled, enqueueAudio } = useAudioContext()
  const { avatarMode, hideAvatar } = useAvatarContext()
  const [batchOpen, setBatchOpen] = useState(false)
  useKioskMode()

  const playedVoiceIds = useRef(new Set<number>())
  const playedTaskIds = useRef(new Set<number>())

  const tasksQuery = useTasks()
  const voiceEventsQuery = useVoiceEvents({ enabled: isEnabled })

  useEffect(() => {
    if (!isEnabled || !voiceEventsQuery.data) return
    for (const ev of voiceEventsQuery.data) {
      if (!playedVoiceIds.current.has(ev.id) && ev.audio_url) {
        enqueueAudio(ev.audio_url, AudioPriority.VOICE_EVENT, ev.tone, ev.motion_id ?? undefined)
        playedVoiceIds.current.add(ev.id)
      }
    }
    if (playedVoiceIds.current.size > MAX_PLAYED_IDS) {
      const arr = [...playedVoiceIds.current]
      playedVoiceIds.current = new Set(arr.slice(-TRIM_TO))
    }
  }, [voiceEventsQuery.data, isEnabled, enqueueAudio])

  useEffect(() => {
    if (!isEnabled || !tasksQuery.data) return
    for (const task of tasksQuery.data) {
      if (!task.is_completed && task.announcement_audio_url && !playedTaskIds.current.has(task.id)) {
        enqueueAudio(task.announcement_audio_url, AudioPriority.ANNOUNCEMENT)
        playedTaskIds.current.add(task.id)
      }
    }
    if (playedTaskIds.current.size > MAX_PLAYED_IDS) {
      const arr = [...playedTaskIds.current]
      playedTaskIds.current = new Set(arr.slice(-TRIM_TO))
    }
  }, [tasksQuery.data, isEnabled, enqueueAudio])

  const activeTasks = tasksQuery.data?.filter((t: TaskData) => !t.is_completed).length ?? 0

  return (
    <div className="flex min-h-screen bg-background">
      <AppSidebar onOpenBatch={() => setBatchOpen(true)} />
      <div className="flex-1 flex flex-col min-w-0">
        <Header />
        <main className="flex-1 flex flex-col p-4 lg:p-6 pb-20 lg:pb-6 min-h-0">
          <Outlet />
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

// Wrapper that provides zones data to AppUiProvider
function AppLayoutWithZones() {
  const zonesQuery = useZones()
  const primaryZone = zonesQuery.data?.[0]
  const currentLux = primaryZone?.environment?.light

  return (
    <AppUiProvider currentLux={currentLux}>
      <AppLayoutInner />
    </AppUiProvider>
  )
}

export default function AppLayout() {
  return (
    <AudioProvider>
      <AvatarProvider>
        <SttProvider>
          <PowerProvider>
            <AppLayoutWithZones />
          </PowerProvider>
        </SttProvider>
      </AvatarProvider>
    </AudioProvider>
  )
}

