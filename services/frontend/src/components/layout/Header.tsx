import { useLocation } from 'react-router'
import { Volume2, VolumeX, Sun, Moon, Gauge, User, Mic, MicOff } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import type { DarkModePreference } from '@/hooks/use-dark-mode'
import type { CharacterThemeConfig } from '@/lib/character-themes'
import type { AvatarMode } from '@/hooks/use-avatar-mode'
import type { STTMode } from '@/hooks/use-server-stt'

const ROUTE_TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/physical': 'Physical Space',
  '/digital': 'Digital Space',
  '/user': 'User State',
}

const STT_MODE_LABELS: Record<STTMode, string> = {
  'push-to-talk': 'PTT',
  auto: 'VAD',
  off: 'OFF',
}

interface Props {
  audioEnabled: boolean
  onToggleAudio: () => void
  darkModePreference: DarkModePreference
  onCycleDarkMode: () => void
  secretThemeActive?: boolean
  secretThemeConfig?: CharacterThemeConfig | null
  avatarMode: AvatarMode
  onCycleAvatarMode: () => void
  sttMode: STTMode
  onCycleSTTMode: () => void
}

export default function Header({
  audioEnabled,
  onToggleAudio,
  darkModePreference,
  onCycleDarkMode,
  secretThemeActive,
  secretThemeConfig,
  avatarMode,
  onCycleAvatarMode,
  sttMode,
  onCycleSTTMode,
}: Props) {
  const location = useLocation()
  const title = ROUTE_TITLES[location.pathname] || 'HEMS'

  const DarkModeIcon = darkModePreference === 'dark' ? Moon :
    darkModePreference === 'light' ? Sun : Gauge

  const sttOff = sttMode === 'off'

  return (
    <header className="sticky top-0 z-30 flex items-center justify-between h-14 border-b border-border bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/80 px-4 lg:px-6">
      <h1 className="text-lg font-semibold text-foreground">
        {secretThemeActive && secretThemeConfig && (
          <span className="text-xs text-primary/50 mr-1">{secretThemeConfig.accentSymbol}</span>
        )}
        {title}
      </h1>
      <div className="flex items-center gap-2">
        <div className="lg:hidden flex gap-1">
          <Button variant="ghost" size="icon" onClick={onToggleAudio} aria-label="オーディオ切替" className="h-9 w-9">
            {audioEnabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={onCycleSTTMode}
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
          <Button variant="ghost" size="icon" onClick={onCycleDarkMode} aria-label="テーマ切替" className="h-9 w-9">
            <DarkModeIcon className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={onCycleAvatarMode}
            aria-label="アバター切替"
            className={cn('h-9 w-9', avatarMode !== 'hidden' && 'text-primary')}
          >
            <User className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </header>
  )
}
