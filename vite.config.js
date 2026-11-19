import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    // В режиме разработки запросы /api проксируются на локальный бэкенд
    proxy: {
      '/api': process.env.VITE_API_PROXY || 'http://localhost:8000',
    },
  },
})
