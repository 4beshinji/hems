import { useState, useEffect, useCallback, useRef } from 'react'

export type DarkModePreference = 'sensor' | 'light' | 'dark'

const STORAGE_KEY = 'hems-dark-mode'
const LUX_THRESHOLD = 100

export function useDarkMode(currentLux?: number | null) {
  const [preference, setPreference] = useState<DarkModePreference>(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    return (stored as DarkModePreference) || 'sensor'
  })
  const [isDark, setIsDark] = useState(false)
  const consecutiveRef = useRef(0)
  const lastDirectionRef = useRef<'dark' | 'light' | null>(null)

  // Sensor-based auto-switch with hysteresis
  useEffect(() => {
    if (preference !== 'sensor' || currentLux == null) return

    const direction: 'dark' | 'light' = currentLux < LUX_THRESHOLD ? 'dark' : 'light'
    if (direction === lastDirectionRef.current) {
      consecutiveRef.current++
    } else {
      consecutiveRef.current = 1
      lastDirectionRef.current = direction
    }

    // Require 2 consecutive readings in same direction
    if (consecutiveRef.current >= 2) {
      setIsDark(direction === 'dark')
    }
  }, [preference, currentLux])

  // Manual override
  useEffect(() => {
    if (preference === 'light') setIsDark(false)
    if (preference === 'dark') setIsDark(true)
  }, [preference])

  // Apply to <html>
  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDark)
  }, [isDark])

  // Persist preference
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, preference)
  }, [preference])

  const cycle = useCallback(() => {
    setPreference((prev) => {
      const order: DarkModePreference[] = ['sensor', 'light', 'dark']
      const idx = order.indexOf(prev)
      return order[(idx + 1) % order.length]
    })
  }, [])

  return { isDark, preference, cycle }
}
