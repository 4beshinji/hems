import { useLocation } from 'react-router'
import { Volume2, VolumeX, Sun, Moon, Gauge } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { DarkModePreference } from '@/hooks/use-dark-mode'

const ROUTE_TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/physical': 'Physical Space',
  '/digital': 'Digital Space',
  '/user': 'User State',
}

interface Props {
  audioEnabled: boolean
  onToggleAudio: () => void
  darkModePreference: DarkModePreference
  onCycleDarkMode: () => void
}

export default function Header({
  audioEnabled,
  onToggleAudio,
  darkModePreference,
  onCycleDarkMode,
}: Props) {
  const location = useLocation()
  const title = ROUTE_TITLES[location.pathname] || 'HEMS'

  const DarkModeIcon = darkModePreference === 'dark' ? Moon :
    darkModePreference === 'light' ? Sun : Gauge

  return (
    <header className="sticky top-0 z-30 flex items-center justify-between h-14 border-b border-border bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/80 px-4 lg:px-6">
      <h1 className="text-lg font-semibold text-foreground">{title}</h1>
      <div className="flex items-center gap-2">
        <div className="lg:hidden flex gap-1">
          <Button variant="ghost" size="icon" onClick={onToggleAudio} aria-label="オーディオ切替" className="h-9 w-9">
            {audioEnabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
          </Button>
          <Button variant="ghost" size="icon" onClick={onCycleDarkMode} aria-label="テーマ切替" className="h-9 w-9">
            <DarkModeIcon className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </header>
  )
}
