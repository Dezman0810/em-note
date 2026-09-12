import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { initNoteLayout } from './composables/useNoteLayout'
import { initTheme } from './composables/useTheme'
import './style.css'

initTheme()
initNoteLayout()

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
