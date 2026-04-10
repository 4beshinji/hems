import { apiFetch } from '@/lib/api-client'
import type { KnowledgeData } from '@/lib/types'

export const fetchKnowledge = (): Promise<KnowledgeData> =>
  apiFetch('/knowledge/')
