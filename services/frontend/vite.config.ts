import path from 'path'
import fs from 'fs'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Load HEMS_API_KEY from the repo root .env (2 levels up from services/frontend/)
// so that `pnpm dev` works without manual env var injection.
function loadHEMSApiKey(): string {
  // 1. Prefer explicit env var (CI / override)
  if (process.env.HEMS_API_KEY) return process.env.HEMS_API_KEY

  // 2. Fall back to repo-root .env
  const envPath = path.resolve(__dirname, '../../.env')
  if (fs.existsSync(envPath)) {
    const line = fs.readFileSync(envPath, 'utf8')
      .split('\n')
      .find(l => l.startsWith('HEMS_API_KEY='))
    if (line) return line.slice('HEMS_API_KEY='.length).trim()
  }

  return ''
}

const apiKey = loadHEMSApiKey()

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy /api/* → backend (mirrors nginx behaviour in production).
      // Injects Authorization header so auth is transparent to the React app.
      '/api': {
        target: process.env.VITE_BACKEND_URL ?? 'http://localhost:8010',
        rewrite: (p) => p.replace(/^\/api/, ''),
        headers: {
          Authorization: `Bearer ${apiKey}`,
        },
      },
    },
  },
})
