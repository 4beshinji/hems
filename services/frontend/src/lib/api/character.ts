import { apiFetch } from '@/lib/api-client'

export interface CharacterInfo {
  name: string
  archetype: string
  first_person: string
  second_person: string | null
  voice_credit: string | null
}

export const fetchCharacter = (): Promise<CharacterInfo> =>
  apiFetch('/character/')
