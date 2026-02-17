import { Thermometer, Droplets, Wind, Users } from 'lucide-react'
import type { ZoneData } from '../App'

interface Props {
  zones: ZoneData[]
}

const ZONE_LABELS: Record<string, string> = {
  living_room: 'リビング',
  bedroom: '寝室',
  kitchen: 'キッチン',
  bathroom: '浴室',
  office: '書斎',
}

function formatAge(lastUpdate?: number | null): string {
  if (!lastUpdate) return ''
  const age = Math.floor(Date.now() / 1000 - lastUpdate)
  if (age < 60) return `${age}秒前`
  if (age < 3600) return `${Math.floor(age / 60)}分前`
  return `${Math.floor(age / 3600)}時間前`
}

function co2Level(co2?: number | null): { color: string; label: string } {
  if (co2 == null) return { color: 'bg-gray-200', label: '' }
  if (co2 < 800) return { color: 'bg-green-400', label: '良好' }
  if (co2 < 1000) return { color: 'bg-yellow-400', label: '注意' }
  if (co2 < 1500) return { color: 'bg-orange-400', label: '換気推奨' }
  return { color: 'bg-red-500', label: '危険' }
}

function co2Width(co2?: number | null): number {
  if (co2 == null) return 0
  return Math.min(100, Math.max(0, (co2 / 2000) * 100))
}

export default function StatusPanel({ zones }: Props) {
  if (zones.length === 0) {
    return (
      <div className="bg-white rounded-xl elevation-2 p-6">
        <h3 className="text-lg font-semibold text-gray-700 mb-2">Environment</h3>
        <p className="text-gray-400 text-sm">センサーデータ待機中...</p>
      </div>
    )
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {zones.map(zone => {
        const env = zone.environment
        const co2Info = co2Level(env.co2)
        const label = ZONE_LABELS[zone.zone_id] || zone.zone_id
        const age = formatAge(env.last_update)

        return (
          <div key={zone.zone_id} className="bg-white rounded-xl elevation-2 p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-gray-800">{label}</h3>
              <div className="flex items-center gap-1">
                {zone.occupancy.count > 0 && (
                  <span className="flex items-center gap-0.5 text-xs text-green-600 bg-green-50 px-2 py-0.5 rounded-full">
                    <Users className="w-3 h-3" />
                    {zone.occupancy.count}
                  </span>
                )}
                {age && <span className="text-xs text-gray-400">{age}</span>}
              </div>
            </div>

            <div className="space-y-2">
              {env.temperature != null && (
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1.5 text-sm text-gray-600">
                    <Thermometer className="w-4 h-4 text-red-400" />
                    温度
                  </span>
                  <span className={`font-mono font-bold ${
                    env.temperature > 28 ? 'text-red-600' :
                    env.temperature < 16 ? 'text-blue-600' : 'text-gray-800'
                  }`}>
                    {env.temperature.toFixed(1)}°C
                  </span>
                </div>
              )}

              {env.humidity != null && (
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1.5 text-sm text-gray-600">
                    <Droplets className="w-4 h-4 text-blue-400" />
                    湿度
                  </span>
                  <span className="font-mono font-bold text-gray-800">
                    {env.humidity.toFixed(0)}%
                  </span>
                </div>
              )}

              {env.co2 != null && (
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="flex items-center gap-1.5 text-sm text-gray-600">
                      <Wind className="w-4 h-4 text-gray-400" />
                      CO2
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="font-mono font-bold text-gray-800">
                        {Math.round(env.co2)}ppm
                      </span>
                      {co2Info.label && (
                        <span className={`text-xs px-1.5 py-0.5 rounded text-white ${co2Info.color}`}>
                          {co2Info.label}
                        </span>
                      )}
                    </span>
                  </div>
                  <div className="w-full bg-gray-100 rounded-full h-1.5">
                    <div
                      className={`h-1.5 rounded-full transition-all ${co2Info.color}`}
                      style={{ width: `${co2Width(env.co2)}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
