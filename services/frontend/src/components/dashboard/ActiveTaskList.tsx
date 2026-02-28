import { memo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ListChecks } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import TaskCard from '@/components/shared/TaskCard'
import { fetchTasks } from '@/lib/api'
import { useAppContext } from '@/app/layout'

const ActiveTaskList = memo(function ActiveTaskList() {
  const { audioEnabled, enqueueAudio } = useAppContext()
  const queryClient = useQueryClient()

  const { data: tasks } = useQuery({
    queryKey: ['tasks'],
    queryFn: fetchTasks,
    refetchInterval: 5000,
  })

  const activeTasks = (tasks ?? [])
    .filter((t) => !t.is_completed)
    .sort((a, b) => b.urgency - a.urgency || a.id - b.id)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ListChecks className="h-4 w-4 text-primary" />
          Active Tasks ({activeTasks.length})
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
                onComplete={() => queryClient.invalidateQueries({ queryKey: ['tasks'] })}
                enqueueAudio={enqueueAudio}
                audioEnabled={audioEnabled}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
})

export default ActiveTaskList
