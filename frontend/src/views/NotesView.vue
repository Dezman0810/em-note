<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import NoteEditorColumn from '../components/NoteEditorColumn.vue'
import AdminUsersModal from '../components/AdminUsersModal.vue'
import ReminderCalendar from '../components/ReminderCalendar.vue'
import { errMessage, foldersApi, notesApi, tagsApi } from '../api/client'
import type { Folder, FolderNoteCounts, Note, Tag } from '../api/types'
import { useAuthStore } from '../stores/auth'
import { fmtCompactMsk, fmtMsk } from '../utils/datetime'
import { foldersSortedAlphabetical } from '../utils/folders'
import { isStrictDescendantOf, tagsWithChildrenSet, visibleTagsForNav } from '../utils/tagsTree'

const adminUsersOpen = ref(false)

const COL_FOLDER_KEY = 'note-ui-w-folder'
const TAG_NAV_COLLAPSED_KEY = 'note-ui-tag-collapsed'
const COL_LIST_KEY = 'note-ui-w-list'
const FOLDER_NAV_MAIN_H_KEY = 'note-ui-folder-main-h'
const FOLDERS_LIST_EXPANDED_KEY = 'note-ui-folders-list-expanded'
const TAGS_LIST_EXPANDED_KEY = 'note-ui-tags-list-expanded'

function readBoolKey(key: string, fallback: boolean): boolean {
  try {
    const raw = localStorage.getItem(key)
    if (raw === null) return fallback
    return raw === '1' || raw === 'true'
  } catch {
    return fallback
  }
}

function writeBoolKey(key: string, v: boolean) {
  try {
    localStorage.setItem(key, v ? '1' : '0')
  } catch {
    /* */
  }
}

function readColW(key: string, fallback: number, min: number, max: number): number {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return fallback
    const n = parseInt(raw, 10)
    if (Number.isNaN(n)) return fallback
    return Math.min(max, Math.max(min, n))
  } catch {
    return fallback
  }
}

const colFolderPx = ref(readColW(COL_FOLDER_KEY, 220, 120, 420))
const colListPx = ref(readColW(COL_LIST_KEY, 300, 160, 640))

type GutterDrag = null | 'folder' | 'list' | 'folderNavV'
const gutterDrag = ref<GutterDrag>(null)
let gutterStartX = 0
let gutterStartFolder = 0
let gutterStartList = 0
let gutterStartY = 0
let gutterStartFolderMainH = 0

const folderNavRef = ref<HTMLElement | null>(null)
const folderNavMainPx = ref(
  readColW(FOLDER_NAV_MAIN_H_KEY, 200, 72, 560)
)

function persistColWidths() {
  try {
    localStorage.setItem(COL_FOLDER_KEY, String(colFolderPx.value))
    localStorage.setItem(COL_LIST_KEY, String(colListPx.value))
    localStorage.setItem(FOLDER_NAV_MAIN_H_KEY, String(folderNavMainPx.value))
  } catch {
    /* */
  }
}

function onGutterDown(which: 'folder' | 'list', e: MouseEvent) {
  e.preventDefault()
  gutterDrag.value = which
  gutterStartX = e.clientX
  gutterStartFolder = colFolderPx.value
  gutterStartList = colListPx.value
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('mousemove', onGutterMove)
  window.addEventListener('mouseup', onGutterUp)
}

function folderNavMainMax(): number {
  const nav = folderNavRef.value
  if (!nav) return 560
  const GUTTER = 6
  const minBottom = 112
  return Math.max(72, nav.clientHeight - minBottom - GUTTER)
}

function onFolderNavVGutterDown(e: MouseEvent) {
  e.preventDefault()
  gutterDrag.value = 'folderNavV'
  gutterStartY = e.clientY
  gutterStartFolderMainH = folderNavMainPx.value
  document.body.style.cursor = 'row-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('mousemove', onGutterMove)
  window.addEventListener('mouseup', onGutterUp)
}

function onGutterMove(e: MouseEvent) {
  if (!gutterDrag.value) return
  if (gutterDrag.value === 'folderNavV') {
    const dy = e.clientY - gutterStartY
    const maxH = folderNavMainMax()
    folderNavMainPx.value = Math.min(maxH, Math.max(72, gutterStartFolderMainH + dy))
    return
  }
  const dx = e.clientX - gutterStartX
  if (gutterDrag.value === 'folder') {
    colFolderPx.value = Math.min(420, Math.max(120, gutterStartFolder + dx))
  } else {
    colListPx.value = Math.min(640, Math.max(160, gutterStartList + dx))
  }
}

