import { useRef, useCallback, lazy, Suspense, type ComponentType } from 'react'
import { NavLink } from 'react-router'
import { LayoutDashboard, Monitor, Heart, Volume2, VolumeX, Sun, Moon, Gauge, User, Mic, MicOff, Zap, LogOut, Play, Cpu, Smartphone, ShieldCheck } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { useAudioContext } from '@/contexts/AudioContext'
import { useAvatarContext } from '@/contexts/AvatarContext'
import { useSttContext } from '@/contexts/SttContext'
import { useAppUiContext } from '@/contexts/AppUiContext'
import { usePowerContext } from '@/contexts/PowerContext'
import type { PowerMode } from '@/lib/types'
import type { AvatarMode } from '@/hooks/use-avatar-mode'
import type { STTMode } from '@/hooks/use-server-stt'
import { IS_PSD } from '@/lib/avatar-type'

const PsdBustUp = IS_PSD
  ? lazy(() => import('@/components/psd/PsdBustUp'))
  : null

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/devices', icon: Cpu, label: 'Devices' },
  { to: '/digital', icon: Monitor, label: 'Digital Space' },
  { to: '/user', icon: Heart, label: 'User State' },
  { to: '/mobile', icon: Smartphone, label: 'Mobile' },
  { to: '/approvals', icon: ShieldCheck, label: 'Approvals' },
] as const

const AVATAR_MODE_LABELS: Record<AvatarMode, string> = {
  hidden: '非表示',
  panel: 'パネル',
  overlay: 'オーバーレイ',
}

const STT_MODE_LABELS: Record<STTMode, string> = {
  'push-to-talk': 'PTT',
  auto: 'VAD',
  off: 'OFF',
}

const STT_LANG_LABELS: Record<string, string> = {
  ja: 'JP',
  en: 'EN',
  auto: 'Auto',
}

const LANG_CYCLE = ['ja', 'en', 'auto']

const POWER_MODE_ICONS: Record<PowerMode, ComponentType<{ className?: string }>> = {
  normal: Zap,
  sleep: Moon,
  away: LogOut,
}

const POWER_MODE_LABELS: Record<PowerMode, string> = {
  normal: '通常',
  sleep: 'スリープ',
  away: '外出',
}

interface Props {
  onOpenBatch: () => void
}

export default function AppSidebar({ onOpenBatch }: Props) {
  const { audioEnabled, toggleAudio } = useAudioContext()
  const { avatarMode, cycleAvatarMode } = useAvatarContext()
  const { sttMode, cycleSTTMode, sttLanguage, setSTTLanguage } = useSttContext()
  const { darkModePreference, cycleDarkMode, isSecretActive, activeConfig, cycleCharacterTheme } = useAppUiContext()
  const { powerMode, cyclePowerMode, powerModePending } = usePowerContext()

  const longPressTimer = useRef<ReturnType<typeof setTimeout>>(undefined)

  const handlePointerDown = useCallback(() => {
    longPressTimer.current = setTimeout(() => {
      cycleCharacterTheme()
    }, 2000)
  }, [cycleCharacterTheme])

  const handlePointerUp = useCallback(() => {
    clearTimeout(longPressTimer.current)
  }, [])

  const cycleLang = useCallback(() => {
    const idx = LANG_CYCLE.indexOf(sttLanguage)
    setSTTLanguage(LANG_CYCLE[(idx + 1) % LANG_CYCLE.length])
  }, [sttLanguage, setSTTLanguage])

  const DarkModeIcon = darkModePreference === 'dark' ? Moon :
    darkModePreference === 'light' ? Sun : Gauge
  const darkModeLabel = darkModePreference === 'dark' ? 'ダーク' :
    darkModePreference === 'light' ? 'ライト' : 'センサー'

  const sttOff = sttMode === 'off'
  const PowerIcon = POWER_MODE_ICONS[powerMode]

  return (
    <aside className="hidden lg:flex flex-col w-56 shrink-0 border-r border-border bg-card h-screen sticky top-0">
      <div className="flex items-center gap-2 px-5 h-14 border-b border-border">
        <div
          className={cn(
            'h-7 w-7 rounded-lg bg-primary flex items-center justify-center select-none',
            isSecretActive && 'ring-2 ring-primary/40'
          )}
          onPointerDown={handlePointerDown}
          onPointerUp={handlePointerUp}
          onPointerLeave={handlePointerUp}
        >
          <span className="text-primary-foreground text-xs font-bold">H</span>
        </div>
        <span className="font-semibold text-foreground">HEMS</span>
        {isSecretActive && activeConfig && (
          <span className="text-[9px] text-primary/60 leading-none">{activeConfig.accentSymbol}</span>
        )}
      </div>

      <nav className="p-3 space-y-1 shrink-0">
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              )
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Avatar bust-up — fills remaining sidebar space */}
      {avatarMode === 'panel' && PsdBustUp ? (
        <Suspense fallback={null}>
          <div className="flex-1 min-h-0 px-3">
            <PsdBustUp />
          </div>
        </Suspense>
      ) : (
        <div className="flex-1" />
      )}

      <div className="p-3 space-y-2">
        <Separator />
        {/* Audio + Dark mode row */}
        <div className="flex gap-1 px-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleAudio}
            aria-label={audioEnabled ? 'オーディオ OFF' : 'オーディオ ON'}
            className="h-9 w-9"
          >
            {audioEnabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={cycleDarkMode}
            aria-label={`テーマ: ${darkModeLabel}`}
            className="h-9 gap-1.5"
          >
            <DarkModeIcon className="h-4 w-4" />
            <span className="text-xs">{darkModeLabel}</span>
          </Button>
        </div>
        {/* Avatar + STT row */}
        <div className="flex gap-1 px-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={cycleAvatarMode}
            aria-label={`アバター: ${AVATAR_MODE_LABELS[avatarMode]}`}
            className="h-9 gap-1.5"
          >
            <User className="h-4 w-4" />
            <span className="text-xs">{AVATAR_MODE_LABELS[avatarMode]}</span>
          </Button>
        </div>
        {/* STT controls */}
        <div className="flex gap-1 px-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={cycleSTTMode}
            aria-label={`音声入力: ${STT_MODE_LABELS[sttMode]}`}
            className={cn('h-9 gap-1.5', !sttOff && 'text-primary')}
          >
            {sttOff ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
            <span className="text-xs">音声 {STT_MODE_LABELS[sttMode]}</span>
          </Button>
          {!sttOff && (
            <Button
              variant="ghost"
              size="sm"
              onClick={cycleLang}
              aria-label={`STT言語: ${STT_LANG_LABELS[sttLanguage] ?? sttLanguage}`}
              className="h-9 px-2"
            >
              <span className="text-xs font-mono">{STT_LANG_LABELS[sttLanguage] ?? sttLanguage}</span>
            </Button>
          )}
        </div>
        {/* Power mode + Batch row */}
        <Separator />
        <div className="flex gap-1 px-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={cyclePowerMode}
            disabled={powerModePending}
            aria-label={`電力モード: ${POWER_MODE_LABELS[powerMode]}`}
            className={cn('h-9 gap-1.5', powerMode !== 'normal' && 'text-amber-500')}
          >
            <PowerIcon className="h-4 w-4" />
            <span className="text-xs">{POWER_MODE_LABELS[powerMode]}</span>
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={onOpenBatch}
            aria-label="バッチ実行"
            className="h-9 w-9"
          >
            <Play className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </aside>
  )
}
