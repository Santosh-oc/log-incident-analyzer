import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const base = process.env.DKUBEX_BASE_PATH ? `${process.env.DKUBEX_BASE_PATH}/` : '/'

export default defineConfig({
  base,
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
