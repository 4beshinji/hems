import { useQuery } from '@tanstack/react-query'
import ChatPanel from '@/components/dashboard/ChatPanel'
import ActiveTaskList from '@/components/dashboard/ActiveTaskList'
import KeyMetricsSummary from '@/components/dashboard/KeyMetricsSummary'
import { fetchCharacter } from '@/lib/api'
import { useAppContext } from '@/app/layout'

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
        {/* Left: Chat (2/3 on desktop) */}
        <div className="lg:col-span-2 min-h-0 flex flex-col gap-4">
          <div className="flex-1 min-h-0">
            <ChatPanel />
          </div>
        </div>
        {/* Right: Key Metrics + Tasks + Avatar (1/3 on desktop) */}
        <div className="space-y-4 min-h-0 overflow-y-auto">
          <KeyMetricsSummary />
          <ActiveTaskList />
          {avatarMode === 'panel' && <div id="avatar-panel-slot" />}
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
