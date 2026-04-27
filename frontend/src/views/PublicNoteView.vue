<script setup lang="ts">
import { isAxiosError } from 'axios'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { errMessage, publicNoteApi } from '../api/client'
import type { Note } from '../api/types'
import NoteEditor from '../components/NoteEditor.vue'
import { DEFAULT_NOTE_TITLE } from '../utils/noteDefaults'
import { normalizeContentJson } from '../utils/noteSnapshot'

const route = useRoute()
const token = computed(() => String(route.params.token || '').trim())

const loading = ref(true)
const error = ref('')
const note = ref<Note | null>(null)
const canEdit = ref(false)
const role = ref('viewer')
const title = ref('')
const contentJson = ref('{}')
const saving = ref(false)

let saveTimer: ReturnType<typeof setTimeout> | null = null
let titleSkipSaveOnce = false
const autoSaveOk = ref(false)

const lastSavedTitle = ref('')
const lastSavedContentJson = ref('')

function syncLastSavedFromEditor() {
  lastSavedTitle.value = title.value
  lastSavedContentJson.value = normalizeContentJson(contentJson.value)
}

function editorTextUnchanged(): boolean {
  return (
    title.value === lastSavedTitle.value &&
    normalizeContentJson(contentJson.value) === lastSavedContentJson.value
  )
}

async function load() {
  const t = token.value
  if (!t) {
    error.value = 'Некорректная ссылка'
    loading.value = false
    return
  }
  loading.value = true
  error.value = ''
  autoSaveOk.value = false
  try {
    const data = await publicNoteApi.get(t)
    note.value = data.note
    canEdit.value = data.can_edit
    role.value = data.role
    title.value = data.note.title
    contentJson.value = data.note.content_json || '{}'
    await nextTick()
    syncLastSavedFromEditor()
    autoSaveOk.value = true
  } catch (e) {
    if (isAxiosError(e) && e.response?.status === 404) {
      error.value = 'Ссылка недействительна или доступ отозван.'
    } else {
      error.value = errMessage(e)
    }
    note.value = null
  } finally {
    loading.value = false
  }
}

async function save() {
  const t = token.value
  if (!t || !note.value || !canEdit.value) return
  if (editorTextUnchanged()) return
  saving.value = true
  error.value = ''
  try {
    const updated = await publicNoteApi.update(t, {
      title: title.value,
      content_json: contentJson.value,
    })
    note.value = updated
    syncLastSavedFromEditor()
  } catch (e) {
    error.value = errMessage(e)
  } finally {
    saving.value = false
  }
}

function scheduleSave() {
  if (!autoSaveOk.value || !canEdit.value) return
  if (editorTextUnchanged()) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => void save(), 700)
}

function onTitleFocus() {
  if (!canEdit.value) return
  if (title.value.trim() === DEFAULT_NOTE_TITLE) {
    titleSkipSaveOnce = true
    title.value = ''
  }
}

function onTitleBlur() {
  if (!canEdit.value) return
  const t = title.value.trim()
  title.value = t || DEFAULT_NOTE_TITLE
}

watch([title, contentJson], () => {
  if (titleSkipSaveOnce) {
    titleSkipSaveOnce = false
    return
  }
  scheduleSave()
})

watch(
  () => route.params.token,
  () => void load(),
  { immediate: true }
)

const bannerText = computed(() => {
  if (canEdit.value) return 'Открытая ссылка: любой с ссылкой может редактировать заметку.'
  return 'Открытая ссылка: только просмотр.'
})

/** Узкая шапка и шире колонка текста; Esc — выход. */
const publicFocusMode = ref(false)

function togglePublicFocusMode() {
  publicFocusMode.value = !publicFocusMode.value
}

function onPublicFocusKeydown(e: KeyboardEvent) {
  if (e.key !== 'Escape') return
  if (!publicFocusMode.value) return
  e.preventDefault()
  publicFocusMode.value = false
}

watch(publicFocusMode, (v) => {
  if (typeof document === 'undefined') return
  document.body.style.overflow = v ? 'hidden' : ''
})

