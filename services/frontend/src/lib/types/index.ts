// ─── Domain type barrel ───────────────────────────────────────────────────────
// Re-exports all types from domain-specific modules.
// Import from '@/lib/types' or 'src/lib/types' as before — this barrel preserves
// backwards-compatibility while keeping each domain file focused.

export * from './voice'
export * from './task'
export * from './timeline'
export * from './zone'
export * from './system'
export * from './integrations'
export * from './biometric'
export * from './perception'
export * from './home'
export * from './shopping'
export * from './chat'
export * from './brain'
export * from './device'
export * from './scene'
export * from './mobile'
export * from './approval'
export * from './feedback'
export * from './threshold'
