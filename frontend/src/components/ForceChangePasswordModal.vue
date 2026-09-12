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
  background: var(--scrim-strong);
  display: grid;
  place-items: center;
  padding: 1.25rem;
  animation: ui-fade-in var(--dur-slow) var(--ease);
}
.force-pw-card {
  width: 100%;
  max-width: 400px;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1.15rem 1.2rem 1.25rem;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  background: var(--surface-overlay);
  box-shadow: var(--shadow-xl);
  color: var(--text-1);
  animation: ui-pop-in var(--dur-slow) var(--ease);
}
h2 {
  margin: 0;
  font-size: var(--fs-lg);
}
p.muted {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-muted);
  line-height: var(--lh-normal);
}
label {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  font-size: var(--fs-sm);
}
input {
  padding: var(--space-4) var(--space-5);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--surface-1);
  color: var(--text-1);
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
</style>
