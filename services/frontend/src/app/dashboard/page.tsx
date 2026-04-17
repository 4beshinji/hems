import { useQuery } from '@tanstack/react-query'
import ChatPanel from '@/components/dashboard/ChatPanel'
import ActiveTaskList from '@/components/dashboard/ActiveTaskList'
import KeyMetricsSummary from '@/components/dashboard/KeyMetricsSummary'
import TimelinePanel from '@/components/dashboard/TimelinePanel'
import { fetchCharacter } from '@/lib/api'

export default function DashboardPage() {
  const { data: character } = useQuery({
    queryKey: ['character'],
    queryFn: fetchCharacter,
    staleTime: Infinity,
  })

  return (
    <div className="flex flex-col flex-1 min-h-0 gap-4">
      <div className="grid gap-4 lg:grid-cols-3 flex-1 min-h-0">
        {/* Left: Chat */}
        <div className="min-h-0 flex flex-col max-h-[calc(100vh-7rem)]">
          <ChatPanel />
        </div>
        {/* Middle: Metrics + Tasks */}
        <div className="space-y-4 min-h-0 overflow-y-auto max-h-[calc(100vh-7rem)]">
          <KeyMetricsSummary />
          <ActiveTaskList />
        </div>
        {/* Right: Timeline */}
        <div className="min-h-0 flex flex-col max-h-[calc(100vh-7rem)]">
          <div className="flex-1 min-h-0">
            <TimelinePanel />
          </div>
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
