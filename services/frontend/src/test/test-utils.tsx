/**
 * Shared test utilities for W5.1+.
 *
 * Usage:
 *   import { renderWithQuery, createTestQueryClient } from '@/test/test-utils'
 *
 * W5.2 (query dedup) and W5.4 (context split) tests should import the wrapper
 * from here so setup stays centralised.
 */
import { type ReactNode } from 'react'
import { render, type RenderOptions } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

/** Create a fresh QueryClient with sane test defaults (no retries, instant GC). */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        // Avoid "act()" warnings: keep stale data, no background refetching
        staleTime: Infinity,
        gcTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  })
}

interface WrapperProps {
  children: ReactNode
}

/**
 * Build a React wrapper that provides a fresh QueryClient.
 * Pass the returned component to RTL's `render({ wrapper })`.
 */
export function makeQueryWrapper(client?: QueryClient) {
  const qc = client ?? createTestQueryClient()
  function QueryWrapper({ children }: WrapperProps) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  }
  return QueryWrapper
}

/** Convenience: render component inside a fresh QueryClientProvider. */
export function renderWithQuery(
  ui: React.ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>
) {
  return render(ui, { wrapper: makeQueryWrapper(), ...options })
}