onMounted(() => {
  window.addEventListener('keydown', onPublicFocusKeydown)
})

onBeforeUnmount(async () => {
  if (saveTimer) clearTimeout(saveTimer)
  if (autoSaveOk.value && canEdit.value) await save()
  window.removeEventListener('keydown', onPublicFocusKeydown)
  if (typeof document !== 'undefined') document.body.style.overflow = ''
})
</script>

<template>
  <div class="public-wrap" :class="{ 'public-wrap--focus': publicFocusMode }">
    <header class="public-head" :class="{ 'public-head--minimal': publicFocusMode }">
      <template v-if="!publicFocusMode">
        <span class="brand">em-note</span>
        <span class="muted small public-head-banner">{{ bannerText }}</span>
      </template>
      <button
        v-if="note && !loading && !error"
        type="button"
        class="public-fs-btn"
        :aria-pressed="publicFocusMode"
        :aria-label="publicFocusMode ? 'Показать шапку и подпись ссылки' : 'Только заметка на весь экран'"
        :title="publicFocusMode ? 'Выйти (Esc)' : 'Только заметка'"
        @click="togglePublicFocusMode"
      >
        {{ publicFocusMode ? 'Шапка' : 'Только заметка' }}
      </button>
    </header>
    <p v-if="loading" class="muted">Загрузка…</p>
    <p v-else-if="error" class="err">{{ error }}</p>
    <template v-else-if="note">
      <input
        v-model="title"
        class="title-input"
        type="text"
        placeholder="Заголовок"
        :readonly="!canEdit"
        @focus="onTitleFocus"
        @blur="onTitleBlur"
      />
      <p v-if="!publicFocusMode" class="muted small meta-line">
        Режим ссылки: {{ role === 'editor' ? 'редактирование' : 'только чтение' }}
        <span v-if="saving"> · Сохранение…</span>
      </p>
      <p v-else-if="saving" class="muted small meta-line">Сохранение…</p>
      <NoteEditor
        v-model:contentJson="contentJson"
        :editable="canEdit"
        :note-id="note?.id ?? null"
        :public-token="token"
      />
    </template>
  </div>
</template>

<style scoped>
.public-wrap {
  width: 100%;
  max-width: min(100% - 1.5rem, 1320px);
  margin: 0 auto;
  padding: 1rem clamp(0.75rem, 2.5vw, 1.75rem) 3rem;
  min-height: 100vh;
  box-sizing: border-box;
  background: var(--bg);
}
.public-wrap--focus {
  max-width: none;
  min-height: 100dvh;
  padding: 0.65rem clamp(0.65rem, 2vw, 1.25rem) 2.5rem;
}
.public-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1rem;
  margin-bottom: 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--border);
}
.public-head--minimal {
  margin-bottom: 0.5rem;
  padding-bottom: 0.45rem;
}
.public-head-banner {
  flex: 1 1 12rem;
  min-width: 0;
}
.public-fs-btn {
  font: inherit;
  font-size: 0.78rem;
  font-weight: 500;
  padding: 0.32rem 0.6rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--panel, #f8fafc);
  color: #475569;
  cursor: pointer;
  flex-shrink: 0;
  margin-left: auto;
}
.public-fs-btn:hover {
  border-color: rgba(37, 99, 235, 0.35);
  color: var(--accent, #2563eb);
}
.public-fs-btn[aria-pressed='true'] {
  background: rgba(37, 99, 235, 0.1);
  border-color: rgba(37, 99, 235, 0.42);
  color: var(--accent, #2563eb);
}
.brand {
  font-weight: 700;
  font-size: 0.9rem;
}
.title-input {
  width: 100%;
  font-size: 1.15rem;
  font-weight: 650;
  padding: 0.38rem 0;
  margin-bottom: 0.35rem;
  border: none;
  border-bottom: 1px solid var(--border);
  background: transparent;
  color: inherit;
}
.meta-line {
  margin: 0 0 0.75rem;
}
.err {
  color: var(--danger);
}
</style>
