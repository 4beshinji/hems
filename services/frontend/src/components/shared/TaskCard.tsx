import { useState, memo } from 'react'
import { motion } from 'framer-motion'
import { CheckCircle, Clock, MapPin, Zap } from 'lucide-react'
import { toast } from 'sonner'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { completeTask } from '@/lib/api'
import { URGENCY_LABELS, URGENCY_VARIANTS, REPORT_STATUS_LABELS } from '@/lib/constants'
import { AudioPriority } from '@/audio'
import type { TaskData } from '@/lib/types'

interface Props {
  task: TaskData
  onComplete: () => void
  enqueueAudio: (url: string, priority: AudioPriority) => void
  audioEnabled: boolean
}

const TaskCard = memo(function TaskCard({ task, onComplete, enqueueAudio, audioEnabled }: Props) {
  const [showDialog, setShowDialog] = useState(false)
  const [reportStatus, setReportStatus] = useState('no_issue')
  const [completionNote, setCompletionNote] = useState('')
  const [completing, setCompleting] = useState(false)

  const handleComplete = async () => {
    setCompleting(true)
    try {
      await completeTask(task.id, reportStatus, completionNote)
      if (audioEnabled && task.completion_audio_url) {
        enqueueAudio(task.completion_audio_url, AudioPriority.USER_ACTION)
      }
      toast.success('タスク完了！', { description: `+${task.xp_reward} XP` })
      onComplete()
      setShowDialog(false)
    } catch {
      toast.error('タスクの完了に失敗しました')
    } finally {
      setCompleting(false)
    }
  }

  const urgencyVariant = URGENCY_VARIANTS[task.urgency] ?? 'success'

  return (
    <>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        whileHover={{ y: -2 }}
      >
        <Card className="h-full flex flex-col">
          <CardContent className="flex-1 flex flex-col gap-3 p-5">
            <div className="flex items-start justify-between gap-2">
              <h3 className="font-semibold text-foreground text-base leading-tight">{task.title}</h3>
              <Badge variant={urgencyVariant} className="shrink-0">
                {URGENCY_LABELS[task.urgency] ?? '通常'}
              </Badge>
            </div>

            {task.description && (
              <p className="text-sm text-muted-foreground line-clamp-2">{task.description}</p>
            )}

            <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
              {task.zone && (
                <span className="flex items-center gap-1">
                  <MapPin className="h-3 w-3" />{task.zone}
                </span>
              )}
              {task.location && <span>{task.location}</span>}
              {task.estimated_duration && (
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />{task.estimated_duration}min
                </span>
              )}
            </div>

            <div className="flex items-center justify-between mt-auto pt-2 border-t border-border">
              <span className="flex items-center gap-1 text-xp-purple font-bold text-sm">
                <Zap className="h-4 w-4" />{task.xp_reward} XP
              </span>
              <Button size="sm" onClick={() => setShowDialog(true)}>
                Complete
              </Button>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>タスク完了報告</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium text-foreground">報告ステータス</label>
              <Select value={reportStatus} onValueChange={setReportStatus} className="mt-1">
                {Object.entries(REPORT_STATUS_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </Select>
            </div>
            <div>
              <label className="text-sm font-medium text-foreground">メモ (任意)</label>
              <textarea
                value={completionNote}
                onChange={(e) => setCompletionNote(e.target.value)}
                placeholder="完了メモ..."
                className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring resize-none"
                rows={3}
                maxLength={500}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDialog(false)}>
              キャンセル
            </Button>
            <Button onClick={handleComplete} disabled={completing}>
              <CheckCircle className="h-4 w-4" />
              {completing ? '処理中...' : '完了'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
})

export default TaskCard
