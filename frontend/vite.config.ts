import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

/** В Docker (docker-compose) прокси на сервис `api`; локально — на хост. */
const apiProxyTarget = process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000'
/** Порт UI: как на VPS (COMPOSE_WEB_PORT, по умолчанию 8080). */
const devWebPort = Number(process.env.COMPOSE_WEB_PORT ?? 8080)
/** В контейнере bind-mount на Windows часто не даёт inotify — без polling Vite не видит правки. */
const dockerDev = !!process.env.API_PROXY_TARGET

export default defineConfig({
  plugins: [vue(), react()],
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
        manualChunks: {
          excalidraw: ['@excalidraw/excalidraw', 'react', 'react-dom'],
          tiptap: [
            '@tiptap/vue-3',
            '@tiptap/starter-kit',
            '@tiptap/pm',
            '@tiptap/extension-table',
            '@tiptap/extension-image',
            '@tiptap/extension-link',
            '@tiptap/extension-highlight',
            '@tiptap/extension-color',
            '@tiptap/extension-text-style',
            '@tiptap/extension-task-list',
            '@tiptap/extension-task-item',
          ],
          codemirror: ['codemirror', '@codemirror/lang-sql', '@codemirror/lang-python'],
          highlight: ['highlight.js'],
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
    },
  },
})
