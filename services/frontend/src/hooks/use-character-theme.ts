import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  type CharacterTheme,
  CHARACTER_THEMES,
  THEME_CYCLE_ORDER,
  THEME_STORAGE_KEY,
} from '@/lib/character-themes'
import { useKonami } from '@/hooks/use-konami'

export function useCharacterTheme() {
  const [theme, setThemeState] = useState<CharacterTheme>(() => {
    const params = new URLSearchParams(window.location.search)
    const urlTheme = params.get('theme') as CharacterTheme | null
    if (urlTheme && THEME_CYCLE_ORDER.includes(urlTheme)) return urlTheme

    const stored = localStorage.getItem(THEME_STORAGE_KEY)
    if (stored && THEME_CYCLE_ORDER.includes(stored as CharacterTheme)) {
      return stored as CharacterTheme
    }

    return 'default'
  })

  useEffect(() => {
    if (theme === 'default') {
      document.documentElement.removeAttribute('data-theme')
    } else {
      document.documentElement.setAttribute('data-theme', theme)
    }
  }, [theme])

  useEffect(() => {
    if (theme === 'default') {
      localStorage.removeItem(THEME_STORAGE_KEY)
    } else {
      localStorage.setItem(THEME_STORAGE_KEY, theme)
    }
  }, [theme])

  const cycleTheme = useCallback(() => {
    setThemeState((prev) => {
      const idx = THEME_CYCLE_ORDER.indexOf(prev)
      return THEME_CYCLE_ORDER[(idx + 1) % THEME_CYCLE_ORDER.length]
    })
  }, [])

  const sequences = useMemo(() =>
    Object.values(CHARACTER_THEMES).map((cfg) => ({
      keys: cfg.konamiSequence,
      onActivate: () => {
        setThemeState((prev) => prev === cfg.id ? 'default' : cfg.id)
      },
    })),
    []
  )

  useKonami(sequences)

  const isSecretActive = theme !== 'default'
  const activeConfig = theme !== 'default' ? CHARACTER_THEMES[theme] : null

  return { theme, cycleTheme, isSecretActive, activeConfig }
}
