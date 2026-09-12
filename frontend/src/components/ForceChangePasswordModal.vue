<script setup lang="ts">
import { ref } from 'vue'
import { errMessage } from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const current = ref('')
const next = ref('')
const confirm = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  if (next.value.length < 8) {
    error.value = 'Новый пароль — минимум 8 символов'
    return
  }
  if (next.value !== confirm.value) {
    error.value = 'Новый пароль и подтверждение не совпадают'
    return
  }
  if (next.value === current.value) {
    error.value = 'Задайте пароль, отличный от временного'
    return
  }
  loading.value = true
  try {
    await auth.changePassword(current.value, next.value)
  } catch (e) {
    error.value = errMessage(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="force-pw-backdrop" role="dialog" aria-labelledby="force-pw-title" aria-modal="true">
    <form class="force-pw-card" @submit.prevent="submit">
      <h2 id="force-pw-title">Задайте свой пароль</h2>
      <p class="muted">
        Сейчас вы вошли по временному паролю от администратора. Старый восстановить нельзя — придумайте новый, чтобы дальше входить самостоятельно.
      </p>
      <label>
        Временный пароль
        <input v-model="current" type="password" autocomplete="current-password" required />
      </label>
      <label>
        Новый пароль
        <input v-model="next" type="password" autocomplete="new-password" required minlength="8" />
      </label>
      <label>
        Ещё раз новый
        <input v-model="confirm" type="password" autocomplete="new-password" required minlength="8" />
      </label>
      <p v-if="error" class="err">{{ error }}</p>
      <button type="submit" :disabled="loading">{{ loading ? '…' : 'Сохранить пароль' }}</button>
    </form>
  </div>
</template>

<style scoped>
.force-pw-backdrop {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: rgba(15, 23, 42, 0.55);
  display: grid;
  place-items: center;
  padding: 1.25rem;
}
.force-pw-card {
  width: 100%;
  max-width: 400px;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1.15rem 1.2rem 1.25rem;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: var(--panel);
  box-shadow: 0 12px 40px rgba(15, 23, 42, 0.18);
}
h2 {
  margin: 0;
  font-size: 1.1rem;
}
p.muted {
  margin: 0;
  font-size: 0.85rem;
  color: var(--text-muted);
  line-height: 1.4;
}
label {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  font-size: 0.88rem;
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
</style>