function onGutterUp() {
  const was = gutterDrag.value
  gutterDrag.value = null
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  window.removeEventListener('mousemove', onGutterMove)
  window.removeEventListener('mouseup', onGutterUp)
  persistColWidths()
  if (was === 'folderNavV') {
    const maxH = folderNavMainMax()
    folderNavMainPx.value = Math.min(maxH, Math.max(72, folderNavMainPx.value))
    persistColWidths()
  }
}

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const notes = ref<Note[]>([])
const folders = ref<Folder[]>([])
const newFolderName = ref('')
const q = ref('')
const loading = ref(true)
const error = ref('')

const filterFolder = ref<string>('all')
const filterTagId = ref<string | null>(null)
const tags = ref<Tag[]>([])
const tagCountById = ref<Record<string, number>>({})
const folderNoteCounts = ref<FolderNoteCounts | null>(null)
const foldersListExpanded = ref(readBoolKey(FOLDERS_LIST_EXPANDED_KEY, true))
const tagsListExpanded = ref(readBoolKey(TAGS_LIST_EXPANDED_KEY, true))
/** Увеличивается после load — обновляет данные календаря напоминаний. */
const reminderRefreshSignal = ref(0)

const folderNavMainStyle = computed(() => {
  if (filterFolder.value === 'trash') {
    return {
      flex: '1 1 auto',
      minHeight: '0',
      overflowY: 'auto' as const,
    }
  }
  return {
    flex: '0 0 auto',
    height: `${folderNavMainPx.value}px`,
    minHeight: '72px',
    overflowY: 'auto' as const,
  }
})

const folderNavBottomStyle = computed(() => {
  if (filterFolder.value === 'trash') {
    return { flex: '0 0 auto' as const }
  }
  return {
    flex: '1 1 auto',
    minHeight: '0',
    display: 'flex',
    flexDirection: 'column' as const,
  }
})

function readTagNavCollapsed(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(TAG_NAV_COLLAPSED_KEY)
    if (!raw) return {}
    const p = JSON.parse(raw) as Record<string, boolean>
    return p && typeof p === 'object' ? p : {}
  } catch {
    return {}
  }
}

const collapsedTagIds = ref<Record<string, boolean>>(readTagNavCollapsed())

const tagsWithKids = computed(() => tagsWithChildrenSet(tags.value))

const tagsVisibleInSidebar = computed(() =>
  visibleTagsForNav(tags.value, collapsedTagIds.value)
)

function persistTagNavCollapsed() {
  try {
    localStorage.setItem(TAG_NAV_COLLAPSED_KEY, JSON.stringify(collapsedTagIds.value))
  } catch {
    /* */
  }
}

function toggleTagNavCollapse(tagId: string, e: Event) {
  e.preventDefault()
  e.stopPropagation()
  const willCollapse = !collapsedTagIds.value[tagId]
  collapsedTagIds.value = {
    ...collapsedTagIds.value,
    [tagId]: willCollapse,
  }
  persistTagNavCollapsed()
  const fid = filterTagId.value
  if (willCollapse && fid && isStrictDescendantOf(tags.value, tagId, fid)) {
    filterTagId.value = null
  }
}

const foldersSorted = computed(() => foldersSortedAlphabetical(folders.value))

function countInFolder(folderId: string): number {
  const fc = folderNoteCounts.value?.folder_counts ?? []
  const row = fc.find((x) => x.folder_id === folderId)
  return row?.count ?? 0
}

const scopeNoteTotal = computed(() => {
  if (!folderNoteCounts.value) return 0
  if (filterFolder.value === 'all') return folderNoteCounts.value.total
  if (filterFolder.value === 'trash') return 0
  return countInFolder(filterFolder.value)
})

async function loadFolderCounts() {
  try {
    folderNoteCounts.value = await foldersApi.noteCounts()
  } catch {
    /* не сбрасываем — оставляем предыдущие числа */
  }
}

function toggleFoldersList(e: Event) {
  e.preventDefault()
  e.stopPropagation()
  foldersListExpanded.value = !foldersListExpanded.value
  writeBoolKey(FOLDERS_LIST_EXPANDED_KEY, foldersListExpanded.value)
}

function toggleTagsList(e: Event) {
  e.preventDefault()
  e.stopPropagation()
  tagsListExpanded.value = !tagsListExpanded.value
  writeBoolKey(TAGS_LIST_EXPANDED_KEY, tagsListExpanded.value)
}

/** Активная заметка из URL /notes/:id */
const activeNoteId = computed(() =>
  route.name === 'note' && typeof route.params.id === 'string' ? route.params.id : null
)

type NoteSort =
  | 'updated_desc'
  | 'updated_asc'
  | 'created_desc'
  | 'created_asc'
  | 'title_asc'
  | 'title_desc'

