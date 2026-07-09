<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { contactsApi, errMessage } from '../api/client'
import type { UserContact } from '../api/types'

withDefaults(
  defineProps<{
    /** Показать выпадающий список для выбора контакта */
    showPicker?: boolean
    /** single — подставить email; multi — добавить к списку через запятую */
    pickMode?: 'single' | 'multi'
    pickerLabel?: string
    compact?: boolean
  }>(),
  {
    showPicker: true,
    pickMode: 'single',
    pickerLabel: 'Из контактов…',
    compact: false,
  }
)

const emit = defineEmits<{ (e: 'pick', email: string): void }>()

const contacts = ref<UserContact[]>([])
const loading = ref(false)
const error = ref('')
const bookExpanded = ref(false)
const newName = ref('')
const newEmail = ref('')
const saving = ref(false)
const pickId = ref('')

function contactLabel(c: UserContact): string {
  return `${c.name} (${c.email})`
}

async function loadContacts() {
  loading.value = true
  error.value = ''
  try {
    contacts.value = await contactsApi.list()
  } catch (e) {
    contacts.value = []
    error.value = errMessage(e)
  } finally {
    loading.value = false
  }
}

async function addContact() {
  const name = newName.value.trim()
  const email = newEmail.value.trim()
  if (!name || !email) {
    error.value = 'Укажите имя и email'
    return
  }
  saving.value = true
  error.value = ''
  try {
    await contactsApi.create({ name, email })
    newName.value = ''
    newEmail.value = ''
    await loadContacts()
    bookExpanded.value = true
  } catch (e) {
    error.value = errMessage(e)
  } finally {
    saving.value = false
  }
}

async function removeContact(c: UserContact) {
  if (!confirm(`Удалить контакт «${c.name}»?`)) return
  error.value = ''
  try {
    await contactsApi.remove(c.id)
    if (pickId.value === c.id) pickId.value = ''
    await loadContacts()
  } catch (e) {
    error.value = errMessage(e)
  }
}

function onPickChange() {
  const id = pickId.value
  if (!id) return
  const c = contacts.value.find((x) => x.id === id)
  pickId.value = ''
  if (!c) return
  emit('pick', c.email)
}

function pickFromList(c: UserContact) {
  emit('pick', c.email)
}

onMounted(() => {
  void loadContacts()
})

defineExpose({ reload: loadContacts, contacts })
</script>

<template>
  <div class="contact-book" :class="{ 'contact-book--compact': compact }">
    <select
      v-if="showPicker && contacts.length"
      v-model="pickId"
      class="contact-book-pick"
      :aria-label="pickerLabel"
      @change="onPickChange"
    >
      <option value="">{{ pickerLabel }}</option>
      <option v-for="c in contacts" :key="c.id" :value="c.id">{{ contactLabel(c) }}</option>
    </select>

    <button
      type="button"
      class="contact-book-toggle"
      :aria-expanded="bookExpanded"
      @click="bookExpanded = !bookExpanded"
    >
      <span class="contact-book-chevron" :class="{ open: bookExpanded }" aria-hidden="true" />
      Мои контакты
      <span v-if="contacts.length" class="contact-book-count">{{ contacts.length }}</span>
    </button>

    <div v-show="bookExpanded" class="contact-book-body">
      <div class="contact-book-form">
        <input v-model="newName" type="text" class="contact-book-input" placeholder="Имя" />
        <input v-model="newEmail" type="email" class="contact-book-input" placeholder="Email" />
        <button type="button" class="contact-book-btn" :disabled="saving" @click="addContact">
          {{ saving ? '…' : 'Добавить' }}
        </button>
      </div>
      <p v-if="loading" class="contact-book-muted">Загрузка…</p>
      <p v-else-if="error" class="contact-book-err">{{ error }}</p>
      <ul v-if="contacts.length" class="contact-book-list">
        <li v-for="c in contacts" :key="c.id" class="contact-book-item">
          <div class="contact-book-item-main">
            <span class="contact-book-name">{{ c.name }}</span>
            <span class="contact-book-email">{{ c.email }}</span>
          </div>
          <div class="contact-book-item-actions">
            <button type="button" class="contact-book-link" @click="pickFromList(c)">
              {{ pickMode === 'multi' ? 'Добавить' : 'Выбрать' }}
            </button>
            <button type="button" class="contact-book-link contact-book-link--danger" @click="removeContact(c)">
              Удалить
            </button>
          </div>
        </li>
      </ul>
      <p v-else-if="!loading" class="contact-book-muted">Пока нет сохранённых контактов</p>
    </div>
  </div>
</template>

<style scoped>
.contact-book {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}
.contact-book--compact {
  margin-top: 0.35rem;
}
.contact-book-pick {
  width: 100%;
  padding: 0.4rem 0.45rem;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.45);
  font: inherit;
  font-size: 0.78rem;
  background: #fff;
  color: inherit;
}
.contact-book-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0;
  border: none;
  background: transparent;
  font: inherit;
  font-size: 0.78rem;
  font-weight: 600;
  color: #334155;
  cursor: pointer;
  text-align: left;
}
.contact-book-toggle:hover {
  color: #1d4ed8;
}
.contact-book-chevron {
  display: inline-block;
  width: 0;
  height: 0;
  border-top: 4px solid transparent;
  border-bottom: 4px solid transparent;
  border-left: 5px solid currentColor;
  transition: transform 0.15s ease;
}
.contact-book-chevron.open {
  transform: rotate(90deg);
}
.contact-book-count {
  font-size: 0.68rem;
  font-weight: 700;
  padding: 0.1rem 0.4rem;
  border-radius: 999px;
  background: rgba(100, 116, 139, 0.15);
  color: #475569;
}
.contact-book-body {
  padding: 0.15rem 0 0.25rem;
}
.contact-book-form {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  align-items: center;
  margin-bottom: 0.45rem;
}
.contact-book-input {
  flex: 1 1 7rem;
  min-width: 0;
  padding: 0.38rem 0.5rem;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.45);
  font: inherit;
  font-size: 0.78rem;
  background: #fff;
}
.contact-book-btn {
  padding: 0.38rem 0.65rem;
  border-radius: 10px;
  border: 1px solid rgba(37, 99, 235, 0.28);
  background: #fff;
  color: #1d4ed8;
  font: inherit;
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.contact-book-btn:disabled {
  opacity: 0.55;
  cursor: default;
}
.contact-book-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.contact-book-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.35rem 0.65rem;
  padding: 0.4rem 0.5rem;
  border-radius: 10px;
  background: rgba(248, 250, 252, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.25);
}
.contact-book-item-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}
.contact-book-name {
  font-weight: 600;
  font-size: 0.78rem;
}
.contact-book-email {
  font-size: 0.72rem;
  color: #64748b;
  word-break: break-all;
}
.contact-book-item-actions {
  display: flex;
  gap: 0.45rem;
  flex-shrink: 0;
}
.contact-book-link {
  border: none;
  background: transparent;
  padding: 0;
  font: inherit;
  font-size: 0.72rem;
  color: #1d4ed8;
  cursor: pointer;
}
.contact-book-link--danger {
  color: #b91c1c;
}
.contact-book-muted {
  margin: 0;
  font-size: 0.72rem;
  color: #64748b;
}
.contact-book-err {
  margin: 0 0 0.35rem;
  font-size: 0.72rem;
  color: #b91c1c;
}
</style>
