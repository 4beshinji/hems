import { useQuery } from '@tanstack/react-query'
import { Camera, User, Activity, PersonStanding } from 'lucide-react'
import { fetchPerception, type PerceptionData } from '../api'

const ZONE_LABELS: Record<string, string> = {
  living_room: 'リビング',
  bedroom: '寝室',
  kitchen: 'キッチン',
  bathroom: '浴室',
  study: '書斎',
}

const POSTURE_LABELS: Record<string, string> = {
  standing: '立位',
  sitting: '座位',
  lying: '横臥',
  walking: '歩行',
  static: '静止',
  unknown: '不明',
}

function activityColor(level: number | null): string {
  if (level === null) return 'bg-gray-200'
  if (level >= 0.7) return 'bg-green-500'
  if (level >= 0.3) return 'bg-yellow-500'
  if (level >= 0.1) return 'bg-orange-400'
  return 'bg-red-400'
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}秒`
  const min = Math.floor(seconds / 60)
  if (min < 60) return `${min}分`
  const h = Math.floor(min / 60)
  return `${h}時間${min % 60}分`
}

export default function PerceptionPanel() {
  const { data } = useQuery<PerceptionData>({
    queryKey: ['perception'],
    queryFn: fetchPerception,
    refetchInterval: 5000,
  })

  if (!data || data.status === 'no_data' || !data.zones) return null

  const zones = Object.entries(data.zones)
  if (zones.length === 0) return null

  return (
    <section className="mb-6">
      <h2 className="text-lg font-semibold text-gray-800 mb-3 flex items-center gap-2">
        <Camera className="w-5 h-5 text-indigo-600" />
        Perception
      </h2>
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {zones.map(([zoneId, z]) => (
          <div key={zoneId} className="bg-white rounded-xl elevation-1 p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="font-medium text-gray-700">
                {ZONE_LABELS[zoneId] || zoneId}
              </span>
              <span className="flex items-center gap-1 text-sm font-bold text-indigo-600">
                <User className="w-4 h-4" />
                {z.person_count}
              </span>
            </div>

            {/* Activity Level Bar */}
            <div className="mb-3">
              <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
                <span className="flex items-center gap-1">
                  <Activity className="w-3 h-3" />
                  活動レベル
                </span>
                <span>{z.activity_level !== null ? (z.activity_level * 100).toFixed(0) : '—'}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className={`h-2 rounded-full transition-all ${activityColor(z.activity_level)}`}
                  style={{ width: `${(z.activity_level ?? 0) * 100}%` }}
                />
              </div>
            </div>

            {/* Posture */}
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-1 text-gray-600">
                <PersonStanding className="w-4 h-4" />
                {POSTURE_LABELS[z.posture_status] || z.posture_status}
              </span>
              {z.posture_duration_sec > 0 && (
                <span className="text-xs text-gray-400">
                  {formatDuration(z.posture_duration_sec)}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
