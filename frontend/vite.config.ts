import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the frontend runs on :5173 and proxies to the backend on :8000.
// In production the backend serves the built assets itself, so no proxy is involved.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
