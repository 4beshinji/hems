import { NavLink } from 'react-router'
import { LayoutDashboard, Thermometer, Monitor, Heart } from 'lucide-react'
import { cn } from '@/lib/utils'

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, label: 'Home' },
  { to: '/physical', icon: Thermometer, label: 'Physical' },
  { to: '/digital', icon: Monitor, label: 'Digital' },
  { to: '/user', icon: Heart, label: 'User' },
] as const

interface Props {
  activeTasks?: number
}

export default function BottomNav({ activeTasks }: Props) {
  return (
    <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-40 border-t border-border bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/80">
      <div className="flex items-center justify-around h-14">
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              cn(
                'relative flex flex-col items-center gap-0.5 px-3 py-1 text-xs transition-colors',
                isActive ? 'text-primary' : 'text-muted-foreground'
              )
            }
          >
            <Icon className="h-5 w-5" />
            <span>{label}</span>
            {to === '/' && activeTasks != null && activeTasks > 0 && (
              <span className="absolute -top-0.5 right-1 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-bold text-destructive-foreground">
                {activeTasks}
              </span>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
