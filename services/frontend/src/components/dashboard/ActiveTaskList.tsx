import { memo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ListChecks, Plus } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import TaskCard from '@/components/shared/TaskCard'
import CreateTaskModal from '@/components/tasks/CreateTaskModal'
import { useTasks, TASKS_KEY } from '@/hooks/queries/use-tasks'
import { useAppContext } from '@/app/layout'

const ActiveTaskList = memo(function ActiveTaskList() {
  const { audioEnabled, enqueueAudio } = useAppContext()
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)

  const { data: tasks } = useTasks()

  const activeTasks = (tasks ?? [])
    .filter((t) => !t.is_completed && t.proposal_status !== 'dismissed')
    .sort((a, b) => b.urgency - a.urgency || a.id - b.id)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            <ListChecks className="h-4 w-4 text-primary" />
            Active Tasks ({activeTasks.length})
          </span>
          <Button size="sm" variant="ghost" onClick={() => setCreateOpen(true)} aria-label="タスク追加">
            <Plus className="h-4 w-4" />
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {activeTasks.length === 0 ? (
          <p className="text-sm text-muted-foreground py-6 text-center">
            タスクはありません
          </p>
        ) : (
          <div className="grid gap-3">
            {activeTasks.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                onComplete={() => queryClient.invalidateQueries({ queryKey: TASKS_KEY })}
                enqueueAudio={enqueueAudio}
                audioEnabled={audioEnabled}
              />
            ))}
          </div>
        )}
      </CardContent>
      <CreateTaskModal open={createOpen} onOpenChange={setCreateOpen} />
    </Card>
  )
})

export default ActiveTaskList