const noteSort = ref<NoteSort>('created_desc')

const sortedNotes = computed(() => {
  const list = [...notes.value]
  const s = noteSort.value
  list.sort((a, b) => {
    if (s === 'title_asc') {
      return (a.title || '').localeCompare(b.title || '', 'ru', { sensitivity: 'base' })
    }
    if (s === 'title_desc') {
      return (b.title || '').localeCompare(a.title || '', 'ru', { sensitivity: 'base' })
    }
    if (s === 'created_asc') {
      return new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
    }
    if (s === 'created_desc') {
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    }
    if (s === 'updated_asc') {
      return new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime()
    }
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
  })
  return list
})

async function loadFolders() {
  try {
    folders.value = await foldersApi.list()
  } catch (e) {
    error.value = errMessage(e)
  }
}

function folderListParams(): { folder_id?: string } {
  if (filterFolder.value !== 'all' && filterFolder.value !== 'trash') {
    return { folder_id: filterFolder.value }
  }
  return {}
}

function tagFilterParams(): { tag_id?: string } {
  return filterTagId.value ? { tag_id: filterTagId.value } : {}
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    if (filterFolder.value === 'trash') {
      notes.value = await notesApi.listTrash()
      tags.value = []
      tagCountById.value = {}
      return
    }
    const fParams = folderListParams()
    const tParams = tagFilterParams()
    const query = q.value.trim()
    const noteList = query
      ? await notesApi.search(query, { ...fParams, ...tParams })
      : await notesApi.list({ ...fParams, ...tParams })
    notes.value = noteList

    const countsParams =
      filterFolder.value !== 'all' && filterFolder.value !== 'trash'
        ? { folder_id: filterFolder.value }
        : undefined
    try {
      const [tagList, counts] = await Promise.all([
        tagsApi.list(),
        tagsApi.noteCounts(countsParams),
      ])
      tags.value = tagList
      const map: Record<string, number> = {}
      for (const c of counts) {
        map[String(c.tag_id)] = c.count
      }
      tagCountById.value = map
    } catch {
      try {
        tags.value = await tagsApi.list()
      } catch (e2) {
        error.value = errMessage(e2)
        tags.value = []
      }
      /* не обнуляем счётчики — иначе при сбое /counts все метки покажут (0) */
    }
  } catch (e) {
    error.value = errMessage(e)
    if (filterFolder.value === 'trash') {
      notes.value = []
    }
  } finally {
    loading.value = false
  }
  if (filterFolder.value !== 'trash') {
    void loadFolderCounts()
    reminderRefreshSignal.value++
  }
}

async function createFolder() {
  const name = newFolderName.value.trim()
  if (!name) return
  try {
    await foldersApi.create({ name })
    newFolderName.value = ''
    error.value = ''
    await loadFolders()
  } catch (e) {
    error.value = errMessage(e)
  }
}

async function deleteFolder(f: Folder) {
  if (!confirm(`Удалить папку «${f.name}»? Заметки снова попадут в общий список «Все заметки».`)) return
  try {
    await foldersApi.remove(f.id)
    if (filterFolder.value === f.id) filterFolder.value = 'all'
    await loadFolders()
    await load()
  } catch (e) {
    error.value = errMessage(e)
  }
}

async function renameFolder(f: Folder) {
  const name = prompt('Новое имя папки', f.name)
  if (!name || !name.trim()) return
  try {
    await foldersApi.update(f.id, { name: name.trim() })
    error.value = ''
    await loadFolders()
    await load()
  } catch (e) {
    error.value = errMessage(e)
  }
}

async function restoreNote(n: Note, ev: Event) {
  ev.preventDefault()
  ev.stopPropagation()
  try {
    await notesApi.restore(n.id)
    error.value = ''
    await loadFolders()
    await load()
  } catch (e) {
    error.value = errMessage(e)
  }
}

async function purgeNote(n: Note, ev: Event) {
  ev.preventDefault()
  ev.stopPropagation()
  if (!confirm(`Удалить «${n.title || 'Без названия'}» навсегда?`)) return
  try {
    await notesApi.purge(n.id)
    error.value = ''
    await load()
    if (activeNoteId.value === n.id) {
      await router.push({ name: 'notes' })
    }
  } catch (e) {
    error.value = errMessage(e)
  }
}

async function createNote() {
  try {
    if (auth.user && !auth.user.can_create_notes) {
      error.value = 'Создание заметок отключено. Доступ выдаёт администратор.'
      return
    }
    if (filterFolder.value === 'trash') {
      error.value = 'Создайте заметку вне корзины'
      return
    }
    const folder_id =
      filterFolder.value !== 'all' && filterFolder.value !== 'trash'
        ? filterFolder.value
        : undefined
    const n = await notesApi.create({
      title: 'Без названия',
      content_json: '{}',
      folder_id,
    })
    await load()
    await router.push({ name: 'note', params: { id: n.id } })
  } catch (e) {
    error.value = errMessage(e)
  }
}

