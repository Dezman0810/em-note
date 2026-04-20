<script setup lang="ts">
import { ref, watch } from 'vue'
import { adminApi, errMessage } from '../api/client'
import type { AdminUserRow } from '../api/types'
import { useAuthStore } from '../stores/auth'
import { fmtMsk } from '../utils/datetime'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ 'update:open': [v: boolean] }>()

const auth = useAuthStore()
const users = ref<AdminUserRow[]>([])
const loading = ref(false)
const err = ref('')
const pending = ref<string | null>(null)

async function load() {
  loading.value = true
  err.value = ''
  try {
    users.value = await adminApi.listUsers()
  } catch (e) {
    err.value = errMessage(e)
    users.value = []
  } finally {
    loading.value = false
  }
}

watch(
  () => props.open,
  (v) => {
    if (v) void load()
  }
)

async function toggle(row: AdminUserRow, ev: Event) {
  const input = ev.target as HTMLInputElement
  const next = input.checked
  pending.value = row.id
  err.value = ''
  try {
    await adminApi.setCanCreateNotes(row.id, next)
    row.can_create_notes = next
    if (auth.user?.id === row.id) {
      await auth.fetchMe()
    }
  } catch (e) {
    err.value = errMessage(e)
    input.checked = !next
  } finally {
    pending.value = null
  }
}

function close() {
  emit('update:open', false)
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="admin-modal-backdrop" @click.self="close">
      <div class="admin-modal" role="dialog" aria-labelledby="admin-modal-title">
        <div class="admin-modal-head">
          <h2 id="admin-modal-title">Пользователи</h2>
          <button type="button" class="admin-close" aria-label="Закрыть" @click="close">×</button>
        </div>
        <p class="muted small admin-lead">
          Галочка «создание заметок»: без неё пользователь может войти, но не создаёт новые заметки.
        </p>
        <p v-if="loading" class="muted small">Загрузка…</p>
        <p v-else-if="err" class="err">{{ err }}</p>
        <div v-else class="admin-table-wrap">
          <table class="admin-table">
            <thead>
              <tr>
                <th>Email</th>
                <th>Имя</th>
                <th>Регистрация</th>
                <th>Новые заметки</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in users" :key="u.id">
                <td class="admin-email">{{ u.email }}</td>
                <td>{{ u.display_name || '—' }}</td>
                <td class="admin-date muted">{{ fmtMsk(u.created_at) }}</td>
                <td class="admin-chk">
                  <input
                    type="checkbox"
                    :checked="u.can_create_notes"
                    :disabled="pending === u.id"
                    :aria-label="`Создание заметок для ${u.email}`"
                    @change="toggle(u, $event)"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.admin-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 1.5rem 1rem;
  box-sizing: border-box;
  overflow-y: auto;
}
.admin-modal {
  width: min(720px, 100%);
  margin-top: min(8vh, 4rem);
  border-radius: var(--radius-lg, 14px);
  border: 1px solid var(--border);
  background: var(--panel);
  box-shadow: var(--shadow-panel, 0 8px 40px rgba(15, 23, 42, 0.12));
  padding: 1rem 1.1rem 1.15rem;
  font-size: 0.85rem;
}
.admin-modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}
.admin-modal-head h2 {
  margin: 0;
  font-size: 1rem;
  font-weight: 650;
  color: var(--note-list-title-active, #0f172a);
}
.admin-close {
  border: none;
  background: transparent;
  font-size: 1.35rem;
  line-height: 1;
  cursor: pointer;
  color: var(--text-muted);
  padding: 0 0.25rem;
}
.admin-close:hover {
  color: var(--note-list-title);
}
.admin-lead {
  margin: 0 0 0.75rem;
}
.err {
  color: var(--danger);
  margin: 0 0 0.5rem;
}
.admin-table-wrap {
  overflow-x: auto;
  max-height: min(60vh, 480px);
  overflow-y: auto;
}
.admin-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.78rem;
}
.admin-table th,
.admin-table td {
  text-align: left;
  padding: 0.35rem 0.5rem;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
.admin-table th {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--note-list-meta);
  font-weight: 600;
}
.admin-email {
  word-break: break-all;
  max-width: 240px;
}
.admin-date {
  white-space: nowrap;
  font-size: 0.72rem;
}
.admin-chk {
  text-align: center;
}
.admin-chk input {
  width: 1.1rem;
  height: 1.1rem;
  cursor: pointer;
}
</style>
