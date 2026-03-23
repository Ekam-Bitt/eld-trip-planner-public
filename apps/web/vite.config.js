import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ command }) => {
  const isDev = command === 'serve'

  // Industry Standard: In development mode, Vite relies heavily on eval() for 
  // SourceMaps, inline styles for HMR, and WebSockets.
  // We completely omit the restrictive CSP in dev to avoid breaking the tooling.
  // A strict CSP should always be enforced by the production server/CDN (e.g. Nginx, Cloudflare, Vercel).
  const headers = isDev ? {} : {
    'Content-Security-Policy': [
      "default-src 'self'",
      "script-src 'self'",
      "style-src 'self'",
      "img-src 'self' data: https://*.tile.openstreetmap.org",
      "connect-src 'self'",
      "frame-ancestors 'none'",
    ].join('; '),
  }

  return {
    plugins: [react()],
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      headers,
      proxy: {
        '/api': {
          target: process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