function logout() {
  auth.logout()
  router.push('/login')
}

function openNote(id: string) {
  void router.push({ name: 'note', params: { id } })
}

function noteRowTitle(n: Note): string {
  const parts = [
    `Создано: ${fmtMsk(n.created_at)}`,
    `Изменено: ${fmtMsk(n.updated_at)}`,
  ]
  if (n.deleted_at) parts.push(`Удалено: ${fmtMsk(n.deleted_at)}`)
  return parts.join('\n')
}

function noteBodyPreview(n: Note): string {
  const raw = (n.content_plain || '').replace(/\s+/g, ' ').trim()
  if (!raw) return ''
  const max = 140
  if (raw.length <= max) return raw
  return raw.slice(0, max).trimEnd() + '…'
}

onMounted(async () => {
  await loadFolders()
  await load()
})

watch(filterFolder, (folder) => {
  if (folder === 'trash') filterTagId.value = null
  void load()
})
watch(filterTagId, () => {
  if (filterFolder.value !== 'trash') void load()
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onGutterMove)
  window.removeEventListener('mouseup', onGutterUp)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
})
</script>

<template>
  <div class="workspace">
    <header class="workspace-header">
      <div class="header-left">
        <h1 class="logo">Note</h1>
        <span class="header-sub">Заметки</span>
      </div>
      <div class="actions">
        <button
          v-if="auth.user?.is_admin"
          type="button"
          class="btn admin-top-btn"
          title="Пользователи и доступ к созданию заметок"
          @click="adminUsersOpen = true"
        >
          Админка
        </button>
        <div class="search-wrap">
          <input
            v-model="q"
            class="search"
            type="search"
            placeholder="Поиск по заголовку и тексту…"
            aria-label="Поиск заметок"
            @keyup.enter="load"
          />
        </div>
        <div class="action-cluster">
          <button type="button" class="btn secondary" @click="load">Найти</button>
          <button type="button" class="btn secondary" @click="router.push('/tags')">Метки</button>
          <button
            type="button"
            class="btn primary"
            :disabled="auth.user != null && !auth.user.can_create_notes"
            :title="
              auth.user && !auth.user.can_create_notes
                ? 'Создание заметок отключено. Обратитесь к администратору.'
                : ''
            "
            @click="createNote"
          >
            Новая заметка
          </button>
        </div>
        <div class="header-user">
          <span class="user" v-if="auth.user">{{ auth.user.email }}</span>
          <button type="button" class="btn ghost" @click="logout">Выйти</button>
        </div>
      </div>
    </header>

    <AdminUsersModal v-model:open="adminUsersOpen" />

    <div class="workspace-body">
      <aside
        class="folders-aside sidebar-panel"
        :style="{ width: colFolderPx + 'px', flexShrink: 0 }"
      >
        <div class="aside-block">
          <h2 class="aside-title">Папки</h2>
        </div>
        <div class="folder-actions">
          <input
            v-model="newFolderName"
            type="text"
            placeholder="Новая папка…"
            @keyup.enter="createFolder"
          />
          <button type="button" class="btn-sm primary" @click="createFolder">+</button>
        </div>
        <nav ref="folderNavRef" class="folder-nav">
          <div class="folder-nav-main" :style="folderNavMainStyle">
            <div class="folder-all-row">
              <button
                v-if="foldersSorted.length"
                type="button"
                class="section-chevron"
                :class="{ 'section-chevron--collapsed': !foldersListExpanded }"
                title="Показать или скрыть список папок"
                @click="toggleFoldersList"
              >
                {{ foldersListExpanded ? '▾' : '▸' }}
              </button>
              <span v-else class="section-chevron-spacer" />
              <button
                type="button"
                class="folder-filter grow folder-filter-all"
                :class="{ on: filterFolder === 'all' }"
                @click="filterFolder = 'all'"
              >
                <span class="folder-label">Все заметки</span>
                <span v-if="folderNoteCounts" class="tag-count">({{ folderNoteCounts.total }})</span>
              </button>
            </div>
            <div v-show="foldersListExpanded" class="folder-rows">
              <div v-for="f in foldersSorted" :key="f.id" class="folder-row">
                <button
                  type="button"
                  class="folder-filter grow"
                  :class="{ on: filterFolder === f.id }"
                  @click="filterFolder = f.id"
                >
                  <span class="folder-label">{{ f.name }}</span>
                  <span class="tag-count">({{ countInFolder(f.id) }})</span>
                </button>
                <button type="button" class="btn-rename" title="Переименовать" @click.stop="renameFolder(f)">
                  ✎
                </button>
                <button type="button" class="btn-del" title="Удалить папку" @click.stop="deleteFolder(f)">
                  ×
                </button>
              </div>
            </div>
          </div>
          <ReminderCalendar
            v-if="filterFolder !== 'trash'"
            :refresh-signal="reminderRefreshSignal"
            @open-note="openNote"
          />
          <div
            v-if="filterFolder !== 'trash'"
            class="folder-nav-v-gutter"
            title="Потяните: больше места для папок или для меток"
            @mousedown="onFolderNavVGutterDown($event)"
          />
          <div class="folder-nav-bottom" :style="folderNavBottomStyle">
            <div v-if="filterFolder !== 'trash'" class="folder-nav-tags">
              <h3 class="tags-aside-title">Метки</h3>
              <div class="folder-all-row tag-all-wrap">
                <button
                  v-if="tags.length"
                  type="button"
                  class="section-chevron"
                  :class="{ 'section-chevron--collapsed': !tagsListExpanded }"
                  title="Показать или скрыть список меток"
                  @click="toggleTagsList"
                >
                  {{ tagsListExpanded ? '▾' : '▸' }}
                </button>
                <span v-else class="section-chevron-spacer" />
                <button
                  type="button"
                  class="folder-filter tag-filter grow folder-filter-all"
                  :class="{ on: filterTagId === null }"
                  @click="filterTagId = null"
                >
                  <span class="folder-label">Все метки</span>
                  <span v-if="folderNoteCounts" class="tag-count">({{ scopeNoteTotal }})</span>
                </button>
              </div>
              <button
                v-for="t in tagsVisibleInSidebar"
                v-show="tagsListExpanded"
                :key="t.id"
                type="button"
                class="folder-filter tag-filter tag-sidebar-row"
                :class="{ on: filterTagId === t.id }"
                :style="{ paddingLeft: (0.35 + Math.max(0, t.depth - 1) * 0.55) + 'rem' }"
                @click="filterTagId = t.id"
              >
                <span
                  v-if="tagsWithKids.has(t.id)"
                  class="tag-chevron"
                  title="Свернуть / развернуть вложенные"
                  role="button"
                  tabindex="0"
                  @click="toggleTagNavCollapse(t.id, $event)"
                  @keydown.enter.prevent="toggleTagNavCollapse(t.id, $event)"
                  @keydown.space.prevent="toggleTagNavCollapse(t.id, $event)"
                >
                  {{ collapsedTagIds[t.id] ? '▸' : '▾' }}
                </span>
                <span v-else class="tag-chevron tag-chevron-spacer" aria-hidden="true" />
                <span class="tag-sidebar-name">{{ t.name }}</span>
                <span class="tag-count">({{ tagCountById[t.id] ?? 0 }})</span>
              </button>
            </div>
            <div class="folder-nav-footer">
              <button
                type="button"
                class="folder-filter trash-filter"
                :class="{ on: filterFolder === 'trash' }"
                @click="filterFolder = 'trash'"
              >
                Корзина
              </button>
            </div>
          </div>
        </nav>
      </aside>

      <div
        class="col-gutter"
        title="Потяните, чтобы изменить ширину колонки"
        @mousedown="onGutterDown('folder', $event)"
      />

      <div
        class="notes-list-col"
        :style="{ width: colListPx + 'px', flexShrink: 0 }"
      >
        <div class="list-toolbar">
          <label class="sort-lab" for="note-sort">Сортировка</label>
          <select id="note-sort" v-model="noteSort" class="sort-select">
            <option value="updated_desc">Дата изменения — сначала новые</option>
            <option value="updated_asc">Дата изменения — сначала старые</option>
            <option value="created_desc">Дата создания — сначала новые</option>
            <option value="created_asc">Дата создания — сначала старые</option>
            <option value="title_asc">Название — А → Я</option>
            <option value="title_desc">Название — Я → А</option>
          </select>
        </div>
        <div class="list-scroll">
          <p v-if="error" class="err">{{ error }}</p>
          <!-- Не скрываем список при обновлении: иначе заметки «мигают» -->
          <p v-if="loading && sortedNotes.length === 0" class="muted load-hint">Загрузка…</p>
          <ul
            v-else
            class="list"
            :class="{ 'list--refreshing': loading && sortedNotes.length > 0 }"
          >
            <li v-for="n in sortedNotes" :key="n.id" :class="{ trashrow: filterFolder === 'trash' }">
              <button
                type="button"
                class="note-item"
                :class="{ current: n.id === activeNoteId }"
                :title="noteRowTitle(n)"
                @click="openNote(n.id)"
              >
                <span class="note-title">{{ n.title || 'Без названия' }}</span>
                <span v-if="noteBodyPreview(n)" class="note-preview">{{ noteBodyPreview(n) }}</span>
                <span class="meta">
                  <span v-if="n.folder_id && filterFolder !== 'trash'" class="folder-badge">{{
                    folders.find((x) => x.id === n.folder_id)?.name
                  }}</span>
                  <span class="dates dates-compact">
                    <template v-if="filterFolder === 'trash' && n.deleted_at">
                      <span class="meta-prefix">Удал.</span>
                      {{ fmtCompactMsk(n.deleted_at) }}
                    </template>
                    <template v-else>
                      <span class="date-bit"
                        ><span class="meta-prefix">Созд.</span>{{ fmtCompactMsk(n.created_at) }}</span
                      >
                      <span class="date-sep" aria-hidden="true">·</span>
                      <span class="date-bit"
                        ><span class="meta-prefix">Изм.</span>{{ fmtCompactMsk(n.updated_at) }}</span
                      >
                    </template>
                  </span>
                </span>
              </button>
              <div v-if="filterFolder === 'trash'" class="trash-actions">
                <button type="button" class="btn-mini" @click="restoreNote(n, $event)">Восстановить</button>
                <button type="button" class="btn-mini danger" @click="purgeNote(n, $event)">
                  Удалить навсегда
                </button>
              </div>
            </li>
          </ul>
          <p v-if="!loading && sortedNotes.length === 0" class="empty">Заметок пока нет.</p>
        </div>
      </div>

      <div
        class="col-gutter"
        title="Потяните, чтобы изменить ширину списка"
        @mousedown="onGutterDown('list', $event)"
      />

      <div class="editor-shell">
        <NoteEditorColumn :note-id="activeNoteId" @refresh="load" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.workspace {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg);
}
.workspace-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem 1rem;
  padding: 0.5rem 1rem 0.55rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.35);
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  flex-shrink: 0;
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.7) inset;
}
.header-left {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}
.logo {
  margin: 0;
  font-size: 0.9375rem;
  font-weight: 700;
  letter-spacing: -0.03em;
  color: #0f172a;
}
.header-sub {
  font-size: 0.68rem;
  font-weight: 500;
  color: var(--note-list-meta);
  letter-spacing: 0.02em;
  text-transform: lowercase;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.65rem;
  margin-left: auto;
}
.admin-top-btn {
  font-size: 0.72rem;
  font-weight: 600;
  padding: 0.35rem 0.55rem;
  border-radius: 8px;
  border: 1px solid rgba(37, 99, 235, 0.35);
  background: rgba(37, 99, 235, 0.08);
  color: var(--accent);
  cursor: pointer;
}
.admin-top-btn:hover {
  background: rgba(37, 99, 235, 0.14);
}
.search-wrap {
  display: flex;
  align-items: center;
}
.search {
  min-width: 200px;
  max-width: 280px;
  width: 36vw;
  padding: 0.4rem 0.65rem;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.45);
  background: #fff;
  color: #334155;
  font-size: 0.75rem;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}
