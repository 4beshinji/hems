import { lazy, Suspense } from 'react'
import { useQuery } from '@tanstack/react-query'
import ChatPanel from '@/components/dashboard/ChatPanel'
import ActiveTaskList from '@/components/dashboard/ActiveTaskList'
import KeyMetricsSummary from '@/components/dashboard/KeyMetricsSummary'
import TimelinePanel from '@/components/dashboard/TimelinePanel'
import { Skeleton } from '@/components/ui/skeleton'
import { fetchCharacter } from '@/lib/api'
import { useAppContext } from '@/app/layout'

import { IS_PSD } from '@/lib/avatar-type'

// PSD 立ち絵はポータル不要 — ダッシュボードに直接描画
const PsdAvatarPanel = IS_PSD
  ? lazy(() => import('@/components/psd/PsdAvatarPanel'))
  : null

export default function DashboardPage() {
  const { avatarMode } = useAppContext()
  const { data: character } = useQuery({
    queryKey: ['character'],
    queryFn: fetchCharacter,
    staleTime: Infinity,
  })

  return (
    <div className="flex flex-col flex-1 min-h-0 gap-4">
      <div className="grid gap-4 lg:grid-cols-3 flex-1 min-h-0">
        {/* Left: Timeline (2/3 on desktop) */}
        <div className="lg:col-span-2 min-h-0 flex flex-col gap-4">
          <div className="flex-1 min-h-0">
            <TimelinePanel />
          </div>
        </div>
        {/* Right: Key Metrics + Chat + Tasks + Avatar (1/3 on desktop) */}
        <div className="space-y-4 min-h-0 overflow-y-auto">
          <KeyMetricsSummary />
          <div className="min-h-[320px] max-h-[420px] flex flex-col">
            <ChatPanel />
          </div>
          <ActiveTaskList />
          {avatarMode === 'panel' && IS_PSD && PsdAvatarPanel && (
            <Suspense fallback={<Skeleton className="w-full aspect-[3/4] rounded-lg" />}>
              <PsdAvatarPanel />
            </Suspense>
          )}
          {avatarMode === 'panel' && !IS_PSD && <div id="avatar-panel-slot" />}
        </div>
      </div>
      {character?.voice_credit ? (
        <p className="text-[10px] text-muted-foreground/50 text-right select-none">
          {character.voice_credit as string}
        </p>
      ) : null}
    </div>
  )
}
