import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

/** В Docker (docker-compose) прокси на сервис `api`; локально — на хост. */
const apiProxyTarget = process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
})
