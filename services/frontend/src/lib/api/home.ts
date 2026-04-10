import { apiFetch } from '@/lib/api-client'
import type { HomeData } from '@/lib/types'

export const fetchHome = (): Promise<HomeData> =>
  apiFetch('/home/')

export const controlLight = (
  entity_id: string,
  on: boolean,
  brightness?: number,
  color_temp?: number
): Promise<void> =>
  apiFetch('/home/light/control', {
    method: 'POST',
    body: JSON.stringify({ entity_id, on, brightness, color_temp }),
  })

export const controlClimate = (
  entity_id: string,
  mode?: string,
  temperature?: number
): Promise<void> =>
  apiFetch('/home/climate/control', {
    method: 'POST',
    body: JSON.stringify({ entity_id, mode, temperature }),
  })

export const controlCover = (
  entity_id: string,
  action?: string,
  position?: number
): Promise<void> =>
  apiFetch('/home/cover/control', {
    method: 'POST',
    body: JSON.stringify({ entity_id, action, position }),
  })
