import type { PCMetrics } from '../api'

interface Props {
  pc: PCMetrics | null
}

export default function PCStatusPanel({ pc }: Props) {
  if (!pc || pc.status === 'no_data' || !pc.cpu) return null

  return (
    <section className="mt-6">
      <h2 className="text-lg font-semibold text-gray-700 mb-3">PC Status</h2>
      <div className="bg-white rounded-xl elevation-1 p-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        {pc.cpu && (
          <div>
            <p className="text-gray-500 text-xs mb-1">CPU</p>
            <p className="font-bold text-gray-800">{pc.cpu.usage_percent.toFixed(0)}%</p>
            {pc.cpu.temp_c > 0 && (
              <p className="text-gray-400 text-xs">{pc.cpu.temp_c.toFixed(0)}°C</p>
            )}
          </div>
        )}
        {pc.memory && (
          <div>
            <p className="text-gray-500 text-xs mb-1">Memory</p>
            <p className="font-bold text-gray-800">{pc.memory.percent.toFixed(0)}%</p>
            <p className="text-gray-400 text-xs">
              {pc.memory.used_gb.toFixed(1)}/{pc.memory.total_gb.toFixed(0)} GB
            </p>
          </div>
        )}
        {pc.gpu && (
          <div>
            <p className="text-gray-500 text-xs mb-1">GPU</p>
            <p className="font-bold text-gray-800">{pc.gpu.usage_percent.toFixed(0)}%</p>
            {pc.gpu.temp_c > 0 && (
              <p className="text-gray-400 text-xs">{pc.gpu.temp_c.toFixed(0)}°C</p>
            )}
          </div>
        )}
        {pc.disk && pc.disk.length > 0 && (
          <div>
            <p className="text-gray-500 text-xs mb-1">Disk ({pc.disk[0].mount})</p>
            <p className="font-bold text-gray-800">{pc.disk[0].percent.toFixed(0)}%</p>
            <p className="text-gray-400 text-xs">
              {pc.disk[0].used_gb.toFixed(0)}/{pc.disk[0].total_gb.toFixed(0)} GB
            </p>
          </div>
        )}
        {pc.bridge_connected === false && (
          <div className="col-span-full text-xs text-amber-600">
            ⚠ OpenClaw bridge disconnected
          </div>
        )}
      </div>
    </section>
  )
}
