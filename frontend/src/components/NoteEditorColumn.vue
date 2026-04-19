<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { errMessage, foldersApi, mailApi, notesApi, sharesApi, tagsApi } from '../api/client'
import type { Folder, Note, NoteShare, Tag } from '../api/types'
import NoteEditor from './NoteEditor.vue'
import { useAuthStore } from '../stores/auth'
import { fmtMsk } from '../utils/datetime'
import { foldersSortedAlphabetical } from '../utils/folders'

const props = defineProps<{ noteId: string | null }>()
const emit = defineEmits<{ refresh: [] }>()

const router = useRouter()
const auth = useAuthStore()

const note = ref<Note | null>(null)
const title = ref('')
const contentJson = ref('{}')
const tags = ref<Tag[]>([])
const shares = ref<NoteShare[]>([])
/** Запрос заметки с API; при переключении не скрываем редактор целиком */
const fetching = ref(false)
let loadGen = 0
const saving = ref(false)
const error = ref('')
const autoSaveOk = ref(false)

const tagQuery = ref('')
const tagFocus = ref(false)

const folders = ref<Folder[]>([])
const folderSelect = ref('')

const showMailModal = ref(false)
const modalEmail = ref('')
const modalMsg = ref('')
const mailSending = ref(false)
const mailError = ref('')

const isOwner = computed(() => !!(note.value && auth.user && note.value.owner_id === auth.user.id))
const isTrashed = computed(() => !!note.value?.deleted_at)
const editorEditable = computed(() => !!note.value && !isTrashed.value)
const foldersSorted = computed(() => foldersSortedAlphabetical(folders.value))

const attachedTagObjects = computed(() => {
  if (!note.value) return []
  const want = new Set(note.value.tag_ids)
  return tags.value
    .filter((t) => want.has(t.id))
    .sort((a, b) => a.name.localeCompare(b.name, 'ru', { sensitivity: 'base' }))
})

let saveTimer: ReturnType<typeof setTimeout> | null = null

function emitRefresh() {
  emit('refresh')
}

async function loadFoldersOnly() {
  if (!note.value) return
  try {
    folders.value = await foldersApi.list(note.value.id)
  } catch {
    /* */
  }
}

async function closePanel() {
  await flushSave()
  await router.push({ name: 'notes' })
}

async function applyFolderChange() {
  if (!note.value) return
  const want: string | null = folderSelect.value ? folderSelect.value : null
  const cur = note.value.folder_id ?? null
  if (want === cur) return
  saving.value = true
  error.value = ''
  try {
    note.value = await notesApi.update(note.value.id, { folder_id: want })
    await loadFoldersOnly()
    emitRefresh()
  } catch (e) {
    error.value = errMessage(e)
    folderSelect.value = note.value.folder_id ?? ''
  } finally {
    saving.value = false
  }
}

const filteredForAttach = computed(() => {
  if (!note.value) return []
  const q = tagQuery.value.trim().toLowerCase()
  if (!q) return []
  const attached = new Set(note.value.tag_ids)
  return tags.value.filter((t) => {
    if (attached.has(t.id)) return false
    const n = t.name.toLowerCase()
    const s = t.slug.toLowerCase()
    if (n.includes(q) || s.includes(q)) return true
    return n.split(/\s+/).some((w) => w.startsWith(q))
  }).slice(0, 20)
})

/** Создать новую метку с таким именем и прикрепить (только владелец; теги в API привязаны к owner_id заметки). */
const canOfferCreateTag = computed(() => {
  if (!isOwner.value || !note.value) return false
  const q = tagQuery.value.trim()
  if (!q || q.length > 120) return false
  const ql = q.toLowerCase()
  if (tags.value.some((t) => t.name.toLowerCase() === ql)) return false
  return true
})

const tagSuggestionsOpen = computed(
  () =>
    tagFocus.value &&
    !!tagQuery.value.trim() &&
    (filteredForAttach.value.length > 0 || canOfferCreateTag.value)
)

function openMailModal() {
  void flushSave()
  modalEmail.value = ''
  modalMsg.value = ''
  mailError.value = ''
  showMailModal.value = true
}

function closeMailModal() {
  showMailModal.value = false
}

