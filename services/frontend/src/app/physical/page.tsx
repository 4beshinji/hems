import { useQuery } from '@tanstack/react-query'
import { Home } from 'lucide-react'
import ZoneEnvironmentCard from '@/components/physical/ZoneEnvironmentCard'
import LightCard from '@/components/physical/LightCard'
import ClimateCard from '@/components/physical/ClimateCard'
import CoverCard from '@/components/physical/CoverCard'
import PerceptionPanel from '@/components/physical/PerceptionPanel'
import LoadingState from '@/components/shared/LoadingState'
import ErrorState from '@/components/shared/ErrorState'
import { fetchZones, fetchHome } from '@/lib/api'
import type { HomeData } from '@/lib/types'

export default function PhysicalPage() {
  const zonesQuery = useQuery({
    queryKey: ['zones'],
    queryFn: fetchZones,
    refetchInterval: 5000,
  })

  const homeQuery = useQuery<HomeData>({
    queryKey: ['home'],
    queryFn: fetchHome,
    refetchInterval: 5000,
  })

  if (zonesQuery.isLoading) return <LoadingState />
  if (zonesQuery.isError) return <ErrorState onRetry={() => zonesQuery.refetch()} />

  const zones = zonesQuery.data ?? []
  const home = homeQuery.data
  const hasHome = home && home.status !== 'no_data' && home.bridge_connected
  const lights = hasHome && home.lights ? Object.entries(home.lights) : []
  const climates = hasHome && home.climates ? Object.entries(home.climates) : []
  const covers = hasHome && home.covers ? Object.entries(home.covers) : []
  const hasSmartHome = lights.length > 0 || climates.length > 0 || covers.length > 0

  return (
    <div className="space-y-6">
      {/* Zone Environment */}
      <section>
        <h2 className="text-sm font-semibold text-foreground mb-3">Environment</h2>
        {zones.length === 0 ? (
          <p className="text-sm text-muted-foreground">センサーデータ待機中...</p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {zones.map((zone) => (
              <ZoneEnvironmentCard key={zone.zone_id} zone={zone} />
            ))}
          </div>
        )}
      </section>

      {/* Smart Home Controls */}
      {hasSmartHome && (
        <section>
          <h2 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
            <Home className="h-4 w-4 text-warning" />
            Smart Home
          </h2>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {lights.map(([id, light]) => (
              <LightCard key={id} entityId={id} light={light} />
            ))}
            {climates.map(([id, climate]) => (
              <ClimateCard key={id} entityId={id} climate={climate} />
            ))}
            {covers.map(([id, cover]) => (
              <CoverCard key={id} entityId={id} cover={cover} />
            ))}
          </div>
        </section>
      )}

      {/* Perception */}
      <section>
        <PerceptionPanel />
      </section>
    </div>
  )
}
