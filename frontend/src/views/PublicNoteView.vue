<script setup lang="ts">
import { isAxiosError } from 'axios'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
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

onBeforeUnmount(async () => {
  if (saveTimer) clearTimeout(saveTimer)
  if (autoSaveOk.value && canEdit.value) await save()
})

const bannerText = computed(() => {
  if (canEdit.value) return 'Открытая ссылка: любой с ссылкой может редактировать заметку.'
  return 'Открытая ссылка: только просмотр.'
})
</script>

<template>
  <div class="public-wrap">
    <header class="public-head">
      <span class="brand">em-note</span>
      <span class="muted small">{{ bannerText }}</span>
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
      <p class="muted small meta-line">
        Режим ссылки: {{ role === 'editor' ? 'редактирование' : 'только чтение' }}
        <span v-if="saving"> · Сохранение…</span>
      </p>
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
  max-width: 920px;
  margin: 0 auto;
  padding: 1rem 1.25rem 3rem;
  min-height: 100vh;
  box-sizing: border-box;
  background: var(--bg);
}
.public-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.5rem 1rem;
  margin-bottom: 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--border);
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
