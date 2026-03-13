import AIActivityLog from '@/components/dashboard/AIActivityLog'
import ActiveTaskList from '@/components/dashboard/ActiveTaskList'
import KeyMetricsSummary from '@/components/dashboard/KeyMetricsSummary'

export default function DashboardPage() {
  return (
    <div className="grid gap-4 lg:grid-cols-3 flex-1 min-h-0">
      {/* Left: AI Activity Log (2/3 on desktop) */}
      <div className="lg:col-span-2 min-h-0">
        <AIActivityLog />
      </div>
      {/* Right: Key Metrics + Tasks (1/3 on desktop) */}
      <div className="space-y-4 min-h-0 overflow-y-auto">
        <KeyMetricsSummary />
        <ActiveTaskList />
      </div>
    </div>
  )
}
