import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [tailwindcss(), react()],
  server: {
    port: 5174,
    proxy: {
      '/api/wallet': {
        target: 'http://localhost:8003',
        rewrite: (path) => path.replace(/^\/api\/wallet/, ''),
      },
    },
  },
})
