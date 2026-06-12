import { useQuery } from '@tanstack/react-query'
import { fetchTasks, fetchStats } from '@/lib/api/tasks'
import type { TaskData, SystemStatsResponse } from '@/lib/types'

export const TASKS_KEY = ['tasks'] as const
export const TASK_STATS_KEY = ['taskStats'] as const

export function useTasks() {
  return useQuery<TaskData[]>({
    queryKey: TASKS_KEY,
    queryFn: fetchTasks,
    refetchInterval: 15000,
    retry: false,
  })
}

export function useTaskStats() {
  return useQuery<SystemStatsResponse>({
    queryKey: TASK_STATS_KEY,
    queryFn: fetchStats,
    retry: false,
  })
}
