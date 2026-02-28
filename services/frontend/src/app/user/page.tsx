import { useQuery } from '@tanstack/react-query'
import HeartRateCard from '@/components/user/HeartRateCard'
import SleepCard from '@/components/user/SleepCard'
import StressCard from '@/components/user/StressCard'
import ActivityCard from '@/components/user/ActivityCard'
import BodyMetricsCard from '@/components/user/BodyMetricsCard'
import XPPanel from '@/components/user/XPPanel'
import { fetchBiometric } from '@/lib/api'

export default function UserPage() {
  const { data: biometric } = useQuery({
    queryKey: ['biometric'],
    queryFn: fetchBiometric,
    refetchInterval: 5000,
  })

  const hasBiometric = biometric && biometric.status !== 'no_data' && biometric.bridge_connected

  return (
    <div className="space-y-4">
      {hasBiometric && (
        <section>
          <h2 className="text-sm font-semibold text-foreground mb-3">
            バイオメトリクス
            {biometric.provider && (
              <span className="ml-2 text-xs text-muted-foreground font-normal">
                ({biometric.provider})
              </span>
            )}
          </h2>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            <HeartRateCard biometric={biometric} />
            <SleepCard biometric={biometric} />
            <StressCard biometric={biometric} />
            <ActivityCard biometric={biometric} />
            <BodyMetricsCard biometric={biometric} />
          </div>
        </section>
      )}
      {!hasBiometric && (
        <p className="text-sm text-muted-foreground py-8 text-center">
          バイオメトリクスデータなし — biometric bridge が接続されていません
        </p>
      )}
      <section>
        <XPPanel />
      </section>
    </div>
  )
}
