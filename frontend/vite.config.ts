import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

/** В Docker (docker-compose) прокси на сервис `api`; локально — на хост. */
const apiProxyTarget = process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000'
const drawioProxyTarget = process.env.DRAWIO_PROXY_TARGET ?? 'http://127.0.0.1:8082'
/** Порт UI: как на VPS (COMPOSE_WEB_PORT, по умолчанию 8080). */
const devWebPort = Number(process.env.COMPOSE_WEB_PORT ?? 8080)
/** В контейнере bind-mount на Windows часто не даёт inotify — без polling Vite не видит правки. */
const dockerDev = !!process.env.API_PROXY_TARGET

export default defineConfig({
  plugins: [
    vue(),
    react(),
    {
      name: 'drawio-app-index',
      configureServer(server) {
        server.middlewares.use((req, _res, next) => {
          const url = req.url?.split('?')[0] || ''
          if (url === '/drawio-app' || url === '/drawio-app/') {
            req.url = '/drawio-app/embed.html'
          }
          next()
        })
      },
    },
    {
      name: 'mindmap-app-index',
      configureServer(server) {
        server.middlewares.use((req, _res, next) => {
          const url = req.url?.split('?')[0] || ''
          if (url === '/mindmap-app' || url === '/mindmap-app/') {
            req.url = '/mindmap-app/index.html'
          }
          next()
        })
      },
    },
  ],
  optimizeDeps: {
    include: [
      '@excalidraw/excalidraw',
      'react',
      'react-dom',
    ],
  },
  build: {
    /*
     * Тяжёлые редакторы — отдельными чанками, иначе они попадали в основной бандл
     * и замедляли первую отрисовку списка заметок. Excalidraw и CodeMirror
     * подгружаются только при раскрытии схемы или блока кода.
     */
    rollupOptions: {
      output: {
        /*
         * У @tiptap/pm нет экспорта "." — если указать пакет целиком,
         * production-сборка Vite (образ web в GHCR) падает.
         */
        manualChunks(id) {
          const normalized = id.replace(/\\/g, '/')
          if (
            normalized.includes('/node_modules/@excalidraw/')
            || normalized.includes('/node_modules/react/')
            || normalized.includes('/node_modules/react-dom/')
          ) {
            return 'excalidraw'
          }
          if (normalized.includes('/node_modules/@tiptap/')) {
            return 'tiptap'
          }
          if (
            normalized.includes('/node_modules/codemirror/')
            || normalized.includes('/node_modules/@codemirror/')
          ) {
            return 'codemirror'
          }
          if (normalized.includes('/node_modules/highlight.js/')) {
            return 'highlight'
          }
        },
      },
    },
    chunkSizeWarningLimit: 1200,
  },
  server: {
    host: true,
    port: devWebPort,
    watch: dockerDev ? { usePolling: true, interval: 1000 } : undefined,
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      // Только /drawio/… — иначе /drawio-app/embed.html попадает в Tomcat как /-app/embed.html (404).
      '/drawio/': {
        target: drawioProxyTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/drawio\/?/, '/'),
      },
    },
  },
})
