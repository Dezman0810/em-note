<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import NoteEditorColumn from '../components/NoteEditorColumn.vue'
import AdminUsersModal from '../components/AdminUsersModal.vue'
import ReminderCalendar from '../components/ReminderCalendar.vue'
import { errMessage, foldersApi, notesApi, tagsApi } from '../api/client'
import type { Folder, FolderNoteCounts, Note, Tag } from '../api/types'
import { useAuthStore } from '../stores/auth'
import { fmtCompactMsk, fmtMsk } from '../utils/datetime'
import { foldersSortedAlphabetical } from '../utils/folders'
import { DEFAULT_NOTE_TITLE } from '../utils/noteDefaults'
import { isStrictDescendantOf, tagsWithChildrenSet, visibleTagsForNav } from '../utils/tagsTree'

const adminUsersOpen = ref(false)

/** Узкий экран: телефон / узкий планшет — отдельный расклад и выдвижная панель папок. */
const MOBILE_LAYOUT_MQ = '(max-width: 768px)'
const isNarrowLayout = ref(false)
const mobileNavOpen = ref(false)
let mobileMq: MediaQueryList | null = null

function syncNarrowLayout() {
  if (typeof window === 'undefined') return
  isNarrowLayout.value = window.matchMedia(MOBILE_LAYOUT_MQ).matches
}

const COL_FOLDER_KEY = 'note-ui-w-folder'
const TAG_NAV_COLLAPSED_KEY = 'note-ui-tag-collapsed'
const COL_LIST_KEY = 'note-ui-w-list'
const FOLDER_NAV_MAIN_H_KEY = 'note-ui-folder-main-h'
const TAGS_PANEL_H_KEY = 'note-ui-tags-panel-h'
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

type GutterDrag = null | 'folder' | 'list' | 'folderNavV' | 'tagsCalendar'
const gutterDrag = ref<GutterDrag>(null)
let gutterStartX = 0
let gutterStartFolder = 0
let gutterStartList = 0
let gutterStartY = 0
let gutterStartFolderMainH = 0
let gutterStartTagsPanelH = 0

const folderNavRef = ref<HTMLElement | null>(null)
const folderNavMainPx = ref(
  readColW(FOLDER_NAV_MAIN_H_KEY, 200, 72, 560)
)
/** Высота блока меток (рамка: фильтры + список); календарь ниже. */
const tagsPanelHeightPx = ref(readColW(TAGS_PANEL_H_KEY, 200, 96, 520))

