import { memo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Zap, Trophy, CheckCircle, Plus } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { fetchStats } from '@/lib/api'

const XPPanel = memo(function XPPanel() {
  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: fetchStats,
    refetchInterval: 10000,
  })

  if (!stats) return null

  const level = Math.floor(stats.total_xp / 1000) + 1
  const xpInLevel = stats.total_xp % 1000
  const xpProgress = (xpInLevel / 1000) * 100

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Trophy className="h-4 w-4 text-xp-purple" />
          XP / Gamification
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="text-center">
          <Badge className="bg-xp-purple text-xp-purple-foreground mb-2">Lv.{level}</Badge>
          <div className="text-3xl font-bold text-xp-purple flex items-center justify-center gap-1">
            <Zap className="h-6 w-6" />
            {stats.total_xp.toLocaleString()}
            <span className="text-sm font-normal text-muted-foreground ml-1">XP</span>
          </div>
          <div className="mt-2">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>Lv.{level}</span>
              <span>Lv.{level + 1}</span>
            </div>
            <Progress value={xpProgress} className="h-2" indicatorClassName="bg-xp-purple" />
            <p className="text-xs text-muted-foreground mt-1">{xpInLevel}/1000 XP</p>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="rounded-lg bg-secondary/50 p-3">
            <CheckCircle className="h-4 w-4 text-success mx-auto mb-1" />
            <p className="text-lg font-bold text-foreground">{stats.tasks_completed}</p>
            <p className="text-[10px] text-muted-foreground">完了</p>
          </div>
          <div className="rounded-lg bg-secondary/50 p-3">
            <Plus className="h-4 w-4 text-info mx-auto mb-1" />
            <p className="text-lg font-bold text-foreground">{stats.tasks_created}</p>
            <p className="text-[10px] text-muted-foreground">作成</p>
          </div>
          <div className="rounded-lg bg-secondary/50 p-3">
            <Zap className="h-4 w-4 text-warning mx-auto mb-1" />
            <p className="text-lg font-bold text-foreground">{stats.tasks_active}</p>
            <p className="text-[10px] text-muted-foreground">アクティブ</p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
})

export default XPPanel
