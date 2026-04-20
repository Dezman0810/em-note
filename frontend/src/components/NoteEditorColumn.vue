<script setup lang="ts">
import { isAxiosError } from 'axios'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { errMessage, foldersApi, mailApi, notesApi, sharesApi, tagsApi } from '../api/client'
import type { Folder, Note, NotePublicLink, NoteShare, Tag } from '../api/types'
import NoteEditor from './NoteEditor.vue'
import { useAuthStore } from '../stores/auth'
import { fmtCompactMsk, fmtMsk } from '../utils/datetime'
import { normalizeContentJson } from '../utils/noteSnapshot'
import { contentHasExcalidraw } from '../utils/tiptapContent'
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
const publicLink = ref<NotePublicLink | null>(null)
const publicRole = ref<'viewer' | 'editor'>('viewer')
const publicCopyOk = ref(false)
const publicAccessBusy = ref(false)
/** Раскрытые настройки общей ссылки (URL, режим, новый токен) */
const publicShareExpanded = ref(false)
/** Список приглашений по email */
const emailSharesExpanded = ref(false)
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

const SCHEMA_TAG_NAME = 'Схема'

/** Компактное напоминание: одно поле datetime-local во всплывающем окне. */
const reminderPanelOpen = ref(false)
const reminderDatetimeLocal = ref('')

const showMailModal = ref(false)
const modalEmail = ref('')
const modalMsg = ref('')
const mailSending = ref(false)
const mailError = ref('')

const isOwner = computed(() => !!(note.value && auth.user && note.value.owner_id === auth.user.id))

const publicUrl = computed(() => {
  if (!publicLink.value || typeof window === 'undefined') return ''
  const path = router.resolve({ name: 'public-note', params: { token: publicLink.value.token } }).href
  return `${window.location.origin}${path}`
})
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

/** Последнее сохранённое на сервере состояние текста — без изменений не шлём PATCH и не двигаем updated_at. */
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

function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

