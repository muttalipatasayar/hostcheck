import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        // Üretim backend'i 8000'de (systemd, hostcheck kullanıcısı). Geliştirme
        // kopyası 8001'de duruyor: HOSTCHECK_API=http://localhost:8001 npm run dev
        target: process.env.HOSTCHECK_API || 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      }
    }
  }
})
