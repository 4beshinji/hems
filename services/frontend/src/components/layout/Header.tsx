import { useLocation } from 'react-router'
import { type ComponentType } from 'react'
import { Volume2, VolumeX, Sun, Moon, Gauge, User, Mic, MicOff, Zap, LogOut, Thermometer, Droplets, Wind } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { useAudioContext } from '@/contexts/AudioContext'
import { useAvatarContext } from '@/contexts/AvatarContext'
import { useSttContext } from '@/contexts/SttContext'
import { useAppUiContext } from '@/contexts/AppUiContext'
import { usePowerContext } from '@/contexts/PowerContext'
import { useZones } from '@/hooks/queries/use-zones'
import type { PowerMode } from '@/lib/types'

const ROUTE_TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/physical': 'Physical Space',
  '/digital': 'Digital Space',
  '/user': 'User State',
}

const STT_MODE_LABELS = {
  'push-to-talk': 'PTT',
  auto: 'VAD',
  off: 'OFF',
} as const

const POWER_MODE_ICONS: Record<PowerMode, ComponentType<{ className?: string }>> = {
  normal: Zap,
  sleep: Moon,
  away: LogOut,
}

export default function Header() {
  const location = useLocation()
  const title = ROUTE_TITLES[location.pathname] || 'HEMS'

  const { audioEnabled, toggleAudio } = useAudioContext()
  const { avatarMode, cycleAvatarMode } = useAvatarContext()
  const { sttMode, cycleSTTMode } = useSttContext()
  const { darkModePreference, cycleDarkMode, isSecretActive, activeConfig } = useAppUiContext()
  const { powerMode, cyclePowerMode, powerModePending } = usePowerContext()

  // Environment data from zones query (same queryKey as AppLayoutWithZones → dedup)
  const zonesQuery = useZones()
  const environment = zonesQuery.data?.[0]?.environment

  const DarkModeIcon = darkModePreference === 'dark' ? Moon :
    darkModePreference === 'light' ? Sun : Gauge

  const sttOff = sttMode === 'off'
  const PowerIcon = POWER_MODE_ICONS[powerMode]

  return (
    <header className="sticky top-0 z-30 flex items-center justify-between h-14 border-b border-border bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/80 px-4 lg:px-6">
      <h1 className="text-lg font-semibold text-foreground">
        {isSecretActive && activeConfig && (
          <span className="text-xs text-primary/50 mr-1">{activeConfig.accentSymbol}</span>
        )}
        {title}
      </h1>
      <div className="flex items-center gap-2">
        {/* Environment indicators */}
        {environment && (
          <div className="hidden sm:flex items-center gap-3 text-xs text-muted-foreground mr-2">
            {environment.temperature != null && (
              <span className="flex items-center gap-1">
                <Thermometer className="h-3.5 w-3.5 text-chart-red" />
                <span className="font-medium text-foreground">{environment.temperature.toFixed(1)}°</span>
              </span>
            )}
            {environment.humidity != null && (
              <span className="flex items-center gap-1">
                <Droplets className="h-3.5 w-3.5 text-chart-blue" />
                <span className="font-medium text-foreground">{environment.humidity.toFixed(0)}%</span>
              </span>
            )}
            {environment.co2 != null && (
              <span className="flex items-center gap-1">
                <Wind className={cn('h-3.5 w-3.5', environment.co2 < 800 ? 'text-chart-green' : environment.co2 < 1500 ? 'text-warning' : 'text-destructive')} />
                <span className="font-medium text-foreground">{Math.round(environment.co2)}</span>
                <span className="text-[10px]">ppm</span>
              </span>
            )}
          </div>
        )}
        <div className="lg:hidden flex gap-1">
          <Button variant="ghost" size="icon" onClick={toggleAudio} aria-label="オーディオ切替" className="h-9 w-9">
            {audioEnabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={cycleSTTMode}
            aria-label={`音声入力: ${STT_MODE_LABELS[sttMode]}`}
            className={cn('h-9 w-9 relative', !sttOff && 'text-primary')}
          >
            {sttOff ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
            {!sttOff && (
              <span className="absolute -bottom-0.5 left-1/2 -translate-x-1/2 text-[8px] font-bold leading-none">
                {STT_MODE_LABELS[sttMode]}
              </span>
            )}
          </Button>
          <Button variant="ghost" size="icon" onClick={cycleDarkMode} aria-label="テーマ切替" className="h-9 w-9">
            <DarkModeIcon className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={cycleAvatarMode}
            aria-label="アバター切替"
            className={cn('h-9 w-9', avatarMode !== 'hidden' && 'text-primary')}
          >
            <User className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={cyclePowerMode}
            disabled={powerModePending}
            aria-label={`電力モード: ${powerMode}`}
            className={cn('h-9 w-9', powerMode !== 'normal' && 'text-amber-500')}
          >
            <PowerIcon className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </header>
  )
}
