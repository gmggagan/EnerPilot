import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// /api is proxied to the FastAPI backend during development.
// Docker compose sets VITE_API_TARGET=http://backend:8000.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 1200,
  },
})
