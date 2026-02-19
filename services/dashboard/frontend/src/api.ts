import { Task, TaskReport } from './components/TaskCard';

export interface SystemStats {
  total_xp: number;
  tasks_completed: number;
  tasks_created: number;
  tasks_active: number;
  tasks_queued: number;
  tasks_completed_last_hour: number;
}

export interface SupplyStats {
  total_issued: number;
  total_burned: number;
  circulating: number;
}

export const fetchTasks = async (): Promise<Task[]> => {
  const res = await fetch('/api/tasks/');
  if (!res.ok) throw new Error('Failed to fetch tasks');
  return res.json();
};

export const fetchStats = async (): Promise<SystemStats> => {
  const res = await fetch('/api/tasks/stats');
  if (!res.ok) throw new Error('Failed to fetch stats');
  return res.json();
};

export const fetchSupply = async (): Promise<SupplyStats> => {
  const res = await fetch('/api/wallet/supply');
  if (!res.ok) throw new Error('Failed to fetch supply');
  return res.json();
};

export const fetchVoiceEvents = async (): Promise<{ id: number; audio_url: string }[]> => {
  const res = await fetch('/api/voice-events/recent');
  if (!res.ok) throw new Error('Failed to fetch voice events');
  return res.json();
};

export const acceptTask = async (taskId: number): Promise<void> => {
  const res = await fetch(`/api/tasks/${taskId}/accept`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error('Failed to accept task');
};

export const completeTask = async ({
  taskId,
  report,
}: {
  taskId: number;
  report?: TaskReport;
}): Promise<Task> => {
  const res = await fetch(`/api/tasks/${taskId}/complete`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      report_status: report?.status || null,
      completion_note: report?.note || null,
    }),
  });
  if (!res.ok) throw new Error('Failed to complete task');
  return res.json();
};
