import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// En desarrollo Vite reenvía /api al backend: el navegador ve un único origen,
// así la cookie de sesión (SameSite=Strict) y el CSRF funcionan sin CORS.
const apiTarget = process.env.VITE_API_PROXY || 'http://localhost:8000'

// Paquete compartido con la app móvil (docs/rfc-001 §8.4). Vive fuera de frontend/ (en packages/core):
// los alias se derivan de su `exports`, así no hay una segunda lista que mantener.
const core = fileURLToPath(new URL('../packages/core/', import.meta.url))
const exportsDelPaquete = JSON.parse(readFileSync(`${core}package.json`, 'utf-8')).exports
const aliasDelCore = Object.entries(exportsDelPaquete).map(([subruta, archivo]) => ({
  find: new RegExp(`^@panaderia/core${subruta === '.' ? '' : subruta.slice(1)}$`),
  replacement: fileURLToPath(new URL(`../packages/core/${archivo}`, import.meta.url)),
}))

export default defineConfig({
  plugins: [react()],
  resolve: { alias: aliasDelCore },
  server: {
    host: true,
    port: 5173,
    watch: { usePolling: true },
    // Vite solo sirve archivos de la raíz del proyecto: el paquete compartido está al lado
    fs: { allow: ['.', core] },
    proxy: {
      '/api': { target: apiTarget, changeOrigin: false },
    },
  },
  preview: {
    proxy: { '/api': { target: apiTarget } },
  },
})
