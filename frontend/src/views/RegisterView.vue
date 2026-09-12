<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { errMessage } from '../api/client'
import { useTheme } from '../composables/useTheme'
import { useAuthStore } from '../stores/auth'

const { label: themeLabel, icon: themeIcon, cycleTheme } = useTheme()

const auth = useAuthStore()
const router = useRouter()
const email = ref('')
const password = ref('')
const displayName = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.register(email.value, password.value, displayName.value || undefined)
    await router.push('/')
  } catch (e) {
    error.value = errMessage(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="page">
    <button
      type="button"
      class="theme-toggle page-theme"
      :aria-label="themeLabel"
      :title="themeLabel"
      @click="cycleTheme"
    >
      <span class="theme-toggle-glyph" aria-hidden="true">{{ themeIcon }}</span>
    </button>
    <form class="card" @submit.prevent="submit">
      <h1>Регистрация</h1>
      <label>
        Имя (необязательно)
        <input v-model="displayName" type="text" autocomplete="nickname" />
      </label>
      <label>
        Email
        <input v-model="email" type="email" autocomplete="username" required />
      </label>
      <label>
        Пароль (мин. 8 символов)
        <input v-model="password" type="password" autocomplete="new-password" required minlength="8" />
      </label>
      <p v-if="error" class="err">{{ error }}</p>
      <button type="submit" :disabled="loading">{{ loading ? '…' : 'Создать аккаунт' }}</button>
      <RouterLink class="link" to="/login">Уже есть аккаунт</RouterLink>
    </form>
  </div>
</template>

<style scoped>
.page {
  position: relative;
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 2rem;
}
.page-theme {
  position: absolute;
  top: var(--space-6);
  right: var(--space-6);
}
.card {
  width: 100%;
  max-width: 360px;
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  padding: var(--space-8);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  background: var(--surface-1);
  box-shadow: var(--shadow-md);
}
h1 {
  margin: 0;
  font-size: var(--fs-xl);
  color: var(--text-1);
}
label {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  font-size: var(--fs-md);
  color: var(--text-2);
}
input {
  padding: var(--space-4) var(--space-5);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--surface-1);
  color: var(--text-1);
  font: inherit;
  transition: var(--transition-colors);
}
input:focus {
  border-color: var(--accent-border);
  outline: none;
  box-shadow: var(--shadow-focus);
}
button {
  padding: var(--space-5);
  border-radius: var(--radius-md);
  border: none;
  background: var(--accent);
  color: var(--text-on-accent);
  font: inherit;
  font-weight: var(--fw-semibold);
  cursor: pointer;
  transition: var(--transition-colors);
}
button:hover:not(:disabled) {
  background: var(--accent-hover);
}
button:disabled {
  opacity: 0.6;
  cursor: default;
}
.err {
  color: var(--danger-text);
  margin: 0;
  font-size: var(--fs-sm);
}
.link {
  text-align: center;
  color: var(--accent-text);
  text-decoration: none;
}
.link:hover {
  text-decoration: underline;
}

@media (max-width: 480px) {
  .page {
    padding: var(--space-6);
  }
  .card {
    padding: var(--space-6);
  }
}
</style>