async function sendMailFromModal() {
  if (!note.value || !modalEmail.value.trim()) {
    mailError.value = 'Укажите email'
    return
  }
  mailSending.value = true
  mailError.value = ''
  const list = modalEmail.value.split(/[,;\s]+/).map((s) => s.trim()).filter(Boolean)
  try {
    await mailApi.sendNote({
      note_id: note.value.id,
      to_emails: list,
      extra_message: modalMsg.value.trim() || undefined,
    })
    closeMailModal()
    alert('Письмо отправлено')
  } catch (e) {
    mailError.value = errMessage(e)
  } finally {
    mailSending.value = false
  }
}

async function load() {
  if (!props.noteId) return
  const gen = ++loadGen
  autoSaveOk.value = false
  fetching.value = true
  error.value = ''
  const requestedId = props.noteId
  try {
    const [n, allTags] = await Promise.all([notesApi.get(requestedId), tagsApi.list()])
    if (gen !== loadGen || requestedId !== props.noteId) return
    note.value = n
    title.value = n.title
    contentJson.value = n.content_json || '{}'
    tags.value = allTags
    tagQuery.value = ''
    const amOwner = !!(auth.user && n.owner_id === auth.user.id)
    shares.value = amOwner ? await sharesApi.list(n.id) : []
    if (gen !== loadGen || requestedId !== props.noteId) return
    await loadFoldersOnly()
    folderSelect.value = n.folder_id ?? ''
  } catch (e) {
    if (gen !== loadGen || requestedId !== props.noteId) return
    error.value = errMessage(e)
    note.value = null
  } finally {
    if (gen === loadGen) {
      fetching.value = false
      await nextTick()
      autoSaveOk.value = true
    }
  }
}

async function save() {
  if (!note.value) return
  saving.value = true
  error.value = ''
  try {
    const updated = await notesApi.update(note.value.id, {
      title: title.value,
      content_json: contentJson.value,
    })
    note.value = updated
    emitRefresh()
  } catch (e) {
    error.value = errMessage(e)
  } finally {
    saving.value = false
  }
}

async function flushSave() {
  if (!autoSaveOk.value || !note.value || isTrashed.value) return
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  await save()
}

function scheduleSave() {
  if (!autoSaveOk.value || isTrashed.value) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => void save(), 700)
}

watch([title, contentJson], () => scheduleSave())

function onTagBlur() {
  setTimeout(() => {
    tagFocus.value = false
  }, 180)
}

async function pickTag(t: Tag) {
  if (!note.value) return
  try {
    note.value = await notesApi.attachTag(note.value.id, t.id)
    tagQuery.value = ''
    tagFocus.value = false
    emitRefresh()
  } catch (e) {
    error.value = errMessage(e)
  }
}

async function removeChip(tagId: string) {
  if (!note.value || !editorEditable.value) return
  try {
    note.value = await notesApi.detachTag(note.value.id, tagId)
    emitRefresh()
  } catch (e) {
    error.value = errMessage(e)
  }
}

async function createAndAttachTag() {
  if (!note.value || !canOfferCreateTag.value) return
  const name = tagQuery.value.trim()
  if (!name) return
  try {
    const created = await tagsApi.create({ name, parent_id: null })
    tags.value = [...tags.value, created].sort((a, b) =>
      a.name.localeCompare(b.name, 'ru', { sensitivity: 'base' })
    )
    note.value = await notesApi.attachTag(note.value.id, created.id)
    tagQuery.value = ''
    tagFocus.value = false
    emitRefresh()
  } catch (e) {
    error.value = errMessage(e)
  }
}

function pickFirstSuggestion() {
  const first = filteredForAttach.value[0]
  if (first) void pickTag(first)
  else if (canOfferCreateTag.value) void createAndAttachTag()
}

async function removeNote() {
  if (!note.value || !confirm('Переместить заметку в корзину?')) return
  try {
    await notesApi.remove(note.value.id)
    emitRefresh()
    await router.push({ name: 'notes' })
  } catch (e) {
    error.value = errMessage(e)
  }
}

async function restoreFromTrash() {
  if (!note.value) return
  try {
    note.value = await notesApi.restore(note.value.id)
    title.value = note.value.title
    contentJson.value = note.value.content_json || '{}'
    await loadFoldersOnly()
    folderSelect.value = note.value.folder_id ?? ''
    emitRefresh()
  } catch (e) {
    error.value = errMessage(e)
  }
}

