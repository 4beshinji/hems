import { memo } from 'react'
import { useQueries } from '@tanstack/react-query'
import { Wifi, WifiOff } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import {
  fetchBiometric,
  fetchGAS,
  fetchHome,
  fetchKnowledge,
  fetchNews,
  fetchPC,
  fetchPerception,
  fetchServices,
  fetchWeather,
} from '@/lib/api'

type BridgeStatus = {
  name: string
  connected: boolean
  hint?: string
}

const BridgeHealthBadge = memo(function BridgeHealthBadge() {
  const queries = useQueries({
    queries: [
      { queryKey: ['weather'], queryFn: fetchWeather, refetchInterval: 60_000 },
      { queryKey: ['news'], queryFn: fetchNews, refetchInterval: 60_000 },
      { queryKey: ['biometric'], queryFn: fetchBiometric, refetchInterval: 30_000 },
      { queryKey: ['perception'], queryFn: fetchPerception, refetchInterval: 30_000 },
      { queryKey: ['home'], queryFn: fetchHome, refetchInterval: 30_000 },
      { queryKey: ['gas'], queryFn: fetchGAS, refetchInterval: 60_000 },
      { queryKey: ['pc'], queryFn: fetchPC, refetchInterval: 30_000 },
      { queryKey: ['services'], queryFn: fetchServices, refetchInterval: 60_000 },
      { queryKey: ['knowledge'], queryFn: fetchKnowledge, refetchInterval: 60_000 },
    ],
  })

  const [weather, news, bio, percep, home, gas, pc, services, knowledge] = queries

  const bridges: BridgeStatus[] = [
    {
      name: 'Weather',
      connected: !!weather.data && weather.data?.status !== 'no_data' && !!weather.data?.current,
    },
    {
      name: 'News',
      connected: !!news.data?.bridge_connected,
    },
    {
      name: 'Biometric',
      connected: !!bio.data?.bridge_connected,
    },
    {
      name: 'Perception',
      connected: !!percep.data && percep.data?.status !== 'no_data',
    },
    {
      name: 'HA',
      connected: !!home.data?.bridge_connected,
    },
    {
      name: 'GAS',
      connected: !!gas.data && gas.data?.status !== 'no_data',
    },
    {
      name: 'PC',
      connected: !!pc.data?.bridge_connected,
    },
    {
      name: 'Services',
      connected: !!services.data && services.data?.status !== 'no_data',
    },
    {
      name: 'Knowledge',
      connected: !!knowledge.data?.status && knowledge.data.status !== 'no_data',
    },
  ]

  // Only show bridges that have ever responded (avoid noise from disabled profiles).
  const seen = bridges.filter(
    (_, i) => queries[i].data !== undefined && queries[i].data !== null,
  )
  if (seen.length === 0) return null

  const offline = seen.filter((b) => !b.connected)

  return (
    <div className="flex flex-wrap items-center gap-1.5 px-2 py-1.5 rounded-md bg-muted/30 border border-border">
      {offline.length === 0 ? (
        <Badge variant="success" className="gap-1 text-[10px] py-0">
          <Wifi className="h-2.5 w-2.5" />
          全 {seen.length} bridge 正常
        </Badge>
      ) : (
        <>
          <Badge variant="destructive" className="gap-1 text-[10px] py-0">
            <WifiOff className="h-2.5 w-2.5" />
            {offline.length}/{seen.length} 切断
          </Badge>
          {offline.map((b) => (
            <Badge key={b.name} variant="outline" className="text-[10px] py-0 font-normal">
              {b.name}
            </Badge>
          ))}
        </>
      )}
    </div>
  )
})

export default BridgeHealthBadge
