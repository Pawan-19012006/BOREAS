import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import cesium from 'vite-plugin-cesium'

// Same backend as the Shore frontend (see ../frontend/vite.config.ts) --
// boreas-core is the single source of truth for both applications. Run on a
// different dev port (5176) so Shore (5174) and Ship can run side by side.
export default defineConfig({
  plugins: [react(), (cesium as any)()],
  server: {
    port: 5176,
    proxy: {
      '/boreas-api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/boreas-api/, ''),
      },
    },
  },
})