async function purgeForever() {
  if (!note.value || !confirm('Удалить заметку навсегда? Это действие необратимо.')) return
  try {
    await notesApi.purge(note.value.id)
    emitRefresh()
    await router.push({ name: 'notes' })
  } catch (e) {
    error.value = errMessage(e)
  }
}

const shareEmail = ref('')
const shareRole = ref('viewer')

async function addShare() {
  if (!note.value || !shareEmail.value.trim()) return
  try {
    await sharesApi.create(note.value.id, {
      invite_email: shareEmail.value.trim(),
      role: shareRole.value,
    })
    shareEmail.value = ''
    shares.value = await sharesApi.list(note.value.id)
  } catch (e) {
    error.value = errMessage(e)
  }
}

async function removeShare(s: NoteShare) {
  if (!note.value) return
  try {
    await sharesApi.remove(note.value.id, s.id)
    shares.value = await sharesApi.list(note.value.id)
  } catch (e) {
    error.value = errMessage(e)
  }
}

onBeforeRouteLeave(async () => {
  await flushSave()
})

function onVisibilityChange() {
  if (document.visibilityState === 'hidden') void flushSave()
}

onMounted(() => {
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onBeforeUnmount(async () => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  await flushSave()
})

watch(
  () => props.noteId,
  async (newId, oldId) => {
    if (oldId && note.value?.id === oldId) {
      await flushSave()
    }
    if (!newId) {
      loadGen++
      note.value = null
      title.value = ''
      contentJson.value = '{}'
      fetching.value = false
      error.value = ''
      autoSaveOk.value = false
      return
    }
    if (newId !== oldId) {
      await load()
    }
  },
  { immediate: true }
)
</script>

<template>
  <div class="editor-column">
    <template v-if="!noteId">
      <div class="editor-placeholder">
        <p class="ph-title">Заметка не выбрана</p>
        <p class="ph-hint muted">Выберите заметку в средней колонке или создайте новую.</p>
      </div>
    </template>
    <template v-else>
      <header class="bar">
        <a href="#" class="back" @click.prevent="closePanel">← Закрыть</a>
        <div class="bar-actions">
          <span v-if="fetching && note" class="save-indicator muted">Загрузка заметки…</span>
          <span v-if="saving && !isTrashed" class="save-indicator muted">Сохранение…</span>
          <template v-if="isTrashed && isOwner">
            <button type="button" class="btn primary" @click="restoreFromTrash">Восстановить</button>
            <button type="button" class="danger" @click="purgeForever">Удалить навсегда</button>
          </template>
          <button v-if="!isTrashed" type="button" class="btn btn-mail" @click="openMailModal">
            Отправить по почте
          </button>
          <button v-if="isOwner && !isTrashed" type="button" class="danger" @click="removeNote">
            В корзину
          </button>
        </div>
      </header>
      <div v-if="isTrashed" class="trash-banner">
        Заметка в корзине — редактирование отключено. Восстановите или удалите навсегда.
      </div>
      <p v-if="error" class="err">{{ error }}</p>
      <template v-if="fetching && !note">
        <p class="muted load-hint-editor">Загрузка…</p>
      </template>
      <template v-else-if="note">
        <div class="editor-main" :class="{ 'editor-fetching': fetching }">
        <input
          v-model="title"
          class="title-input"
          type="text"
          placeholder="Заголовок"
          :readonly="isTrashed"
        />
        <div v-if="!isTrashed" class="title-extras tags-block">
          <div v-if="editorEditable" class="tags-inline-row">
            <span v-for="t in attachedTagObjects" :key="t.id" class="tag-chip tag-chip-inline">
              {{ t.name }}
              <button type="button" class="chip-x chip-x-inline" aria-label="Убрать метку" @click="removeChip(t.id)">
                ×
              </button>
            </span>
            <div class="tag-field">
              <input
                v-model="tagQuery"
                type="text"
                class="tag-input-compact"
                :placeholder="isOwner ? '+ метка…' : '+ добавить…'"
                autocomplete="off"
                @focus="tagFocus = true"
                @blur="onTagBlur"
                @keydown.enter.prevent="pickFirstSuggestion"
              />
              <ul v-if="tagSuggestionsOpen" class="suggestions suggestions-pop">
                <li
                  v-for="t in filteredForAttach"
                  :key="t.id"
                  class="suggestion suggestion-compact"
                  @mousedown.prevent="pickTag(t)"
                >
                  {{ t.name }}
                </li>
                <li
                  v-if="canOfferCreateTag"
                  class="suggestion suggestion-create suggestion-compact"
                  @mousedown.prevent="createAndAttachTag()"
                >
                  <span class="create-icon" aria-hidden="true">+</span>
                  Создать «{{ tagQuery.trim() }}»
                </li>
              </ul>
            </div>
          </div>
          <div v-else-if="attachedTagObjects.length" class="tags-inline-row tags-inline-readonly">
            <span v-for="t in attachedTagObjects" :key="t.id" class="tag-chip tag-chip-inline tag-chip-readonly">{{
              t.name
            }}</span>
          </div>
          <p
            v-if="editorEditable && tagFocus && tagQuery.trim() && !tagSuggestionsOpen"
            class="muted small tag-quick-hint"
          >
            <template v-if="isOwner">
              Нет совпадений: уточните запрос, или создайте новую метку (Enter), если имя свободно.
            </template>
            <template v-else>Нет подходящих меток — уточните поиск.</template>
          </p>
        </div>
        <p class="note-dates muted small">
          Создано: {{ fmtMsk(note.created_at) }} · Изменено: {{ fmtMsk(note.updated_at)
          }}<template v-if="note.deleted_at">
            · Удалено: {{ fmtMsk(note.deleted_at) }}</template
          >
        </p>
        <div v-if="!isTrashed" class="folder-bar">
          <label class="folder-lab" for="folder-sel-col">Папка</label>
          <select
            id="folder-sel-col"
            v-model="folderSelect"
            class="folder-select"
            @change="applyFolderChange"
          >
            <option value="">Не в папке (корень)</option>
            <option v-for="f in foldersSorted" :key="f.id" :value="f.id">{{ f.name }}</option>
          </select>
        </div>
        <NoteEditor v-model:contentJson="contentJson" :editable="editorEditable" />

        <section class="panel" v-if="isOwner && !isTrashed">
          <h2>Доступ</h2>
          <div class="row">
            <input v-model="shareEmail" type="email" placeholder="email пользователя" />
            <select v-model="shareRole">
              <option value="viewer">Читатель</option>
              <option value="editor">Редактор</option>
            </select>
            <button type="button" class="btn" @click="addShare">Добавить</button>
          </div>
          <ul class="shares">
            <li v-for="s in shares" :key="s.id">
              <span>{{ s.shared_with_user_id || s.invite_email }}</span>
              <span class="muted">{{ s.role }}</span>
              <button type="button" class="linkish" @click="removeShare(s)">убрать</button>
            </li>
          </ul>
        </section>
        </div>
      </template>

      <div v-if="showMailModal" class="modal-backdrop" @click.self="closeMailModal">
        <div class="modal" role="dialog" aria-labelledby="mail-title">
          <h2 id="mail-title">Отправить заметку на почту</h2>
          <p class="muted small">
            Укажите email получателя (несколько — через запятую). Для отправки должен быть настроен
            SMTP в <code>PUT /api/users/me/smtp</code> (например через Swagger).
          </p>
          <label class="modal-label">Email</label>
          <input v-model="modalEmail" type="text" class="modal-input" placeholder="name@example.com" />
          <label class="modal-label">Сообщение (необязательно)</label>
          <textarea v-model="modalMsg" class="modal-textarea" rows="3" placeholder="Текст к письму" />
          <p v-if="mailError" class="err">{{ mailError }}</p>
          <div class="modal-actions">
            <button type="button" class="btn" @click="closeMailModal">Отмена</button>
            <button type="button" class="btn primary" :disabled="mailSending" @click="sendMailFromModal">
              {{ mailSending ? 'Отправка…' : 'Отправить' }}
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.editor-column {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 0.75rem 1rem 2rem;
  background: var(--bg);
  overflow-y: auto;
  max-height: calc(100vh - 52px);
}
.editor-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 2rem 1rem;
  min-height: 240px;
}
.ph-title {
  margin: 0 0 0.35rem;
  font-size: 0.9rem;
  font-weight: 600;
  color: #374151;
}
.ph-hint {
  margin: 0;
  font-size: 0.78rem;
  max-width: 260px;
}
.load-hint-editor {
  margin: 1rem 0;
  font-size: 0.88rem;
}
.editor-main {
  min-width: 0;
}
.editor-fetching {
  opacity: 0.55;
  pointer-events: none;
  user-select: none;
  transition: opacity 0.12s ease;
}
.trash-banner {
  background: rgba(185, 28, 28, 0.08);
  border: 1px solid rgba(185, 28, 28, 0.25);
  color: var(--danger);
  padding: 0.55rem 0.75rem;
  border-radius: 8px;
  margin-bottom: 0.75rem;
  font-size: 0.82rem;
}
.note-dates {
  margin: 0 0 0.65rem;
}
.bar .btn.primary {
  background: var(--accent);
  color: #fff;
  border: none;
  padding: 0.32rem 0.55rem;
  border-radius: 6px;
  cursor: pointer;
  font: inherit;
  font-size: 0.78rem;
}
.folder-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.45rem 0.65rem;
  margin-bottom: 0.85rem;
}
.folder-lab {
  font-size: 0.8rem;
  font-weight: 500;
}
.folder-select {
  padding: 0.3rem 0.45rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  font: inherit;
  font-size: 0.78rem;
  background: var(--panel);
  color: inherit;
  min-width: 160px;
}
.bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.bar-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  align-items: center;
}
.save-indicator {
  font-size: 0.78rem;
}
.back {
  color: var(--accent);
  text-decoration: none;
  font-weight: 500;
  font-size: 0.8rem;
}
.danger {
  background: transparent;
  border: 1px solid var(--danger);
  color: var(--danger);
  padding: 0.32rem 0.55rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.78rem;
}
.btn-mail {
  border: 1px solid var(--border);
  padding: 0.32rem 0.55rem;
  border-radius: 8px;
  background: var(--panel);
  cursor: pointer;
  font: inherit;
  font-size: 0.78rem;
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
.title-extras.tags-block {
  margin-bottom: 0.55rem;
}
.tags-inline-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.28rem;
  min-height: 1.55rem;
}
.tags-inline-readonly {
  opacity: 0.95;
}
.tag-field {
  position: relative;
  flex: 1 1 7rem;
  min-width: 6.5rem;
  max-width: 14rem;
}
.tag-chip-inline {
  padding: 0.12rem 0.38rem;
  font-size: 0.72rem;
  line-height: 1.35;
  border-radius: 999px;
}
.chip-x-inline {
  font-size: 0.92rem;
  line-height: 1;
}
.tag-input-compact {
  width: 100%;
  box-sizing: border-box;
  padding: 0.14rem 0.5rem;
  min-height: 1.55rem;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.45);
  font: inherit;
  font-size: 0.72rem;
  background: #fff;
  color: inherit;
  line-height: 1.3;
}
.tag-input-compact::placeholder {
  color: #94a3b8;
  font-size: 0.72rem;
}
.tag-input-compact:hover {
  border-color: rgba(100, 116, 139, 0.5);
}
.tag-input-compact:focus {
  outline: none;
  border-color: rgba(37, 99, 235, 0.45);
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.1);
}
.suggestions-pop {
  left: 0;
  right: auto;
  min-width: 11rem;
  max-width: min(17rem, 92vw);
  margin-top: 4px;
  z-index: 30;
}
.suggestion-compact {
  padding: 0.32rem 0.48rem;
  font-size: 0.74rem;
}
.tag-chip-readonly {
  cursor: default;
  opacity: 0.92;
}
.tag-quick-hint {
  margin: 0.35rem 0 0;
}
.panel {
  margin-top: 1.15rem;
  padding: 0.75rem 0.85rem;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--panel);
  box-shadow:
    0 1px 2px rgba(15, 23, 42, 0.04),
    0 4px 12px rgba(15, 23, 42, 0.03);
}
.tags-panel {
  background: linear-gradient(180deg, #ffffff 0%, #fbfcfe 100%);
}
.panel-head {
  margin-bottom: 0.65rem;
}
.panel-head h2 {
  margin: 0 0 0.28rem;
  font-size: 0.6875rem;
  font-weight: 650;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #64748b;
}
.panel > h2 {
  margin: 0 0 0.45rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: #334155;
}
.panel-desc {
  margin: 0;
  font-size: 0.72rem;
  line-height: 1.45;
  color: var(--text-muted);
}
.panel-desc strong {
  font-weight: 600;
  color: #334155;
}
.muted {
  color: var(--text-muted);
  font-size: 0.85rem;
}
.small {
  font-size: 0.75rem;
}
.attached-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 0.6rem;
  min-height: 1.5rem;
  align-items: center;
}
.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.22rem;
  padding: 0.15rem 0.42rem;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 0.78rem;
}
.chip-x {
  border: none;
  background: none;
  cursor: pointer;
  padding: 0 0.12rem;
  font-size: 1rem;
  line-height: 1;
  color: var(--text-muted);
}
.chip-x:hover {
  color: var(--danger);
}
.tag-add {
  position: relative;
  max-width: 320px;
}
.tag-input {
  width: 100%;
  max-width: 320px;
  padding: 0.42rem 0.55rem;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.45);
  font: inherit;
  font-size: 0.8rem;
  background: #fff;
  color: inherit;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}