function persistColWidths() {
  try {
    localStorage.setItem(COL_FOLDER_KEY, String(colFolderPx.value))
    localStorage.setItem(COL_LIST_KEY, String(colListPx.value))
    localStorage.setItem(FOLDER_NAV_MAIN_H_KEY, String(folderNavMainPx.value))
    localStorage.setItem(TAGS_PANEL_H_KEY, String(tagsPanelHeightPx.value))
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
  const minBottom = 160
  return Math.max(72, nav.clientHeight - minBottom - GUTTER)
}

/** Макс. высота блока меток: оставляем место календарю и корзине. */
function tagsPanelHeightMax(): number {
  const nav = folderNavRef.value
  if (!nav) return 520
  const bottom = nav.querySelector('.folder-nav-bottom') as HTMLElement | null
  if (!bottom) return 520
  const footer = bottom.querySelector('.folder-nav-footer') as HTMLElement | null
  const fh = footer ? footer.offsetHeight + 8 : 48
  const g = 6
  const calMin = 100
  return Math.max(96, bottom.clientHeight - fh - calMin - g - 4)
}

function clampTagsPanelHeight() {
  const maxH = tagsPanelHeightMax()
  tagsPanelHeightPx.value = Math.min(maxH, Math.max(96, tagsPanelHeightPx.value))
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

function onTagsCalendarGutterDown(e: MouseEvent) {
  e.preventDefault()
  gutterDrag.value = 'tagsCalendar'
  gutterStartY = e.clientY
  gutterStartTagsPanelH = tagsPanelHeightPx.value
  document.body.style.cursor = 'row-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('mousemove', onGutterMove)
  window.addEventListener('mouseup', onGutterUp)
}

function onGutterMove(e: MouseEvent) {
  if (!gutterDrag.value) return
  if (gutterDrag.value === 'tagsCalendar') {
    const dy = e.clientY - gutterStartY
    const maxH = tagsPanelHeightMax()
    tagsPanelHeightPx.value = Math.min(maxH, Math.max(96, gutterStartTagsPanelH + dy))
    return
  }
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
    clampTagsPanelHeight()
  }
  if (was === 'tagsCalendar') {
    const maxH = tagsPanelHeightMax()
    tagsPanelHeightPx.value = Math.min(maxH, Math.max(96, tagsPanelHeightPx.value))
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

/** Корзина — отдельный режим; иначе смотрим filterFolderIds. */
const folderViewTrash = ref(false)
/** Пустой список при folderViewTrash === false — все папки. Ctrl/Cmd+клик — несколько папок (ИЛИ). */
const filterFolderIds = ref<string[]>([])
/** Пустой список — без фильтра по меткам. Ctrl/Cmd+клик добавляет метку к фильтру (ИЛИ). */
const filterTagIds = ref<string[]>([])

const isAllFoldersScope = computed(
  () => !folderViewTrash.value && filterFolderIds.value.length === 0
)
const tags = ref<Tag[]>([])
const tagCountById = ref<Record<string, number>>({})
const folderNoteCounts = ref<FolderNoteCounts | null>(null)
const foldersListExpanded = ref(readBoolKey(FOLDERS_LIST_EXPANDED_KEY, true))
const tagsListExpanded = ref(readBoolKey(TAGS_LIST_EXPANDED_KEY, true))
/** Увеличивается после load — обновляет данные календаря напоминаний. */
const reminderRefreshSignal = ref(0)
/** Синхронизация открытой заметки в редакторе при изменениях из списка (DnD метки, папки и т.д.). */
const editorSyncSignal = ref(0)

const MIME_NOTE_ID = 'application/x-em-note-id'
const MIME_TAG_ID = 'application/x-em-note-tag-id'

function onNoteDragStart(e: DragEvent, noteId: string) {
  if (folderViewTrash.value) return
  e.dataTransfer?.setData(MIME_NOTE_ID, noteId)
  e.dataTransfer!.effectAllowed = 'move'
}

function onFolderDragOver(e: DragEvent) {
  const types = e.dataTransfer?.types ? [...e.dataTransfer.types] : []
  if (!types.includes(MIME_NOTE_ID)) return
  e.preventDefault()
  e.dataTransfer!.dropEffect = 'move'
}

async function onFolderDrop(e: DragEvent, folderKey: string) {
  e.preventDefault()
  const noteId = e.dataTransfer?.getData(MIME_NOTE_ID)
  if (!noteId) return
  const targetFolder: string | null = folderKey === 'all' ? null : folderKey
  const cur = notes.value.find((x) => x.id === noteId)
  if (cur && (cur.folder_id ?? null) === targetFolder) return
  try {
    await notesApi.update(noteId, { folder_id: targetFolder })
    error.value = ''
    await loadFolders()
    await load()
    bumpEditorSyncIfOpen(noteId)
  } catch (err) {
    error.value = errMessage(err)
  }
}

function onTagDragStart(e: DragEvent, tagId: string) {
  e.dataTransfer?.setData(MIME_TAG_ID, tagId)
  e.dataTransfer!.effectAllowed = 'copy'
}

function onNoteRowDragOver(e: DragEvent) {
  const types = e.dataTransfer?.types ? [...e.dataTransfer.types] : []
  if (!types.includes(MIME_TAG_ID)) return
  e.preventDefault()
  e.dataTransfer!.dropEffect = 'copy'
}

async function onNoteRowDrop(e: DragEvent, noteId: string) {
  e.preventDefault()
  const tagId = e.dataTransfer?.getData(MIME_TAG_ID)
  if (!tagId) return
  try {
    await notesApi.attachTag(noteId, tagId)
    error.value = ''
    await load()
    reminderRefreshSignal.value++
    bumpEditorSyncIfOpen(noteId)
  } catch (err) {
    error.value = errMessage(err)
  }
}

const folderNavMainStyle = computed(() => ({
  flex: '0 0 auto',
  height: `${folderNavMainPx.value}px`,
  minHeight: '72px',
  overflow: 'hidden',
  display: 'flex',
  flexDirection: 'column' as const,
}))

const folderNavBottomStyle = computed(() => ({
  flex: '1 1 auto',
  minHeight: '0',
  display: 'flex',
  flexDirection: 'column' as const,
}))

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
  if (willCollapse && filterTagIds.value.length) {
    filterTagIds.value = filterTagIds.value.filter(
      (id) => !isStrictDescendantOf(tags.value, tagId, id)
    )
  }
}

function clearTagFilter() {
  filterTagIds.value = []
}

function onSidebarTagClick(t: Tag, e: MouseEvent) {
  const id = t.id
  if (e.ctrlKey || e.metaKey) {
    const cur = [...filterTagIds.value]
    const i = cur.indexOf(id)
    if (i >= 0) cur.splice(i, 1)
    else cur.push(id)
    filterTagIds.value = cur
  } else {
    filterTagIds.value = [id]
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
  if (folderViewTrash.value || isAllFoldersScope.value) {
    return folderNoteCounts.value.total
  }
  const ids = filterFolderIds.value
  if (ids.length === 1) return countInFolder(ids[0]!)
  return ids.reduce((s, id) => s + countInFolder(id), 0)
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

const noteRouteOpen = computed(() => !!activeNoteId.value)

watch(isNarrowLayout, (narrow) => {
  if (!narrow) mobileNavOpen.value = false
})

watch(activeNoteId, () => {
  mobileNavOpen.value = false
})

function bumpEditorSyncIfOpen(noteId: string) {
  if (noteId === activeNoteId.value) editorSyncSignal.value++
}

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
    const list = await foldersApi.list()
    folders.value = [...list]
  } catch (e) {
    error.value = errMessage(e)
  }
}

function folderListParams(): { folder_id?: string | string[] } {
  if (folderViewTrash.value) return {}
  const ids = filterFolderIds.value
  if (!ids.length) return {}
  return ids.length === 1 ? { folder_id: ids[0]! } : { folder_id: [...ids] }
}

function clearFolderPicker() {
  folderViewTrash.value = false
  filterFolderIds.value = []
}

function openTrashFolder() {
  folderViewTrash.value = true
  filterFolderIds.value = []
}

function onSidebarFolderClick(f: Folder, e: MouseEvent) {
  if (folderViewTrash.value) folderViewTrash.value = false
  const id = f.id
  if (e.ctrlKey || e.metaKey) {
    const cur = [...filterFolderIds.value]
    const i = cur.indexOf(id)
    if (i >= 0) cur.splice(i, 1)
    else cur.push(id)
    filterFolderIds.value = cur
  } else {
    filterFolderIds.value = [id]
  }
}

function tagFilterParams(): { tag_id?: string | string[] } {
  const ids = filterTagIds.value
  if (!ids.length) return {}
  return ids.length === 1 ? { tag_id: ids[0]! } : { tag_id: [...ids] }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    if (folderViewTrash.value) {
      notes.value = await notesApi.listTrash()
      try {
        const [tagList, counts] = await Promise.all([
          tagsApi.list(),
          tagsApi.noteCounts(undefined),
        ])
        tags.value = Array.isArray(tagList) ? [...tagList] : []
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
      }
      void loadFolderCounts()
      reminderRefreshSignal.value++
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
      !folderViewTrash.value && filterFolderIds.value.length
        ? filterFolderIds.value.length === 1
          ? { folder_id: filterFolderIds.value[0]! }
          : { folder_id: [...filterFolderIds.value] }
        : undefined
    try {
      const [tagList, counts] = await Promise.all([
        tagsApi.list(),
        tagsApi.noteCounts(countsParams),
      ])
      tags.value = Array.isArray(tagList) ? [...tagList] : []
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
    if (folderViewTrash.value) {
      notes.value = []
    }
  } finally {
    loading.value = false
  }
  void loadFolderCounts()
  reminderRefreshSignal.value++
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
    filterFolderIds.value = filterFolderIds.value.filter((x) => x !== f.id)
    error.value = ''
    try {
      const list = await foldersApi.list()
      /* если GET закэширован и вернул старую папку — всё равно убираем удалённую */
      folders.value = list.filter((x) => x.id !== f.id)
    } catch {
      folders.value = folders.value.filter((x) => x.id !== f.id)
    }
    await nextTick()
    await load()
  } catch (e) {
    error.value = errMessage(e)
    await loadFolders()
  }
}

async function renameFolder(f: Folder) {
  const name = prompt('Новое имя папки', f.name)
  if (!name || !name.trim()) return
  try {
    const updated = await foldersApi.update(f.id, { name: name.trim() })
    error.value = ''
    folders.value = folders.value.map((x) => (x.id === updated.id ? updated : x))
    await nextTick()
    await load()
  } catch (e) {
    error.value = errMessage(e)
    await loadFolders()
  }
}

function tagRenameTakenByOther(raw: string, excludeTagId: string): boolean {
  const n = raw.trim().toLowerCase()
  if (!n) return false
  return tags.value.some(
    (x) => x.id !== excludeTagId && x.name.trim().toLowerCase() === n
  )
}

async function renameTag(t: Tag) {
  const name = prompt('Новое имя метки', t.name)
  if (name == null) return
  const trimmed = name.trim()
  if (!trimmed) return
  if (trimmed === t.name) return
  if (tagRenameTakenByOther(trimmed, t.id)) {
    error.value = 'Метка с таким именем уже существует'
    return
  }
  try {
    error.value = ''
    const updated = await tagsApi.update(t.id, { name: trimmed })
    tags.value = tags.value.map((x) => (x.id === updated.id ? updated : x))
    await load()
  } catch (e) {
    error.value = errMessage(e)
    await load()
  }
}

async function removeTag(t: Tag) {
  if (!confirm(`Удалить метку «${t.name}»? Дочерние станут на ступень выше.`)) return
  const removedId = t.id
  const promoteTo = t.parent_id
  try {
    await tagsApi.remove(removedId)
    filterTagIds.value = filterTagIds.value.filter((x) => x !== removedId)
    error.value = ''
    tags.value = tags.value
      .filter((x) => x.id !== removedId)
      .map((x) => (x.parent_id === removedId ? { ...x, parent_id: promoteTo } : x))
    await load()
  } catch (e) {
    error.value = errMessage(e)
    await load()
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
  if (!confirm(`Удалить «${n.title || DEFAULT_NOTE_TITLE}» навсегда?`)) return
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
    if (folderViewTrash.value) {
      error.value = 'Создайте заметку вне корзины'
      return
    }
    const folder_id =
      filterFolderIds.value.length === 1 ? filterFolderIds.value[0]! : undefined
    const n = await notesApi.create({
      title: DEFAULT_NOTE_TITLE,
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
  syncNarrowLayout()
  mobileMq = window.matchMedia(MOBILE_LAYOUT_MQ)
  mobileMq.addEventListener('change', syncNarrowLayout)

  await loadFolders()
  await load()
  await nextTick()
  clampTagsPanelHeight()
  window.addEventListener('resize', clampTagsPanelHeight)
})

watch(folderViewTrash, (trash) => {
  if (trash) filterTagIds.value = []
  void load()
})
watch(
  filterFolderIds,
  () => {
    if (folderViewTrash.value && filterFolderIds.value.length) {
      folderViewTrash.value = false
    }
    void load()
  },
  { deep: true }
)
watch(
  filterTagIds,
  () => {
    if (folderViewTrash.value) {
      if (filterTagIds.value.length) {
        folderViewTrash.value = false
        filterFolderIds.value = []
        void load()
      }
      return
    }
    void load()
  },
  { deep: true }
)

onBeforeUnmount(() => {
  mobileMq?.removeEventListener('change', syncNarrowLayout)
  mobileMq = null
  window.removeEventListener('resize', clampTagsPanelHeight)
  window.removeEventListener('mousemove', onGutterMove)
  window.removeEventListener('mouseup', onGutterUp)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
})
</script>

<template>
  <div
    class="workspace"
    :class="{
      'workspace--narrow': isNarrowLayout,
      'workspace--note-route': noteRouteOpen,
    }"
  >
    <div
      v-if="isNarrowLayout && mobileNavOpen"
      class="mobile-nav-backdrop"
      aria-hidden="true"
      @click="mobileNavOpen = false"
    />
    <header class="workspace-header">
      <div class="header-left">
        <button
          v-if="isNarrowLayout"
          type="button"
          class="btn header-menu-btn"
          aria-label="Папки, метки и календарь"
          title="Папки и метки"
          @click="mobileNavOpen = !mobileNavOpen"
        >
          ☰
        </button>
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
        :class="{ 'folders-aside--drawer-open': isNarrowLayout && mobileNavOpen }"
        :style="
          isNarrowLayout
            ? {}
            : { width: colFolderPx + 'px', flexShrink: 0 }
        "
      >
        <nav ref="folderNavRef" class="folder-nav">
          <div class="folder-nav-main" :style="folderNavMainStyle">
            <div class="folder-nav-folders-panel">
              <div class="folder-nav-folders-sticky">
                <div class="folder-new-row">
                  <input
                    v-model="newFolderName"
                    type="text"
                    placeholder="Новая папка…"
                    aria-label="Имя новой папки"
                    @keyup.enter="createFolder"
                  />
                  <button type="button" class="btn-sm primary" title="Создать папку" @click="createFolder">+</button>
                </div>
                <div class="folder-all-row tag-all-wrap folder-all-row--frame">
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
                    :class="{ on: isAllFoldersScope }"
                    @click="clearFolderPicker"
                    @dragover="onFolderDragOver"
                    @drop="onFolderDrop($event, 'all')"
                  >
                    <span class="folder-label nav-scope-label">Все заметки</span>
                    <span v-if="folderNoteCounts" class="tag-count">({{ folderNoteCounts.total }})</span>
                  </button>
                </div>
              </div>
              <div class="folder-nav-folders-scroll">
                <div v-show="foldersListExpanded" class="folder-rows">
                  <div
                    v-for="f in foldersSorted"
                    :key="f.id"
                    class="nav-row"
                    :class="{ on: filterFolderIds.includes(f.id) }"
                    @dragover="onFolderDragOver"
                    @drop="onFolderDrop($event, f.id)"
                  >
                    <button
                      type="button"
                      class="nav-row-label"
                      title="Ctrl или ⌘ + клик — выбрать несколько папок"
                      @click="onSidebarFolderClick(f, $event)"
                    >
                      <span class="folder-label">{{ f.name }}</span>
                    </button>
                    <div class="nav-row-actions">
                      <button
                        type="button"
                        class="btn-rename"
                        title="Переименовать"
                        @click.stop="renameFolder(f)"
                      >
                        ✎
                      </button>
                      <button
                        type="button"
                        class="btn-del"
                        title="Удалить папку"
                        @click.stop="deleteFolder(f)"
                      >
                        ×
                      </button>
                    </div>
                    <span class="tag-count">({{ countInFolder(f.id) }})</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div
            class="folder-nav-v-gutter"
            title="Потяните: больше места для папок или для меток"
            @mousedown="onFolderNavVGutterDown($event)"
          />
          <div class="folder-nav-bottom" :style="folderNavBottomStyle">
            <div class="folder-nav-tags-panel" :style="{ height: tagsPanelHeightPx + 'px' }">
                <div class="folder-nav-tags-sticky">
                  <div class="folder-all-row tag-all-wrap folder-all-row--frame">
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
                      :class="{ on: !filterTagIds.length }"
                      @click="clearTagFilter"
                    >
                      <span class="folder-label nav-scope-label">Все метки</span>
                      <span v-if="folderNoteCounts" class="tag-count">({{ scopeNoteTotal }})</span>
                    </button>
                  </div>
                </div>
                <div class="folder-nav-tags-scroll">
                  <div
                    v-for="t in tagsVisibleInSidebar"
                    v-show="tagsListExpanded"
                    :key="t.id"
                    class="nav-row tag-sidebar-row"
                    :class="{ on: filterTagIds.includes(t.id) }"
                    :style="{ paddingLeft: (0.35 + Math.max(0, t.depth - 1) * 0.55) + 'rem' }"
                    draggable="true"
                    @dragstart="onTagDragStart($event, t.id)"
                  >
                    <button
                      type="button"
                      class="nav-row-label nav-row-label--tag"
                      title="Ctrl или ⌘ + клик — выбрать несколько меток"
                      @click="onSidebarTagClick(t, $event)"
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
                    </button>
                    <div class="nav-row-actions">
                      <button type="button" class="btn-rename" title="Переименовать" @click.stop="renameTag(t)">
                        ✎
                      </button>
                      <button type="button" class="btn-del" title="Удалить метку" @click.stop="removeTag(t)">
                        ×
                      </button>
                    </div>
                    <span class="tag-count">({{ tagCountById[t.id] ?? 0 }})</span>
                  </div>
                </div>
              </div>
              <div
                class="folder-nav-tags-cal-gutter"
                title="Потяните вниз — меньше меток и больше календарь; вверх — больше меток"
                @mousedown="onTagsCalendarGutterDown($event)"
              />
              <div class="folder-nav-calendar-wrap">
                <ReminderCalendar :refresh-signal="reminderRefreshSignal" @open-note="openNote" />
              </div>
            <div class="folder-nav-footer">
              <button
                type="button"
                class="folder-filter trash-filter"
                :class="{ on: folderViewTrash }"
                @click="openTrashFolder"
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
            <li v-for="n in sortedNotes" :key="n.id" :class="{ trashrow: folderViewTrash }">
              <button
                type="button"
                class="note-item"
                :class="{ current: n.id === activeNoteId }"
                :title="noteRowTitle(n)"
                :draggable="!folderViewTrash"
                @dragstart="onNoteDragStart($event, n.id)"
                @dragover="onNoteRowDragOver"
                @drop="onNoteRowDrop($event, n.id)"
                @click="openNote(n.id)"
              >
                <span class="note-title">{{ n.title || DEFAULT_NOTE_TITLE }}</span>
                <span v-if="noteBodyPreview(n)" class="note-preview">{{ noteBodyPreview(n) }}</span>
                <span class="meta">
                  <span v-if="n.folder_id && !folderViewTrash" class="folder-badge">{{
                    folders.find((x) => x.id === n.folder_id)?.name
                  }}</span>
                  <span class="dates dates-compact">
                    <template v-if="folderViewTrash && n.deleted_at">
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
              <div v-if="folderViewTrash" class="trash-actions">
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
        <NoteEditorColumn
          :note-id="activeNoteId"
          :editor-sync-signal="editorSyncSignal"
          @refresh="load"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.workspace {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  background: var(--bg);
}
.mobile-nav-backdrop {
  position: fixed;
  inset: 0;
  z-index: 180;
  background: rgba(15, 23, 42, 0.42);
  -webkit-tap-highlight-color: transparent;
}
.header-menu-btn {
  padding: 0.32rem 0.5rem;
  margin-right: 0.15rem;
  font-size: 1rem;
  line-height: 1;
  background: #fff;
  border: 1px solid rgba(148, 163, 184, 0.45);
  border-radius: 10px;
  cursor: pointer;
  flex-shrink: 0;
  color: #334155;
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
  background: rgba(15, 23, 42, 0.06);
}
.folders-aside {
  border-right: 1px solid var(--sidebar-edge);
  background: var(--sidebar-bg);
  padding: 0.65rem 0.55rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-height: 0;
  max-height: calc(100vh - 52px);
  overflow: hidden;
  font-family: system-ui, -apple-system, 'Segoe UI', 'Inter', Roboto, sans-serif;
  color: #1f2937;
}
.sidebar-panel {
  box-shadow: inset -1px 0 0 rgba(15, 23, 42, 0.04);
}
.folder-new-row {
  display: flex;
  gap: 0.32rem;
  align-items: center;
  margin-bottom: 0.35rem;
}
.folder-new-row input {
  flex: 1;
  min-width: 0;
  padding: 0.28rem 0.4rem;
  border-radius: 8px;
  border: 1px solid #d1d5db;
  font: inherit;
  font-size: 0.7rem;
  background: #fff;
  color: #1f2937;
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
  gap: 0;
  padding-bottom: 0;
  min-height: 0;
}
.folder-all-row {
  display: flex;
  align-items: stretch;
  gap: 2px;
}
.folder-all-row--frame {
  border: 1px solid var(--sidebar-edge);
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
  align-items: stretch;
}
.folder-all-row--frame .section-chevron {
  border-radius: 0;
  align-self: stretch;
}
.folder-all-row--frame .folder-filter-all {
  border: none !important;
  background: transparent !important;
  border-radius: 0;
  box-shadow: none !important;
}
.folder-all-row--frame .folder-filter-all.on {
  border-radius: 0;
}
.nav-scope-label {
  font-weight: 600;
  font-size: 0.76rem;
  letter-spacing: -0.02em;
  color: #111827;
}
.folder-filter-all.on .nav-scope-label {
  color: #111827;
}
.tag-all-wrap {
  margin-bottom: 3px;
}
.folder-nav-tags-cal-gutter {
  flex-shrink: 0;
  height: 6px;
  margin: 0 -0.15rem;
  border-radius: 3px;
  cursor: row-resize;
  background: transparent;
}
.folder-nav-calendar-wrap {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding-top: 2px;
}
.folder-nav-tags-panel,
.folder-nav-folders-panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fafbfc;
  box-shadow: none;
}
.folder-nav-tags-panel {
  flex: 0 0 auto;
}
.folder-nav-folders-panel {
  flex: 1 1 auto;
}
.folder-nav-tags-sticky,
.folder-nav-folders-sticky {
  flex-shrink: 0;
  padding: 0.35rem 0.4rem 0.25rem;
  border-bottom: 1px solid #eceef2;
  background: transparent;
  border-radius: 8px 8px 0 0;
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
  background: var(--sidebar-hover);
  color: #374151;
}
.section-chevron-spacer {
  width: 1.35rem;
  flex-shrink: 0;
}
.folder-nav-folders-panel .folder-filter {
  font-size: 0.78rem;
}
.folder-nav-folders-panel .folder-filter .tag-count {
  font-size: 0.62rem;
  font-weight: 500;
  line-height: 1.2;
}
.folder-rows {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.folder-filter-all {
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
.folder-nav-bottom {
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.folder-nav-tags-scroll,
.folder-nav-folders-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0.25rem 0.35rem 0.3rem;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.folder-nav-tags-panel .folder-filter .tag-count {
  font-size: 0.62rem;
  font-weight: 500;
  line-height: 1.2;
}
.tag-filter {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.35rem;
}
.nav-row.tag-sidebar-row .nav-row-label--tag {
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
  background: var(--sidebar-hover);
  color: #374151;
}
.tag-chevron-spacer {
  visibility: hidden;
  pointer-events: none;
}
.nav-row .tag-count {
  font-size: 0.62rem;
  font-weight: 500;
  opacity: 0.72;
  flex-shrink: 0;
  line-height: 1.2;
}
.folder-nav-footer {
  flex-shrink: 0;
  margin-top: auto;
  padding-top: 0.4rem;
  border-top: 1px solid #e5e7eb;
}
.folder-filter {
  display: block;
  width: 100%;
  text-align: left;
  padding: 0.36rem 0.5rem;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  font: inherit;
  font-size: 0.72rem;
  color: #374151;
  transition:
    background 0.12s ease,
    border-color 0.12s ease,
    color 0.12s ease;
}
.folder-filter:hover:not(.on) {
  background: var(--sidebar-hover);
  border-color: transparent;
}
.folder-filter.grow {
  flex: 1;
}
.folder-filter.on {
  background: var(--sidebar-active);
  border-color: transparent;
  color: #111827;
  font-weight: 600;
  box-shadow: none;
}
.trash-filter {
  font-size: 0.7rem;
  background: transparent;
  color: #4b5563;
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
  background: var(--sidebar-hover);
}
.nav-row {
  display: flex;
  align-items: center;
  gap: 0.2rem;
  width: 100%;
  box-sizing: border-box;
  padding: 0.32rem 0.45rem;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  cursor: default;
  transition:
    background 0.12s ease,
    border-color 0.12s ease;
}
.nav-row:hover:not(.on) {
  background: var(--sidebar-hover);
  border-color: transparent;
}
.nav-row.on {
  background: var(--sidebar-active);
  border-color: transparent;
  box-shadow: none;
}
.nav-row.on .tag-count {
  color: #6b7280;
  font-weight: 600;
  font-size: 0.62rem;
  opacity: 1;
}
.nav-row.on .folder-label,
.nav-row.on .tag-sidebar-name {
  color: #111827;
  font-weight: 600;
}
.nav-row-label {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  align-items: center;
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 0;
  margin: 0;
  font: inherit;
  font-size: 0.72rem;
  color: #374151;
  text-align: left;
}
/* Папки: чуть крупнее текст строки (+~1 pt к базовому 0.72rem) */
.nav-row:not(.tag-sidebar-row) .nav-row-label {
  font-size: 0.78rem;
}
.nav-row-label:focus-visible {
  outline: 2px solid rgba(37, 99, 235, 0.45);
  outline-offset: 2px;
  border-radius: 6px;
}
.nav-row-actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  gap: 2px;
}
@media (hover: hover) {
  .nav-row .nav-row-actions {
    opacity: 0;
    transition: opacity 0.12s ease;
  }
  .nav-row:hover .nav-row-actions,
  .nav-row:focus-within .nav-row-actions {
    opacity: 1;
  }
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
  background: var(--sidebar-hover);
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

.workspace--narrow .workspace-header {
  padding-left: max(0.5rem, env(safe-area-inset-left, 0px));
  padding-right: max(0.65rem, env(safe-area-inset-right, 0px));
  padding-top: max(0.5rem, env(safe-area-inset-top, 0px));
}
.workspace--narrow .actions {
  flex-wrap: nowrap;
  margin-left: auto;
  gap: 0.35rem;
  min-width: 0;
}
.workspace--narrow .search-wrap {
  flex: 1;
  min-width: 0;
}
.workspace--narrow .search {
  min-width: 0;
  width: 100%;
  max-width: none;
}
.workspace--narrow .header-user .user {
  display: none;
}
.workspace--narrow .header-user {
  border-left: none;
  margin-left: 0;
  padding-left: 0;
  flex-shrink: 0;
}
.workspace--narrow .folders-aside {
  position: fixed;
  top: 0;
  bottom: 0;
  left: 0;
  width: min(20rem, 88vw);
  max-width: 360px;
  max-height: none;
  z-index: 200;
  transform: translateX(-100%);
  transition: transform 0.22s ease;
  padding-top: calc(0.65rem + env(safe-area-inset-top, 0px));
  padding-bottom: env(safe-area-inset-bottom, 0px);
  box-shadow: 4px 0 28px rgba(15, 23, 42, 0.18);
}
.workspace--narrow .folders-aside.folders-aside--drawer-open {
  transform: translateX(0);
}
.workspace--narrow .col-gutter {
  display: none;
}
.workspace--narrow .notes-list-col {
  width: 100% !important;
  flex: 1 1 auto;
  max-height: none;
  min-height: 0;
}
.workspace--narrow.workspace--note-route .notes-list-col {
  display: none;
}
.workspace--narrow:not(.workspace--note-route) .editor-shell {
  display: none;
}
.workspace--narrow.workspace--note-route .editor-shell {
  flex: 1 1 auto;
  width: 100%;
  min-width: 0;
  max-height: none;
  min-height: calc(
    100dvh - 52px - env(safe-area-inset-top, 0px) - env(safe-area-inset-bottom, 0px)
  );
}
.workspace--narrow .workspace-body {
  flex: 1;
  min-height: 0;
}
</style>
