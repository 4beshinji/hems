import { BiometricData } from '../api'

interface Props {
  biometric: BiometricData | null
}

const hrZoneColors: Record<string, string> = {
  rest: 'text-green-600',
  fat_burn: 'text-yellow-600',
  cardio: 'text-orange-600',
  peak: 'text-red-600',
}

const stressCategoryColors: Record<string, string> = {
  relaxed: 'text-green-600',
  normal: 'text-blue-600',
  moderate: 'text-yellow-600',
  high: 'text-red-600',
}

export default function BiometricPanel({ biometric }: Props) {
  if (!biometric || biometric.status === 'no_data' || !biometric.bridge_connected) return null

  const hr = biometric.heart_rate
  const sleep = biometric.sleep
  const activity = biometric.activity
  const stress = biometric.stress
  const fatigue = biometric.fatigue
  const spo2 = biometric.spo2

  const stepsProgress = activity
    ? Math.min((activity.steps / (activity.steps_goal || 10000)) * 100, 100)
    : 0

  return (
    <section className="mt-6">
      <h2 className="text-lg font-semibold text-gray-800 mb-3">
        バイオメトリクス
        {biometric.provider && (
          <span className="ml-2 text-xs text-gray-400 font-normal">
            ({biometric.provider})
          </span>
        )}
      </h2>
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
        {/* Heart Rate */}
        {hr && (
          <div className="bg-white rounded-xl elevation-1 p-4">
            <div className="text-xs text-gray-500 mb-1">心拍数</div>
            <div className={`text-2xl font-bold ${hrZoneColors[hr.zone] || 'text-gray-800'}`}>
              {hr.bpm}
              <span className="text-sm font-normal ml-1">bpm</span>
            </div>
            <div className="text-xs text-gray-400 mt-1">
              {hr.zone === 'rest' ? '安静' :
               hr.zone === 'fat_burn' ? '脂肪燃焼' :
               hr.zone === 'cardio' ? '有酸素' :
               hr.zone === 'peak' ? 'ピーク' : hr.zone}
              {hr.resting_bpm != null && ` / 安静時${hr.resting_bpm}bpm`}
            </div>
            {spo2 && (
              <div className="text-xs text-gray-500 mt-1">
                SpO2: <span className={spo2.percent < 95 ? 'text-red-600 font-bold' : ''}>
                  {spo2.percent}%
                </span>
              </div>
            )}
          </div>
        )}

        {/* Sleep */}
        {sleep && sleep.duration_minutes > 0 && (
          <div className="bg-white rounded-xl elevation-1 p-4">
            <div className="text-xs text-gray-500 mb-1">睡眠</div>
            <div className="text-2xl font-bold text-indigo-700">
              {Math.floor(sleep.duration_minutes / 60)}h{sleep.duration_minutes % 60}m
            </div>
            {sleep.quality_score > 0 && (
              <div className="mt-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-400">品質</span>
                  <div className="flex-1 bg-gray-200 rounded-full h-1.5">
                    <div
                      className={`h-1.5 rounded-full ${
                        sleep.quality_score >= 70 ? 'bg-green-500' :
                        sleep.quality_score >= 50 ? 'bg-yellow-500' : 'bg-red-500'
                      }`}
                      style={{ width: `${sleep.quality_score}%` }}
                    />
                  </div>
                  <span className="text-xs font-medium">{sleep.quality_score}</span>
                </div>
              </div>
            )}
            <div className="flex gap-2 mt-2 text-xs text-gray-400">
              {sleep.deep_minutes > 0 && <span>深い{sleep.deep_minutes}m</span>}
              {sleep.rem_minutes > 0 && <span>REM{sleep.rem_minutes}m</span>}
              {sleep.light_minutes > 0 && <span>浅い{sleep.light_minutes}m</span>}
            </div>
          </div>
        )}

        {/* Activity / Steps */}
        {activity && activity.steps > 0 && (
          <div className="bg-white rounded-xl elevation-1 p-4">
            <div className="text-xs text-gray-500 mb-1">歩数</div>
            <div className="text-2xl font-bold text-emerald-700">
              {activity.steps.toLocaleString()}
            </div>
            <div className="mt-1">
              <div className="flex items-center gap-2">
                <div className="flex-1 bg-gray-200 rounded-full h-1.5">
                  <div
                    className={`h-1.5 rounded-full ${
                      stepsProgress >= 100 ? 'bg-green-500' : 'bg-blue-500'
                    }`}
                    style={{ width: `${stepsProgress}%` }}
                  />
                </div>
                <span className="text-xs text-gray-400">
                  {Math.round(stepsProgress)}%
                </span>
              </div>
            </div>
            <div className="text-xs text-gray-400 mt-1">
              目標 {(activity.steps_goal || 10000).toLocaleString()}歩
              {activity.calories > 0 && ` / ${activity.calories}kcal`}
            </div>
          </div>
        )}

        {/* Stress / Fatigue */}
        {(stress || fatigue) && (
          <div className="bg-white rounded-xl elevation-1 p-4">
            <div className="text-xs text-gray-500 mb-1">ストレス / 疲労</div>
            {stress && (
              <div className="mb-2">
                <span className={`text-lg font-bold ${stressCategoryColors[stress.category] || 'text-gray-800'}`}>
                  {stress.category === 'relaxed' ? 'リラックス' :
                   stress.category === 'normal' ? '通常' :
                   stress.category === 'moderate' ? 'やや高い' :
                   stress.category === 'high' ? '高い' : stress.category}
                </span>
                <span className="text-sm text-gray-400 ml-1">({stress.level})</span>
              </div>
            )}
            {fatigue && fatigue.score > 0 && (
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-400">疲労度</span>
                  <div className="flex-1 bg-gray-200 rounded-full h-1.5">
                    <div
                      className={`h-1.5 rounded-full ${
                        fatigue.score > 70 ? 'bg-red-500' :
                        fatigue.score > 40 ? 'bg-yellow-500' : 'bg-green-500'
                      }`}
                      style={{ width: `${fatigue.score}%` }}
                    />
                  </div>
                  <span className="text-xs font-medium">{fatigue.score}</span>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