.tag-input::placeholder {
  color: #94a3b8;
}
.tag-input:hover {
  border-color: rgba(100, 116, 139, 0.5);
}
.tag-input:focus {
  outline: none;
  border-color: rgba(37, 99, 235, 0.45);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}
.suggestions {
  position: absolute;
  left: 0;
  right: 0;
  top: 100%;
  margin: 6px 0 0;
  padding: 0.35rem;
  list-style: none;
  background: #fff;
  border: 1px solid rgba(148, 163, 184, 0.35);
  border-radius: 12px;
  box-shadow:
    0 4px 6px rgba(15, 23, 42, 0.04),
    0 12px 28px rgba(15, 23, 42, 0.1);
  z-index: 10;
  max-height: 220px;
  overflow-y: auto;
}
.suggestion {
  padding: 0.45rem 0.6rem;
  cursor: pointer;
  font-size: 0.8rem;
  border-radius: 8px;
  color: #334155;
}
.suggestion:hover {
  background: #f1f5f9;
}
.suggestion-create {
  margin-top: 0.15rem;
  padding-top: 0.5rem;
  border-top: 1px solid rgba(226, 232, 240, 0.9);
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-weight: 500;
  color: var(--accent);
}
.suggestion-create:hover {
  background: rgba(37, 99, 235, 0.06);
}
.create-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.15rem;
  height: 1.15rem;
  border-radius: 6px;
  background: rgba(37, 99, 235, 0.12);
  font-size: 0.95rem;
  line-height: 1;
  font-weight: 600;
}
.none {
  font-size: 0.78rem;
}
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  margin-bottom: 0.45rem;
}
.row input,
.row select {
  padding: 0.38rem 0.48rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: inherit;
  font-size: 0.78rem;
}
.btn {
  padding: 0.38rem 0.6rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--panel);
  cursor: pointer;
  color: inherit;
  font-size: 0.78rem;
}
.btn.primary {
  background: var(--accent);
  color: #fff;
  border-color: transparent;
}
.btn.primary:hover:not(:disabled) {
  background: var(--accent-hover);
}
.shares {
  list-style: none;
  margin: 0.4rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}
.shares li {
  display: flex;
  gap: 0.55rem;
  align-items: center;
  font-size: 0.78rem;
}
.linkish {
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
  padding: 0;
  font: inherit;
}
.err {
  color: var(--danger);
  font-size: 0.8rem;
}
code {
  font-size: 0.82em;
  background: var(--bg);
  padding: 0.1em 0.32em;
  border-radius: 4px;
}
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 1rem;
}
.modal {
  background: var(--panel);
  border-radius: 12px;
  border: 1px solid var(--border);
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.12);
  max-width: 420px;
  width: 100%;
  padding: 1.1rem;
}
.modal h2 {
  margin: 0 0 0.45rem;
  font-size: 1rem;
}
.modal-label {
  display: block;
  font-size: 0.78rem;
  font-weight: 500;
  margin-top: 0.55rem;
  margin-bottom: 0.22rem;
}
.modal-input,
.modal-textarea {
  width: 100%;
  padding: 0.45rem 0.55rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  font: inherit;
  font-size: 0.82rem;
  background: var(--bg);
  color: inherit;
}
.modal-textarea {
  resize: vertical;
  min-height: 72px;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.45rem;
  margin-top: 0.85rem;
}
</style>
