import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// En desarrollo Vite reenvía /api al backend: el navegador ve un único origen,
// así la cookie de sesión (SameSite=Strict) y el CSRF funcionan sin CORS.
const apiTarget = process.env.VITE_API_PROXY || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    watch: { usePolling: true },
    proxy: {
      '/api': { target: apiTarget, changeOrigin: false },
    },
  },
  preview: {
    proxy: { '/api': { target: apiTarget } },
  },
})
