export type CharacterTheme = 'default' | 'yukari' | 'una' | 'nurse'

export interface CharacterThemeConfig {
  id: CharacterTheme
  name: string
  accentSymbol: string
  konamiSequence: string[]
}

export const CHARACTER_THEMES: Record<Exclude<CharacterTheme, 'default'>, CharacterThemeConfig> = {
  yukari: {
    id: 'yukari',
    name: '結月ゆかり',
    accentSymbol: '🌙',
    konamiSequence: ['y', 'u', 'k', 'a', 'r', 'i'],
  },
  una: {
    id: 'una',
    name: '音街ウナ',
    accentSymbol: '🐟',
    konamiSequence: ['u', 'n', 'a'],
  },
  nurse: {
    id: 'nurse',
    name: 'ナースロボ＿タイプT',
    accentSymbol: '💉',
    konamiSequence: ['n', 'u', 'r', 's', 'e'],
  },
}

export const THEME_CYCLE_ORDER: CharacterTheme[] = ['default', 'yukari', 'una', 'nurse']

export const THEME_STORAGE_KEY = 'hems-character-theme'
