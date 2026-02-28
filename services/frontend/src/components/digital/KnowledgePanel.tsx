import { memo } from 'react'
import { BookOpen, FileText, RefreshCw } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import type { KnowledgeData } from '@/lib/types'

interface Props {
  knowledge: KnowledgeData | null
}

const KnowledgePanel = memo(function KnowledgePanel({ knowledge }: Props) {
  if (!knowledge || knowledge.status === 'no_data') return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-warning" />
          Knowledge Base
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex items-center gap-3 px-3 py-2 rounded-lg bg-secondary/50">
            <FileText className="h-4 w-4 text-warning shrink-0" />
            <div>
              <span className="text-sm font-medium text-foreground">
                {knowledge.total_notes} ノート
              </span>
              <p className="text-xs text-muted-foreground">
                {knowledge.indexed} indexed
              </p>
            </div>
          </div>
          {knowledge.recent_changes && knowledge.recent_changes.length > 0 && (
            <div className="flex items-center gap-3 px-3 py-2 rounded-lg bg-secondary/50">
              <RefreshCw className="h-4 w-4 text-info shrink-0" />
              <div className="min-w-0">
                <span className="text-sm font-medium text-foreground">最近の変更</span>
                <div className="space-y-0.5">
                  {knowledge.recent_changes.slice(-3).reverse().map((change, i) => (
                    <p key={i} className="text-xs text-muted-foreground truncate">
                      {change.title} ({change.action})
                    </p>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
})

export default KnowledgePanel
