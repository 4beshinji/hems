import { memo } from 'react'
import { Mail, Github, Globe, Check, AlertTriangle } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { formatAge } from '@/lib/formatters'
import type { ServicesData, ServiceStatusItem } from '@/lib/types'

const ICON_MAP: Record<string, typeof Mail> = {
  gmail: Mail,
  github: Github,
}

interface Props {
  services: ServicesData | null
}

const ServiceStatusPanel = memo(function ServiceStatusPanel({ services }: Props) {
  if (!services || services.status === 'no_data') return null

  const items: ServiceStatusItem[] = Object.values(services).filter(
    (v): v is ServiceStatusItem => typeof v === 'object' && v !== null && 'name' in v
  )

  if (items.length === 0) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Globe className="h-4 w-4 text-info" />
          Services
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {items.map((svc) => {
            const Icon = ICON_MAP[svc.name] ?? Globe
            const hasUnread = svc.unread_count > 0
            return (
              <div key={svc.name} className="flex items-center gap-3 px-3 py-2 rounded-lg bg-secondary/50">
                <Icon className={`h-4 w-4 shrink-0 ${svc.error ? 'text-destructive' : hasUnread ? 'text-info' : 'text-success'}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-foreground capitalize">{svc.name}</span>
                    {svc.error ? (
                      <AlertTriangle className="h-3.5 w-3.5 text-destructive" />
                    ) : hasUnread ? (
                      <Badge variant="info" className="text-[10px] px-1.5 py-0">
                        {svc.unread_count}
                      </Badge>
                    ) : (
                      <Check className="h-3.5 w-3.5 text-success" />
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground truncate">
                    {svc.summary || (svc.error ? 'エラー' : '確認済み')}
                  </p>
                </div>
                <span className="text-[10px] text-muted-foreground shrink-0">
                  {formatAge(svc.last_check)}
                </span>
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
})

export default ServiceStatusPanel
