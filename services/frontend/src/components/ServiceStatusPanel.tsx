import { Mail, Github, Globe, Check, AlertTriangle } from 'lucide-react'
import type { ServicesData, ServiceStatusItem } from '../App'

interface Props {
  services: ServicesData | null
}

const ICON_MAP: Record<string, typeof Mail> = {
  gmail: Mail,
  github: Github,
}

function ServiceIcon({ name }: { name: string }) {
  const Icon = ICON_MAP[name] ?? Globe
  return <Icon className="w-4 h-4" />
}

function formatElapsed(lastCheck: number): string {
  if (!lastCheck) return ''
  const elapsed = Math.floor(Date.now() / 1000 - lastCheck)
  if (elapsed < 60) return `${elapsed}秒前`
  if (elapsed < 3600) return `${Math.floor(elapsed / 60)}分前`
  return `${Math.floor(elapsed / 3600)}時間前`
}

function ServiceItem({ svc }: { svc: ServiceStatusItem }) {
  const hasUnread = svc.unread_count > 0

  return (
    <div className="flex items-center gap-3 px-3 py-2 rounded-lg bg-gray-50">
      <div className={`flex-shrink-0 ${svc.error ? 'text-red-400' : hasUnread ? 'text-blue-500' : 'text-green-500'}`}>
        <ServiceIcon name={svc.name} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-700 capitalize">{svc.name}</span>
          {svc.error ? (
            <AlertTriangle className="w-3.5 h-3.5 text-red-400" />
          ) : hasUnread ? (
            <span className="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 text-xs font-bold text-white bg-blue-500 rounded-full">
              {svc.unread_count}
            </span>
          ) : (
            <Check className="w-3.5 h-3.5 text-green-500" />
          )}
        </div>
        <p className="text-xs text-gray-500 truncate">
          {svc.summary || (svc.error ? 'エラー' : '確認済み')}
        </p>
      </div>
      <span className="text-[10px] text-gray-400 flex-shrink-0">
        {formatElapsed(svc.last_check)}
      </span>
    </div>
  )
}

export default function ServiceStatusPanel({ services }: Props) {
  if (!services || services.status === 'no_data') return null

  const items: ServiceStatusItem[] = Object.values(services).filter(
    (v): v is ServiceStatusItem => typeof v === 'object' && v !== null && 'name' in v
  )

  if (items.length === 0) return null

  return (
    <div className="bg-white rounded-xl elevation-2 p-5 mt-4">
      <h3 className="font-semibold text-gray-800 flex items-center gap-2 mb-3">
        <Globe className="w-5 h-5 text-teal-500" />
        Services
      </h3>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {items.map(svc => (
          <ServiceItem key={svc.name} svc={svc} />
        ))}
      </div>
    </div>
  )
}
