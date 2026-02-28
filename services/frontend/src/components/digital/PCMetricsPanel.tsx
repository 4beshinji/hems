import { memo, useState } from 'react'
import { Cpu, MemoryStick, Monitor, HardDrive, ChevronDown, ChevronUp } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import type { PCMetrics } from '@/lib/types'

interface Props {
  pc: PCMetrics | null
}

const PCMetricsPanel = memo(function PCMetricsPanel({ pc }: Props) {
  const [showProcesses, setShowProcesses] = useState(false)

  if (!pc || pc.status === 'no_data' || !pc.cpu) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Monitor className="h-4 w-4 text-chart-blue" />
          PC Status
          {pc.bridge_connected === false && (
            <span className="text-xs text-warning font-normal ml-auto">bridge disconnected</span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {/* CPU */}
          {pc.cpu && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Cpu className="h-3.5 w-3.5" />
                CPU
              </div>
              <p className="text-xl font-bold text-foreground">{pc.cpu.usage_percent.toFixed(0)}%</p>
              <Progress value={pc.cpu.usage_percent} className="h-1.5" />
              {pc.cpu.temp_c > 0 && (
                <p className="text-xs text-muted-foreground">{pc.cpu.temp_c.toFixed(0)}°C</p>
              )}
            </div>
          )}

          {/* Memory */}
          {pc.memory && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <MemoryStick className="h-3.5 w-3.5" />
                Memory
              </div>
              <p className="text-xl font-bold text-foreground">{pc.memory.percent.toFixed(0)}%</p>
              <Progress value={pc.memory.percent} className="h-1.5" />
              <p className="text-xs text-muted-foreground">
                {pc.memory.used_gb.toFixed(1)}/{pc.memory.total_gb.toFixed(0)} GB
              </p>
            </div>
          )}

          {/* GPU */}
          {pc.gpu && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Monitor className="h-3.5 w-3.5" />
                GPU
              </div>
              <p className="text-xl font-bold text-foreground">{pc.gpu.usage_percent.toFixed(0)}%</p>
              <Progress value={pc.gpu.usage_percent} className="h-1.5" />
              {pc.gpu.temp_c > 0 && (
                <p className="text-xs text-muted-foreground">{pc.gpu.temp_c.toFixed(0)}°C</p>
              )}
            </div>
          )}

          {/* Disks - show all */}
          {pc.disk && pc.disk.map((d, i) => (
            <div key={i} className="space-y-1.5">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <HardDrive className="h-3.5 w-3.5" />
                Disk ({d.mount})
              </div>
              <p className="text-xl font-bold text-foreground">{d.percent.toFixed(0)}%</p>
              <Progress value={d.percent} className="h-1.5" />
              <p className="text-xs text-muted-foreground">
                {d.used_gb.toFixed(0)}/{d.total_gb.toFixed(0)} GB
              </p>
            </div>
          ))}
        </div>

        {/* Top Processes */}
        {pc.top_processes && pc.top_processes.length > 0 && (
          <div>
            <button
              onClick={() => setShowProcesses(!showProcesses)}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              {showProcesses ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
              Top Processes
            </button>
            {showProcesses && (
              <div className="mt-2 text-xs">
                <div className="grid grid-cols-4 gap-2 text-muted-foreground font-medium mb-1">
                  <span>Name</span><span className="text-right">CPU%</span><span className="text-right">Mem</span><span className="text-right">PID</span>
                </div>
                {pc.top_processes.slice(0, 5).map((p) => (
                  <div key={p.pid} className="grid grid-cols-4 gap-2 py-0.5 text-foreground">
                    <span className="truncate">{p.name}</span>
                    <span className="text-right">{p.cpu_percent.toFixed(1)}</span>
                    <span className="text-right">{p.mem_mb.toFixed(0)}M</span>
                    <span className="text-right text-muted-foreground">{p.pid}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
})

export default PCMetricsPanel
