import { useQuery } from '@tanstack/react-query'
import ChatPanel from '@/components/dashboard/ChatPanel'
import ActiveTaskList from '@/components/dashboard/ActiveTaskList'
import AIActivityLog from '@/components/dashboard/AIActivityLog'
import AlertHistoryCard from '@/components/dashboard/AlertHistoryCard'
import BridgeHealthBadge from '@/components/dashboard/BridgeHealthBadge'
import DeviceTimelineCard from '@/components/dashboard/DeviceTimelineCard'
import EnvTrendCard from '@/components/dashboard/EnvTrendCard'
import KeyMetricsSummary from '@/components/dashboard/KeyMetricsSummary'
import NewsBanner from '@/components/dashboard/NewsBanner'
import TimelinePanel from '@/components/dashboard/TimelinePanel'
import UserStateCard from '@/components/dashboard/UserStateCard'
import VLMSceneCard from '@/components/dashboard/VLMSceneCard'
import WeatherAlertBanner from '@/components/dashboard/WeatherAlertBanner'
import WeatherCard from '@/components/dashboard/WeatherCard'
import { fetchCharacter } from '@/lib/api'

export default function DashboardPage() {
  const { data: character } = useQuery({
    queryKey: ['character'],
    queryFn: fetchCharacter,
    staleTime: Infinity,
  })

  return (
    <div className="flex flex-col flex-1 min-h-0 gap-4">
      <WeatherAlertBanner />
      <BridgeHealthBadge />
      <div className="grid gap-4 lg:grid-cols-3 flex-1 min-h-0">
        {/* Left: Chat */}
        <div className="min-h-0 flex flex-col max-h-[calc(100vh-7rem)]">
          <ChatPanel />
        </div>
        {/* Middle: Metrics + Tasks */}
        <div className="space-y-4 min-h-0 overflow-y-auto max-h-[calc(100vh-7rem)]">
          <UserStateCard />
          <KeyMetricsSummary />
          <WeatherCard />
          <NewsBanner />
          <VLMSceneCard />
          <ActiveTaskList />
          <AIActivityLog />
          <EnvTrendCard />
          <DeviceTimelineCard />
          <AlertHistoryCard />
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
