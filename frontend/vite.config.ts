import react from '@vitejs/plugin-react'
// From vitest/config, not vite: the plain `defineConfig` has no `test` key, so
// `tsc --noEmit` would reject the block below.
import { defineConfig } from 'vitest/config'

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
  test: {
    // jsdom rather than node: the things worth testing here read localStorage
    // and navigator.language, and one of them has to survive both of those
    // throwing. A node environment would make those cases untestable.
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['src/test-setup.ts'],
    restoreMocks: true,
  },
})
