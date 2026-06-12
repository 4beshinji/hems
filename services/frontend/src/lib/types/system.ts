// ─── PC Metrics ───────────────────────────────────────────────────────────────
export interface PCCpu {
  usage_percent: number
  temp_c: number
}

export interface PCMemory {
  percent: number
  used_gb: number
  total_gb: number
}

export interface PCGpu {
  usage_percent: number
  temp_c: number
}

export interface PCDisk {
  mount: string
  percent: number
  used_gb: number
  total_gb: number
}

export interface PCProcess {
  name: string
  cpu_percent: number
  mem_mb: number
  pid: number
}

export interface PCMetrics {
  status?: string | null
  bridge_connected?: boolean
  cpu?: PCCpu | null
  memory?: PCMemory | null
  gpu?: PCGpu | null
  disk?: PCDisk[] | null
  top_processes?: PCProcess[] | null
  last_update?: number | null
}

// ─── Services ─────────────────────────────────────────────────────────────────
export interface ServiceStatusItem {
  name: string
  status: string
  unread_count: number
  last_check?: string | null
  error?: string | null
  summary?: string | null
}

export interface ServicesData {
  status?: string | null
  [key: string]: unknown
}