function syncReminderFieldsFromIso(iso: string | null | undefined) {
  if (!iso) {
    reminderDatetimeLocal.value = ''
    return
  }
  const s = iso.trim()
  const hasTz = /([zZ]$)|([+-]\d{2}:\d{2}$)|([+-]\d{2}\d{2}$)/.test(s)
  const normalized = hasTz ? s : `${s}Z`
  const d = new Date(normalized)
  if (Number.isNaN(d.getTime())) {
    reminderDatetimeLocal.value = ''
    return
  }
  reminderDatetimeLocal.value = `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}

const hasReminderSet = computed(() => !!note.value?.reminder_at)

async function updateReminderAt(iso: string | null) {
  if (!note.value || !editorEditable.value) return
  saving.value = true
  error.value = ''
  try {
    note.value = await notesApi.update(note.value.id, { reminder_at: iso })
    syncReminderFieldsFromIso(note.value.reminder_at)
    emitRefresh()
  } catch (e) {
    error.value = errMessage(e)
  } finally {
    saving.value = false
  }
}

async function saveReminderFromForm() {
  if (!note.value || !editorEditable.value) return
  const raw = reminderDatetimeLocal.value.trim()
  if (!raw) {
    await updateReminderAt(null)
    reminderPanelOpen.value = false
    return
  }
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) {
    error.value = 'Некорректные дата и время'
    return
  }
  error.value = ''
  await updateReminderAt(d.toISOString())
  reminderPanelOpen.value = false
}

function clearReminder() {
  reminderDatetimeLocal.value = ''
  void updateReminderAt(null)
  reminderPanelOpen.value = false
}

async function syncSchemaTag() {
  if (!note.value || !isOwner.value || !editorEditable.value) return
  const has = contentHasExcalidraw(contentJson.value)
  let schemaTag = tags.value.find((t) => t.name === SCHEMA_TAG_NAME)
  if (has && !schemaTag) {
    try {
      schemaTag = await tagsApi.create({ name: SCHEMA_TAG_NAME })
      tags.value = await tagsApi.list()
    } catch {
      return
    }
  }
  if (!schemaTag) return
  const attached = note.value.tag_ids.includes(schemaTag.id)
  try {
    if (has && !attached) {
      note.value = await notesApi.attachTag(note.value.id, schemaTag.id)
      emitRefresh()
    } else if (!has && attached) {
      note.value = await notesApi.detachTag(note.value.id, schemaTag.id)
      emitRefresh()
    }
  } catch {
    /* не блокируем сохранение текста */
  }
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
    publicLink.value = null
    if (amOwner) {
      try {
        const pl = await notesApi.getPublicLink(n.id)
        publicLink.value = pl
        publicRole.value = pl.role === 'editor' ? 'editor' : 'viewer'
      } catch (e) {
        if (!isAxiosError(e) || e.response?.status !== 404) {
          /* ignore optional feature */
        }
      }
    }
    if (gen !== loadGen || requestedId !== props.noteId) return
    publicShareExpanded.value = false
    emailSharesExpanded.value = false
    await loadFoldersOnly()
    folderSelect.value = n.folder_id ?? ''
    syncReminderFieldsFromIso(n.reminder_at)
    reminderPanelOpen.value = false
    await syncSchemaTag()
  } catch (e) {
    if (gen !== loadGen || requestedId !== props.noteId) return
    error.value = errMessage(e)
    note.value = null
  } finally {
    if (gen === loadGen) {
      fetching.value = false
      await nextTick()
      syncLastSavedFromEditor()
      autoSaveOk.value = true
    }
  }
}

function parseUpdatedAt(iso: string | undefined): number {
  if (!iso) return 0
  const t = Date.parse(iso)
  return Number.isNaN(t) ? 0 : t
}

/** Подтянуть заметку с сервера, если её обновили в другом месте (например по публичной ссылке). */
async function refetchNoteIfRemoteNewer() {
  if (!props.noteId || !note.value || fetching.value) return
  const gen = loadGen
  try {
    const remote = await notesApi.get(props.noteId)
    if (gen !== loadGen || props.noteId !== note.value.id) return
    if (parseUpdatedAt(remote.updated_at) <= parseUpdatedAt(note.value.updated_at)) return
    note.value = remote
    title.value = remote.title
    contentJson.value = remote.content_json || '{}'
    await loadFoldersOnly()
    folderSelect.value = remote.folder_id ?? ''
    syncReminderFieldsFromIso(remote.reminder_at)
    syncLastSavedFromEditor()
    emitRefresh()
    void syncSchemaTag()
  } catch {
    /* сеть / 401 — не мешаем редактированию */
  }
}

async function save() {
  if (!note.value) return
  if (editorTextUnchanged()) return
  saving.value = true
  error.value = ''
  try {
    const updated = await notesApi.update(note.value.id, {
      title: title.value,
      content_json: contentJson.value,
    })
    note.value = updated
    syncLastSavedFromEditor()
    emitRefresh()
    await syncSchemaTag()
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
  try {
    const remote = await notesApi.get(note.value.id)
    if (parseUpdatedAt(remote.updated_at) > parseUpdatedAt(note.value.updated_at)) {
      note.value = remote
      title.value = remote.title
      contentJson.value = remote.content_json || '{}'
      await loadFoldersOnly()
      folderSelect.value = remote.folder_id ?? ''
      syncReminderFieldsFromIso(remote.reminder_at)
      syncLastSavedFromEditor()
      emitRefresh()
      void syncSchemaTag()
      return
    }
  } catch {
    /* если GET не удался — сохраняем локальные правки как раньше */
  }
  await save()
}

function scheduleSave() {
  if (!autoSaveOk.value || isTrashed.value) return
  if (editorTextUnchanged()) return
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

async function onPublicAccessToggle(e: Event) {
  const el = e.target as HTMLInputElement
  const wantOn = el.checked
  if (!note.value) return
  publicAccessBusy.value = true
  error.value = ''
  try {
    if (wantOn) {
      publicLink.value = await notesApi.upsertPublicLink(note.value.id, { role: publicRole.value })
      publicShareExpanded.value = true
    } else {
      await notesApi.deletePublicLink(note.value.id)
      publicLink.value = null
      publicShareExpanded.value = false
    }
    publicCopyOk.value = false
  } catch (err) {
    error.value = errMessage(err)
    el.checked = !wantOn
  } finally {
    publicAccessBusy.value = false
  }
}

async function setPublicRole(role: 'viewer' | 'editor') {
  if (publicRole.value === role || !note.value || !publicLink.value) return
  publicRole.value = role
  publicAccessBusy.value = true
  error.value = ''
  try {
    publicLink.value = await notesApi.upsertPublicLink(note.value.id, { role })
    publicCopyOk.value = false
  } catch (e) {
    error.value = errMessage(e)
  } finally {
    publicAccessBusy.value = false
  }
}

async function regenPublicLink() {
  if (!note.value || !publicLink.value) return
  if (!confirm('Старая ссылка перестанет работать. Продолжить?')) return
  publicAccessBusy.value = true
  error.value = ''
  try {
    publicLink.value = await notesApi.regeneratePublicLink(note.value.id)
    publicCopyOk.value = false
  } catch (e) {
    error.value = errMessage(e)
  } finally {
    publicAccessBusy.value = false
  }
}

async function copyPublicUrl() {
  const u = publicUrl.value
  if (!u) return
  try {
    await navigator.clipboard.writeText(u)
    publicCopyOk.value = true
    setTimeout(() => {
      publicCopyOk.value = false
    }, 2000)
  } catch {
    error.value = 'Не удалось скопировать ссылку'
  }
}

onBeforeRouteLeave(async () => {
  await flushSave()
})

function onVisibilityChange() {
  if (document.visibilityState === 'hidden') {
    void flushSave()
  } else if (document.visibilityState === 'visible') {
    void refetchNoteIfRemoteNewer()
  }
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
          <button
            v-if="!isTrashed && !isOwner"
            type="button"
            class="share-hub-tile share-hub-tile-mail share-mail-bar"
            @click="openMailModal"
          >
            <span class="share-hub-ico" aria-hidden="true">✉</span>
            По почте
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
        <section v-if="isOwner && !isTrashed" class="share-hub" aria-label="Обмен и доступ">
          <div class="share-hub-toolbar">
            <button type="button" class="share-hub-tile share-hub-tile-mail" @click="openMailModal">
              <span class="share-hub-ico" aria-hidden="true">✉</span>
              <span class="share-hub-tile-text">По почте</span>
            </button>
            <div class="share-hub-divider" aria-hidden="true" />
            <div class="share-hub-link-line">
              <span class="share-hub-tile-label">Ссылка</span>
              <span v-if="publicLink && !publicShareExpanded" class="share-hub-role-pill">{{
                publicRole === 'editor' ? 'Редактирование' : 'Чтение'
              }}</span>
              <label class="public-switch public-switch--compact">
                <input
                  type="checkbox"
                  :checked="!!publicLink"
                  :disabled="publicAccessBusy"
                  @change="onPublicAccessToggle"
                />
                <span class="public-switch-ui" aria-hidden="true" />
              </label>
              <button
                type="button"
                class="share-hub-expand"
                :aria-expanded="publicShareExpanded"
                @click="publicShareExpanded = !publicShareExpanded"
              >
                <span class="share-hub-chevron" :class="{ open: publicShareExpanded }" aria-hidden="true" />
                <span>{{ publicShareExpanded ? 'Свернуть' : 'Настроить' }}</span>
              </button>
            </div>
          </div>
          <div v-show="publicShareExpanded" class="share-hub-drop">
            <template v-if="publicLink">
              <div class="public-mode-row">
                <span class="mode-label">Доступ по ссылке</span>
                <div class="mode-seg" role="group" aria-label="Режим общей ссылки">
                  <button
                    type="button"
                    class="mode-btn"
                    :class="{ active: publicRole === 'viewer' }"
                    :disabled="publicAccessBusy"
                    @click="setPublicRole('viewer')"
                  >
                    Только чтение
                  </button>
                  <button
                    type="button"
                    class="mode-btn"
                    :class="{ active: publicRole === 'editor' }"
                    :disabled="publicAccessBusy"
                    @click="setPublicRole('editor')"
                  >
                    Редактирование
                  </button>
                </div>
              </div>
              <div class="public-url-row">
                <input class="public-url-input" type="text" readonly :value="publicUrl" />
                <button type="button" class="share-hub-btn-secondary" :disabled="publicAccessBusy" @click="copyPublicUrl">
                  {{ publicCopyOk ? 'Скопировано' : 'Копировать' }}
                </button>
              </div>
              <p class="public-regen-hint">
                <button type="button" class="linkish" :disabled="publicAccessBusy" @click="regenPublicLink">
                  Новый адрес ссылки
                </button>
                <span class="muted small"> — прежний перестанет работать</span>
              </p>
            </template>
          </div>

          <button
            type="button"
            class="share-hub-subtoggle"
            :aria-expanded="emailSharesExpanded"
            @click="emailSharesExpanded = !emailSharesExpanded"
          >
            <span class="share-hub-chevron" :class="{ open: emailSharesExpanded }" aria-hidden="true" />
            <span>Доступ по email</span>
            <span v-if="shares.length" class="share-hub-count">{{ shares.length }}</span>
          </button>
          <div v-show="emailSharesExpanded" class="share-hub-drop share-hub-drop-email">
            <div class="share-form-row">
              <input v-model="shareEmail" class="share-input" type="email" placeholder="Email пользователя" />
              <select v-model="shareRole" class="share-select">
                <option value="viewer">Читатель</option>
                <option value="editor">Редактор</option>
              </select>
              <button type="button" class="share-hub-btn-secondary" @click="addShare">Добавить</button>
            </div>
            <ul v-if="shares.length" class="share-email-list">
              <li v-for="s in shares" :key="s.id" class="share-email-item">
                <span class="share-email-who">{{ s.shared_with_user_id || s.invite_email }}</span>
                <span class="share-email-role">{{ s.role }}</span>
                <button type="button" class="linkish" @click="removeShare(s)">Убрать</button>
              </li>
            </ul>
            <p v-else class="muted small share-email-empty">Пока никого не приглашали</p>
          </div>
        </section>

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
        <div v-if="!isTrashed" class="folder-reminder-line">
          <div class="folder-bar">
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
          <div v-if="editorEditable" class="reminder-compact">
            <button
              type="button"
              class="reminder-compact-btn"
              :class="{ 'reminder-compact-btn--open': reminderPanelOpen }"
              title="Напоминание"
              @click="reminderPanelOpen = !reminderPanelOpen"
            >
              <span class="reminder-ico" aria-hidden="true">⏰</span>
              <span v-if="hasReminderSet" class="reminder-compact-sum">{{ fmtCompactMsk(note.reminder_at) }}</span>
              <span v-else class="reminder-compact-ph muted">Напоминание</span>
            </button>
            <div v-show="reminderPanelOpen" class="reminder-popover">
              <input
                v-model="reminderDatetimeLocal"
                type="datetime-local"
                class="reminder-dl"
                step="60"
              />
              <div class="reminder-popover-actions">
                <button type="button" class="btn-rem-save" :disabled="saving" @click="saveReminderFromForm">OK</button>
                <button
                  v-if="hasReminderSet"
                  type="button"
                  class="btn-rem-clear"
                  :disabled="saving"
                  @click="clearReminder"
                >
                  Убрать
                </button>
              </div>
            </div>
          </div>
        </div>

        <NoteEditor v-model:contentJson="contentJson" :editable="editorEditable" />
        </div>
      </template>

      <div v-if="showMailModal" class="modal-backdrop share-modal-backdrop" @click.self="closeMailModal">
        <div class="modal share-modal" role="dialog" aria-labelledby="mail-title">
          <h2 id="mail-title">Отправить заметку на почту</h2>
          <p class="muted small share-modal-lead">
            Укажите email получателя (несколько — через запятую). Нужен SMTP в настройках API
            (<code>/api/users/me/smtp</code>).
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
.folder-reminder-line {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 0.35rem 0.75rem;
  margin-bottom: 0.55rem;
}
.folder-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.45rem 0.65rem;
  flex: 1 1 200px;
  margin-bottom: 0;
  min-width: 0;
}
.folder-lab {
  font-size: 0.78rem;
  font-weight: 500;
}
.folder-select {
  padding: 0.26rem 0.4rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  font: inherit;
  font-size: 0.74rem;
  background: var(--panel);
  color: inherit;
  min-width: 140px;
  max-width: 100%;
}
.reminder-compact {
  position: relative;
  flex: 0 0 auto;
  align-self: center;
}
.reminder-compact-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.28rem;
  padding: 0.22rem 0.4rem;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--panel);
  font: inherit;
  font-size: 0.68rem;
  font-weight: 500;
  color: #475569;
  cursor: pointer;
  max-width: 11rem;
  transition:
    border-color 0.12s ease,
    background 0.12s ease;
}
.reminder-compact-btn:hover {
  border-color: rgba(37, 99, 235, 0.3);
  background: var(--list-row-hover);
}
.reminder-compact-btn--open {
  border-color: rgba(37, 99, 235, 0.35);
}
.reminder-ico {
  font-size: 0.75rem;
  line-height: 1;
  opacity: 0.85;
}
.reminder-compact-sum {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  color: var(--accent);
  font-weight: 600;
}
.reminder-compact-ph {
  font-size: 0.65rem;
}
.reminder-popover {
  position: absolute;
  z-index: 30;
  right: 0;
  top: calc(100% + 4px);
  padding: 0.4rem 0.45rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--panel);
  box-shadow: var(--shadow-panel, 0 4px 20px rgba(15, 23, 42, 0.1));
  min-width: 15rem;
  max-width: min(100vw - 2rem, 18rem);
}
.reminder-dl {
  width: 100%;
  box-sizing: border-box;
  padding: 0.3rem 0.35rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  font: inherit;
  font-size: 0.72rem;
  font-variant-numeric: tabular-nums;
  background: #fff;
  color: inherit;
  margin-bottom: 0.4rem;
}
.reminder-dl:focus {
  outline: none;
  border-color: rgba(37, 99, 235, 0.45);
}
.reminder-popover-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  align-items: center;
}
.btn-rem-save {
  padding: 0.38rem 0.75rem;
  border-radius: 8px;
  border: none;
  background: var(--accent);
  color: #fff;
  font: inherit;
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 1px 2px rgba(37, 99, 235, 0.25);
}
.btn-rem-save:hover:not(:disabled) {
  background: var(--accent-hover);
}
.btn-rem-save:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.btn-rem-clear {
  padding: 0.38rem 0.65rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: transparent;
  font: inherit;
  font-size: 0.76rem;
  color: var(--text-muted);
  cursor: pointer;
}
.btn-rem-clear:hover:not(:disabled) {
  border-color: var(--danger);
  color: var(--danger);
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
.share-hub {
  margin-bottom: 1rem;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  background: linear-gradient(165deg, rgba(239, 246, 255, 0.55) 0%, rgba(248, 250, 252, 0.98) 48%, #fff 100%);
  box-shadow:
    0 1px 2px rgba(15, 23, 42, 0.04),
    0 8px 24px rgba(15, 23, 42, 0.05);
  overflow: hidden;
}
.share-hub-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.65rem;
  padding: 0.55rem 0.75rem;
}
.share-hub-tile {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.38rem 0.75rem;
  border-radius: 10px;
  border: 1px solid rgba(37, 99, 235, 0.22);
  background: rgba(255, 255, 255, 0.85);
  cursor: pointer;
  font: inherit;
  font-size: 0.8rem;
  font-weight: 600;
  color: #1e40af;
  transition:
    background 0.12s ease,
    border-color 0.12s ease,
    box-shadow 0.12s ease;
}
.share-hub-tile:hover {
  background: #fff;
  border-color: rgba(37, 99, 235, 0.4);
  box-shadow: 0 1px 4px rgba(37, 99, 235, 0.12);
}
.share-hub-ico {
  font-size: 1rem;
  line-height: 1;
  opacity: 0.92;
}
.share-hub-divider {
  width: 1px;
  height: 1.5rem;
  background: rgba(148, 163, 184, 0.45);
  flex-shrink: 0;
}
.share-hub-link-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem 0.55rem;
  flex: 1;
  min-width: 0;
}
.share-hub-tile-label {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}
.share-hub-role-pill {
  font-size: 0.68rem;
  font-weight: 600;
  padding: 0.12rem 0.45rem;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.1);
  color: #1d4ed8;
}
.share-hub-expand {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.32rem 0.5rem;
  border: none;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  font: inherit;
  font-size: 0.76rem;
  font-weight: 600;
  color: #475569;
}
.share-hub-expand:hover {
  background: rgba(37, 99, 235, 0.06);
  color: #1e40af;
}
.share-hub-chevron {
  display: inline-block;
  width: 0.35rem;
  height: 0.35rem;
  border-right: 2px solid currentColor;
  border-bottom: 2px solid currentColor;
  transform: rotate(-45deg);
  transition: transform 0.15s ease;
  flex-shrink: 0;
}
.share-hub-chevron.open {
  transform: rotate(45deg);
}
.share-hub-drop {
  padding: 0 0.75rem 0.65rem;
  border-top: 1px solid rgba(226, 232, 240, 0.95);
  background: rgba(255, 255, 255, 0.5);
}
.share-hub-subtoggle {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: none;
  border-top: 1px solid rgba(226, 232, 240, 0.95);
  background: rgba(248, 250, 252, 0.75);
  cursor: pointer;
  font: inherit;
  font-size: 0.8rem;
  font-weight: 600;
  color: #334155;
  text-align: left;
}
.share-hub-subtoggle:hover {
  background: rgba(241, 245, 249, 0.95);
}
.share-hub-count {
  margin-left: auto;
  font-size: 0.7rem;
  font-weight: 700;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  background: rgba(100, 116, 139, 0.15);
  color: #475569;
}
.share-hub-drop-email {
  padding: 0.65rem 0.75rem 0.75rem;
}
.share-form-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  align-items: center;
  margin-bottom: 0.5rem;
}
.share-input {
  flex: 1 1 10rem;
  min-width: 0;
  padding: 0.4rem 0.55rem;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.45);
  font: inherit;
  font-size: 0.78rem;
  background: #fff;
  color: inherit;
}
.share-input:focus {
  outline: none;
  border-color: rgba(37, 99, 235, 0.45);
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.1);
}
.share-select {
  padding: 0.4rem 0.45rem;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.45);
  font: inherit;
  font-size: 0.78rem;
  background: #fff;
  color: inherit;
}
.share-hub-btn-secondary {
  padding: 0.4rem 0.7rem;
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
.share-hub-btn-secondary:hover:not(:disabled) {
  background: rgba(37, 99, 235, 0.06);
}
.share-hub-btn-secondary:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.share-email-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.share-email-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.45rem 0.65rem;
  padding: 0.4rem 0.5rem;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(226, 232, 240, 0.9);
  font-size: 0.78rem;
}
.share-email-who {
  flex: 1 1 8rem;
  min-width: 0;
  word-break: break-all;
}
.share-email-role {
  font-size: 0.72rem;
  font-weight: 600;
  color: #64748b;
  text-transform: lowercase;
}
.share-email-empty {
  margin: 0.2rem 0 0;
}
.public-switch--compact {
  margin: 0 0.15rem;
}
.public-switch {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  user-select: none;
  font-size: 0.8rem;
  font-weight: 600;
  color: #334155;
}
.public-switch input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}
.public-switch-ui {
  width: 2.5rem;
  height: 1.35rem;
  border-radius: 999px;
  background: #cbd5e1;
  position: relative;
  transition: background 0.15s ease;
  flex-shrink: 0;
}
.public-switch-ui::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: calc(1.35rem - 4px);
  height: calc(1.35rem - 4px);
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
  transition: transform 0.15s ease;
}
.public-switch input:checked + .public-switch-ui {
  background: #2563eb;
}
.public-switch input:checked + .public-switch-ui::after {
  transform: translateX(1.12rem);
}
.public-switch input:focus-visible + .public-switch-ui {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.public-switch input:disabled + .public-switch-ui {
  opacity: 0.55;
}
.public-mode-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
  margin: 0.65rem 0 0.75rem;
}
.mode-label {
  font-size: 0.78rem;
  font-weight: 600;
  color: #475569;
}
.mode-seg {
  display: inline-flex;
  border-radius: 10px;
  border: 1px solid var(--border);
  overflow: hidden;
  background: var(--panel);
}
.mode-btn {
  border: none;
  margin: 0;
  padding: 0.4rem 0.85rem;
  font: inherit;
  font-size: 0.78rem;
  cursor: pointer;
  background: transparent;
  color: #475569;
}
.mode-btn:hover:not(:disabled) {
  background: rgba(37, 99, 235, 0.06);
}
.mode-btn.active {
  background: rgba(37, 99, 235, 0.14);
  color: #1d4ed8;
  font-weight: 600;
}
.mode-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.public-url-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  align-items: stretch;
}
.public-url-input {
  flex: 1 1 12rem;
  min-width: 0;
  box-sizing: border-box;
  padding: 0.45rem 0.55rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  font-size: 0.72rem;
  font-family: ui-monospace, monospace;
  background: #fff;
  color: inherit;
}
.public-regen-hint {
  margin: 0.5rem 0 0;
  font-size: 0.75rem;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  border: 0;
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
.share-modal-backdrop {
  backdrop-filter: blur(2px);
}
.share-modal {
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  background: linear-gradient(180deg, #fff 0%, #f8fafc 100%);
  box-shadow:
    0 20px 50px rgba(15, 23, 42, 0.15),
    0 0 0 1px rgba(255, 255, 255, 0.8) inset;
  max-width: 440px;
}
.share-modal-lead {
  line-height: 1.45;
}
.share-mail-bar {
  font-size: 0.78rem;
  padding: 0.32rem 0.55rem;
}
.share-hub-drop .public-mode-row {
  margin-top: 0.55rem;
  margin-bottom: 0.55rem;
}
.share-hub-drop .public-url-row {
  margin-bottom: 0.15rem;
}
</style>