.search::placeholder {
  color: #94a3b8;
}
.search:hover {
  border-color: rgba(100, 116, 139, 0.45);
}
.search:focus {
  outline: none;
  border-color: rgba(37, 99, 235, 0.4);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}
.action-cluster {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
}
.header-user {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  padding-left: 0.25rem;
  border-left: 1px solid rgba(148, 163, 184, 0.35);
  margin-left: 0.1rem;
}
.user {
  font-size: 0.7rem;
  color: var(--note-list-meta);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.btn {
  padding: 0.35rem 0.6rem;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.4);
  cursor: pointer;
  font-size: 0.72rem;
  font-weight: 500;
  background: #fff;
  color: #475569;
  transition:
    background 0.12s ease,
    border-color 0.12s ease,
    color 0.12s ease;
}
.btn.secondary:hover {
  background: var(--list-row-hover);
  border-color: rgba(100, 116, 139, 0.45);
  color: #334155;
}
.btn.primary {
  background: var(--accent);
  color: #fff;
  border-color: transparent;
  box-shadow: 0 1px 2px rgba(37, 99, 235, 0.22);
}
.btn.primary:hover {
  background: var(--accent-hover);
}
.btn.ghost {
  background: transparent;
  border-color: transparent;
  color: var(--text-muted);
}
.btn.ghost:hover {
  background: rgba(148, 163, 184, 0.12);
  color: #334155;
}
.workspace-body {
  display: flex;
  flex-direction: row;
  flex: 1;
  min-height: 0;
  align-items: stretch;
}
.col-gutter {
  width: 5px;
  flex-shrink: 0;
  cursor: col-resize;
  background: transparent;
  align-self: stretch;
  position: relative;
  z-index: 2;
}
.col-gutter:hover {
  background: rgba(37, 99, 235, 0.12);
}
.folders-aside {
  border-right: 1px solid rgba(148, 163, 184, 0.28);
  background: linear-gradient(190deg, #f1f5f9 0%, #eef2f7 100%);
  padding: 0.65rem 0.55rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-height: 0;
  max-height: calc(100vh - 52px);
  overflow: hidden;
}
.sidebar-panel {
  box-shadow: inset -1px 0 0 rgba(15, 23, 42, 0.06);
}
.aside-title {
  margin: 0;
  font-size: 0.6875rem;
  font-weight: 650;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #64748b;
}
.folder-actions {
  display: flex;
  gap: 0.32rem;
}
.folder-actions input {
  flex: 1;
  min-width: 0;
  padding: 0.3rem 0.42rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  font: inherit;
  font-size: 0.72rem;
  background: var(--panel);
}
.btn-sm {
  padding: 0.28rem 0.44rem;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  font-weight: 600;
  font-size: 0.72rem;
}
.btn-sm.primary {
  background: var(--accent);
  color: #fff;
}
.folder-nav {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  gap: 0;
}
.folder-nav-main {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding-bottom: 0.32rem;
}
.folder-all-row {
  display: flex;
  align-items: stretch;
  gap: 2px;
}
.tag-all-wrap {
  margin-bottom: 3px;
}
.section-chevron {
  flex-shrink: 0;
  width: 1.35rem;
  min-height: 1.75rem;
  border: none;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  font-size: 0.65rem;
  line-height: 1;
  color: #64748b;
  padding: 0;
}
.section-chevron:hover {
  background: rgba(37, 99, 235, 0.1);
  color: var(--accent);
}
.section-chevron-spacer {
  width: 1.35rem;
  flex-shrink: 0;
}
.folder-rows {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.folder-filter-all,
.folder-row .folder-filter.grow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.35rem;
}
.folder-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
}
.folder-nav-v-gutter {
  flex-shrink: 0;
  height: 6px;
  margin: 0 -0.15rem;
  border-radius: 3px;
  cursor: row-resize;
  background: transparent;
}
.folder-nav-v-gutter:hover {
  background: rgba(37, 99, 235, 0.14);
}
.folder-nav-bottom {
  min-height: 0;
}
.folder-nav-tags {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 0.35rem 0 0.4rem;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.tags-aside-title {
  margin: 0 0 0.2rem;
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
}
.tag-filter {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.35rem;
}
.folder-filter.tag-filter.tag-sidebar-row {
  display: flex;
  justify-content: flex-start;
  gap: 0.25rem;
}
.tag-sidebar-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
}
.tag-chevron {
  flex-shrink: 0;
  width: 1.2rem;
  text-align: center;
  font-size: 0.62rem;
  line-height: 1.5;
  color: #64748b;
  border-radius: 4px;
  cursor: pointer;
  user-select: none;
}
.tag-chevron:hover {
  background: rgba(37, 99, 235, 0.12);
  color: var(--accent);
}
.tag-chevron-spacer {
  visibility: hidden;
  pointer-events: none;
}
.tag-filter .tag-count {
  font-weight: 500;
  opacity: 0.72;
  flex-shrink: 0;
  margin-left: auto;
}
.folder-nav-footer {
  flex-shrink: 0;
  margin-top: 0;
  padding-top: 0.4rem;
  border-top: 1px solid var(--border);
}
.folder-filter {
  display: block;
  width: 100%;
  text-align: left;
  padding: 0.36rem 0.5rem;
  border: 1px solid transparent;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.58);
  cursor: pointer;
  font: inherit;
  font-size: 0.72rem;
  color: #475569;
  transition:
    background 0.12s ease,
    border-color 0.12s ease,
    color 0.12s ease;
}
.folder-filter:hover:not(.on) {
  background: rgba(255, 255, 255, 0.92);
  border-color: rgba(148, 163, 184, 0.35);
}
.folder-filter.grow {
  flex: 1;
}
.folder-filter.on {
  background: rgba(255, 255, 255, 0.98);
  border-color: rgba(37, 99, 235, 0.35);
  color: var(--accent);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(37, 99, 235, 0.1);
}
.trash-filter {
  font-size: 0.7rem;
  background: rgba(255, 255, 255, 0.4);
}
.trash-filter.on {
  color: var(--danger);
  border-color: rgba(220, 38, 38, 0.3);
  background: rgba(254, 226, 226, 0.55);
  font-weight: 600;
}
.btn-rename {
  flex-shrink: 0;
  width: 1.55rem;
  height: 1.55rem;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 0.8rem;
  line-height: 1;
}
.btn-rename:hover {
  color: var(--accent);
  background: var(--bg);
}
.folder-row {
  display: flex;
  align-items: center;
  gap: 2px;
}
.btn-del {
  flex-shrink: 0;
  width: 1.55rem;
  height: 1.55rem;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
}
.btn-del:hover {
  color: var(--danger);
  background: var(--bg);
}

