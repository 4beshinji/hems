import { createContext, useContext, useMemo, type ReactNode } from 'react'
import { useDarkMode, type DarkModePreference } from '@/hooks/use-dark-mode'
import { useCharacterTheme } from '@/hooks/use-character-theme'
import type { CharacterThemeConfig } from '@/lib/character-themes'

interface AppUiContextValue {
  darkModePreference: DarkModePreference
  cycleDarkMode: () => void
  isSecretActive: boolean
  activeConfig: CharacterThemeConfig | null
  cycleCharacterTheme: () => void
}

const AppUiContext = createContext<AppUiContextValue | null>(null)

interface AppUiProviderProps {
  children: ReactNode
  currentLux?: number | null
}

export function AppUiProvider({ children, currentLux }: AppUiProviderProps) {
  const { preference: darkModePreference, cycle: cycleDarkMode } = useDarkMode(currentLux)
  const { cycleTheme: cycleCharacterTheme, isSecretActive, activeConfig } = useCharacterTheme()

  const value = useMemo<AppUiContextValue>(
    () => ({
      darkModePreference,
      cycleDarkMode,
      isSecretActive,
      activeConfig,
      cycleCharacterTheme,
    }),
    [darkModePreference, cycleDarkMode, isSecretActive, activeConfig, cycleCharacterTheme],
  )

  return <AppUiContext.Provider value={value}>{children}</AppUiContext.Provider>
}

export function useAppUiContext(): AppUiContextValue {
  const ctx = useContext(AppUiContext)
  if (!ctx) throw new Error('useAppUiContext must be used within AppUiProvider')
  return ctx
}
