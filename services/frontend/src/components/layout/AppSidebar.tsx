import { NavLink } from 'react-router'
import { LayoutDashboard, Thermometer, Monitor, Heart, Volume2, VolumeX, Sun, Moon, Gauge } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import type { DarkModePreference } from '@/hooks/use-dark-mode'

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/physical', icon: Thermometer, label: 'Physical Space' },
  { to: '/digital', icon: Monitor, label: 'Digital Space' },
  { to: '/user', icon: Heart, label: 'User State' },
] as const

interface Props {
  audioEnabled: boolean
  onToggleAudio: () => void
  darkModePreference: DarkModePreference
  onCycleDarkMode: () => void
  totalXp?: number
}

export default function AppSidebar({
  audioEnabled,
  onToggleAudio,
  darkModePreference,
  onCycleDarkMode,
  totalXp,
}: Props) {
  const DarkModeIcon = darkModePreference === 'dark' ? Moon :
    darkModePreference === 'light' ? Sun : Gauge
  const darkModeLabel = darkModePreference === 'dark' ? 'ダーク' :
    darkModePreference === 'light' ? 'ライト' : 'センサー'

  return (
    <aside className="hidden lg:flex flex-col w-56 shrink-0 border-r border-border bg-card h-screen sticky top-0">
      <div className="flex items-center gap-2 px-5 h-14 border-b border-border">
        <div className="h-7 w-7 rounded-lg bg-primary flex items-center justify-center">
          <span className="text-primary-foreground text-xs font-bold">H</span>
        </div>
        <span className="font-semibold text-foreground">HEMS</span>
      </div>

      <nav className="flex-1 p-3 space-y-1">
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

      <div className="p-3 space-y-2">
        <Separator />
        {totalXp != null && (
          <div className="flex items-center gap-2 px-3 py-2 text-sm">
            <span className="font-bold text-xp-purple">{totalXp} XP</span>
          </div>
        )}
        <div className="flex gap-1 px-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggleAudio}
            aria-label={audioEnabled ? 'オーディオ OFF' : 'オーディオ ON'}
            className="h-9 w-9"
          >
            {audioEnabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onCycleDarkMode}
            aria-label={`テーマ: ${darkModeLabel}`}
            className="h-9 gap-1.5"
          >
            <DarkModeIcon className="h-4 w-4" />
            <span className="text-xs">{darkModeLabel}</span>
          </Button>
        </div>
      </div>
    </aside>
  )
}
