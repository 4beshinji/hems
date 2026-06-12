import { createContext, useContext, useMemo, type ReactNode } from 'react'
import { usePowerMode } from '@/hooks/use-power-mode'
import type { PowerMode } from '@/lib/types'

interface PowerContextValue {
  powerMode: PowerMode
  cyclePowerMode: () => void
  powerModePending: boolean
}

const PowerContext = createContext<PowerContextValue | null>(null)

export function PowerProvider({ children }: { children: ReactNode }) {
  const { mode: powerMode, cycleMode: cyclePowerMode, isPending: powerModePending } = usePowerMode()

  const value = useMemo<PowerContextValue>(
    () => ({ powerMode, cyclePowerMode, powerModePending }),
    [powerMode, cyclePowerMode, powerModePending],
  )

  return <PowerContext.Provider value={value}>{children}</PowerContext.Provider>
}

export function usePowerContext(): PowerContextValue {
  const ctx = useContext(PowerContext)
  if (!ctx) throw new Error('usePowerContext must be used within PowerProvider')
  return ctx
}
