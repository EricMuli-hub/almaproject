import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  build: { chunkSizeWarningLimit: 1200 },
  test: { environment: 'jsdom', globals: true, setupFiles: ['./tests/setup.js'], testTimeout: 60000, hookTimeout: 60000 },
})
