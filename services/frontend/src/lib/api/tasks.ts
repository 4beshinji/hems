import { apiFetch } from '@/lib/api-client'
import type { TaskData, SystemStatsResponse } from '@/lib/types'

export const fetchTasks = (): Promise<TaskData[]> =>
  apiFetch('/tasks/')

export const fetchStats = (): Promise<SystemStatsResponse> =>
  apiFetch('/tasks/stats')

export const completeTask = (
  taskId: number,
  reportStatus: string,
  completionNote: string
): Promise<void> =>
  apiFetch(`/tasks/${taskId}/complete`, {
    method: 'PUT',
    body: JSON.stringify({ report_status: reportStatus, completion_note: completionNote }),
  })
