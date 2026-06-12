import { useQuery } from '@tanstack/react-query'
import { fetchTasks, fetchStats } from '@/lib/api/tasks'
import type { TaskData, SystemStatsResponse } from '@/lib/types'

export const TASKS_KEY = ['tasks'] as const
export const TASK_STATS_KEY = ['taskStats'] as const

/**
 * 共有 tasks フック。
 * 最短 refetchInterval = 5000ms (layout/ActiveTaskList/usePsdEventDriven が要求する最短値)
 * TanStack Query は同一 queryKey で複数コンポーネントが呼んでも
 * 実 HTTP は 1 系統のみ。interval はここで一元管理する。
 */
export const TASKS_REFETCH_INTERVAL = 5000

export function useTasks() {
  return useQuery<TaskData[]>({
    queryKey: TASKS_KEY,
    queryFn: fetchTasks,
    refetchInterval: TASKS_REFETCH_INTERVAL,
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
