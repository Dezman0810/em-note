<script setup lang="ts">
import { isAxiosError } from 'axios'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { errMessage, publicChecklistApi } from '../api/client'
import type { Note } from '../api/types'
import NoteEditor from '../components/NoteEditor.vue'
import { DEFAULT_NOTE_TITLE } from '../utils/noteDefaults'
import { useTheme } from '../composables/useTheme'

/**
 * Ссылка «чек-бокс»: заметка только для чтения, можно лишь ставить и снимать галочки.
 * Сервер принимает по этой ссылке единственную операцию — отметку пункта по номеру.
 */
const { label: themeLabel, icon: themeIcon, cycleTheme } = useTheme()

const route = useRoute()
const token = computed(() => String(route.params.token || '').trim())

const loading = ref(true)
const error = ref('')
const notice = ref('')
const note = ref<Note | null>(null)
const contentJson = ref('{}')
const pending = ref(0)

let noticeTimer: ReturnType<typeof setTimeout> | null = null

function showNotice(text: string) {
  notice.value = text
  if (noticeTimer) clearTimeout(noticeTimer)
  noticeTimer = setTimeout(() => {
    notice.value = ''
  }, 4000)
}

async function load(opts: { silent?: boolean } = {}) {
  const t = token.value
  if (!t) {
    error.value = 'Некорректная ссылка'
    loading.value = false
    return
  }
  if (!opts.silent) loading.value = true
  error.value = ''
  try {
    const data = await publicChecklistApi.get(t)
    note.value = data.note
    contentJson.value = data.note.content_json || '{}'
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

async function onTaskToggle(index: number, checked: boolean, text: string): Promise<boolean> {
  const t = token.value
  if (!t) return false
  pending.value++
  try {
    const data = await publicChecklistApi.toggle(t, { index, checked, text })
    note.value = data.note
    contentJson.value = data.note.content_json || '{}'
    return true
  } catch (e) {
    if (isAxiosError(e) && e.response?.status === 409) {
      showNotice('Владелец изменил список — показываем актуальную версию.')
      await load({ silent: true })
    } else if (isAxiosError(e) && e.response?.status === 404) {
      error.value = 'Ссылка недействительна или доступ отозван.'
      note.value = null
    } else {
      showNotice(`Не удалось сохранить отметку: ${errMessage(e)}`)
    }
    return false
  } finally {
    pending.value--
  }
}

/** «Готово N из M» по всем чек-боксам заметки. */
const progress = computed(() => {
  let done = 0
  let total = 0
  const walk = (n: unknown) => {
    if (!n || typeof n !== 'object') return
    const o = n as { type?: unknown; attrs?: { checked?: unknown }; content?: unknown }
    if (o.type === 'taskItem') {
      total++
      if (o.attrs?.checked) done++
    }
    if (Array.isArray(o.content)) o.content.forEach(walk)
  }
  try {
    walk(JSON.parse(contentJson.value))
  } catch {
    /* пустой или битый документ — счётчик не показываем */
  }
  return { done, total }
})

/** Вернулись на вкладку — подтянуть отметки, сделанные другими. */
function onVisible() {
  if (document.visibilityState === 'visible' && note.value && pending.value === 0) {
    void load({ silent: true })
  }
}

watch(
  () => route.params.token,
  () => void load(),
  { immediate: true }
)

onMounted(() => {
  document.addEventListener('visibilitychange', onVisible)
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisible)
  if (noticeTimer) clearTimeout(noticeTimer)
})
</script>

<template>
  <div class="public-wrap">
    <header class="public-head">
      <span class="brand">em-note</span>
      <span class="muted small public-head-banner">
        Ссылка «чек-бокс»: можно только отмечать пункты, остальное — для чтения.
      </span>
      <button
        type="button"
        class="theme-toggle"
        :aria-label="themeLabel"
        :title="themeLabel"
        @click="cycleTheme"
      >
        <span class="theme-toggle-glyph" aria-hidden="true">{{ themeIcon }}</span>
      </button>
    </header>
    <p v-if="loading" class="muted">Загрузка…</p>
    <p v-else-if="error" class="err">{{ error }}</p>
    <template v-else-if="note">
      <h1 class="title">{{ note.title || DEFAULT_NOTE_TITLE }}</h1>
      <p class="muted small meta-line">
        <template v-if="progress.total">Готово {{ progress.done }} из {{ progress.total }}</template>
        <template v-else>В заметке нет чек-боксов.</template>
        <span v-if="pending"> · Сохранение…</span>
      </p>
      <p v-if="notice" class="notice" role="status">{{ notice }}</p>
      <NoteEditor
        :content-json="contentJson"
        :editable="false"
        :note-id="note.id"
        :checklist-token="token"
        :task-toggle="onTaskToggle"
        :owner-tools="false"
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
  display: flex;
  flex-direction: column;
  overflow-x: clip;
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
.public-head-banner {
  flex: 1 1 12rem;
  min-width: 0;
}
.brand {
  font-weight: 700;
  font-size: var(--fs-md);
}
.title {
  font-size: var(--fs-lg);
  font-weight: 650;
  margin: 0 0 0.35rem;
  padding: 0.38rem 0;
  border-bottom: 1px solid var(--border);
  overflow-wrap: anywhere;
}
.meta-line {
  margin: 0 0 0.75rem;
}
.notice {
  margin: 0 0 0.75rem;
  padding: 0.45rem 0.7rem;
  border-radius: 6px;
  background: var(--accent-subtle-hover);
  color: var(--accent-text);
  font-size: var(--fs-xs);
}
.err {
  color: var(--danger-text);
}
/* Чек-боксы здесь — единственный интерактив: подсказываем курсором. */
.public-wrap :deep(ul[data-type='taskList'] input[type='checkbox']) {
  cursor: pointer;
}
.public-wrap :deep(.editor-wrap:not(.editor-wrap--fit) .editor-content) {
  overflow-x: auto;
  overflow-y: visible;
}
</style>
