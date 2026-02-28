import AIActivityLog from '@/components/dashboard/AIActivityLog'
import ActiveTaskList from '@/components/dashboard/ActiveTaskList'
import KeyMetricsSummary from '@/components/dashboard/KeyMetricsSummary'

export default function DashboardPage() {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {/* Left: AI Activity Log (2/3 on desktop) */}
      <div className="lg:col-span-2">
        <AIActivityLog />
      </div>
      {/* Right: Key Metrics + Tasks (1/3 on desktop) */}
      <div className="space-y-4">
        <KeyMetricsSummary />
        <ActiveTaskList />
      </div>
    </div>
  )
}