.notes-list-col {
  border-right: 1px solid rgba(148, 163, 184, 0.28);
  background: linear-gradient(180deg, #fafbfc 0%, #f4f5f8 100%);
  display: flex;
  flex-direction: column;
  min-height: 0;
  max-height: calc(100vh - 52px);
}
.list-toolbar {
  padding: 0.5rem 0.6rem 0.45rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.25);
  display: flex;
  flex-direction: column;
  gap: 0.32rem;
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.45);
}
.sort-lab {
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
}
.sort-select {
  width: 100%;
  padding: 0.34rem 0.5rem;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.4);
  font: inherit;
  font-size: 0.7rem;
  background: #fff;
  color: #475569;
}
.list-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 0.35rem 0.45rem 0.75rem;
}
.load-hint {
  margin: 0.35rem 0;
  font-size: 0.78rem;
}
.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.list--refreshing {
  opacity: 0.72;
  pointer-events: none;
  transition: opacity 0.15s ease;
}
.list li.trashrow {
  display: flex;
  flex-direction: column;
  gap: 0.32rem;
}
.note-item {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  width: 100%;
  text-align: left;
  padding: 0.32rem 0.45rem 0.36rem;
  border-radius: 10px;
  border: 1px solid transparent;
  background: rgba(255, 255, 255, 0.65);
  cursor: pointer;
  font: inherit;
  color: inherit;
  transition:
    border-color 0.14s ease,
    background 0.14s ease,
    box-shadow 0.14s ease;
}
.note-item:hover {
  background: #fff;
  border-color: rgba(148, 163, 184, 0.35);
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
}
.note-item.current {
  border-color: rgba(37, 99, 235, 0.38);
  background: var(--list-row-active);
  box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.08);
}
.trash-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.32rem;
  padding: 0 0.15rem;
}
.btn-mini {
  font-size: 0.72rem;
  padding: 0.22rem 0.45rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--panel);
  cursor: pointer;
  color: inherit;
}
.btn-mini.danger {
  border-color: var(--danger);
  color: var(--danger);
}
.dates {
  display: inline-flex;
  align-items: center;
  gap: 0.28rem;
  flex-wrap: wrap;
  font-size: 0.625rem;
  line-height: 1.35;
  font-weight: 450;
  font-variant-numeric: tabular-nums;
  color: var(--note-list-meta);
  letter-spacing: 0.01em;
}
.dates-compact {
  font-size: 0.5625rem;
  line-height: 1.3;
  gap: 0.18rem;
}
.dates-compact .meta-prefix {
  margin-right: 0.12rem;
}
.date-sep {
  opacity: 0.45;
  user-select: none;
}
.meta-prefix {
  font-size: 0.58rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #cbd5e1;
}
.dates-compact .meta-prefix {
  font-size: 0.5rem;
}
.note-title {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-weight: 500;
  font-size: 0.7rem;
  line-height: 1.35;
  letter-spacing: -0.01em;
  margin-bottom: 0.12rem;
  color: var(--note-list-title);
}
.note-preview {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 0.6rem;
  line-height: 1.32;
  color: #94a3b8;
  margin-bottom: 0.14rem;
}
.note-item.current .note-title {
  color: var(--note-list-title-active);
  font-weight: 560;
}
.meta {
  font-size: 0.5625rem;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.12rem;
}
.folder-badge {
  font-size: 0.58rem;
  font-weight: 500;
  padding: 0.08rem 0.35rem;
  border-radius: 999px;
  background: rgba(241, 245, 249, 0.95);
  border: 1px solid rgba(148, 163, 184, 0.28);
  color: #64748b;
}
.err {
  color: var(--danger);
  font-size: 0.75rem;
}
.empty {
  font-size: 0.72rem;
  color: var(--note-list-meta);
  margin: 1.25rem 0;
  text-align: center;
  line-height: 1.5;
}
.editor-shell {
  flex: 1;
  min-width: 180px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  max-height: calc(100vh - 52px);
}
</style>
