<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { errMessage } from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(email.value, password.value)
    const redirect = (route.query.redirect as string) || '/'
    await router.push(redirect)
  } catch (e) {
    error.value = errMessage(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="page">
    <form class="card" @submit.prevent="submit">
      <h1>Вход</h1>
      <label>
        Email
        <input v-model="email" type="email" autocomplete="username" required />
      </label>
      <label>
        Пароль
        <input v-model="password" type="password" autocomplete="current-password" required />
      </label>
      <p v-if="error" class="err">{{ error }}</p>
      <button type="submit" :disabled="loading">{{ loading ? '…' : 'Войти' }}</button>
      <RouterLink class="link" to="/register">Регистрация</RouterLink>
    </form>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 2rem;
}
.card {
  width: 100%;
  max-width: 360px;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
h1 {
  margin: 0;
  font-size: 1.35rem;
}
label {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  font-size: 0.9rem;
}
input {
  padding: 0.5rem 0.65rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: inherit;
}
button {
  padding: 0.6rem;
  border-radius: 8px;
  border: none;
  background: var(--accent);
  color: #fff;
  font-weight: 600;
  cursor: pointer;
}
button:disabled {
  opacity: 0.6;
  cursor: default;
}
.err {
  color: var(--danger);
  margin: 0;
  font-size: 0.9rem;
}
.link {
  text-align: center;
  color: var(--accent);
  text-decoration: none;
}
</style>
