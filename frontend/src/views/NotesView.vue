<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import NoteEditorColumn from '../components/NoteEditorColumn.vue'
import AdminUsersModal from '../components/AdminUsersModal.vue'
import ReminderCalendar from '../components/ReminderCalendar.vue'
import { errMessage, foldersApi, noteFilterPresetsApi, notesApi, tagsApi, type TagsNoteCountsParams } from '../api/client'
import {
  MIME_TAG_ID,
  MIME_TAG_IDS_JSON,
  isTagAttachDragTypes,
  readDroppedTagIds,
} from '../utils/dndTags'
import type { Folder, FolderNoteCounts, Note, NoteFilterPreset, Tag } from '../api/types'
import { useAuthStore } from '../stores/auth'
import { fmtCompactMsk, fmtMsk } from '../utils/datetime'
import { foldersSortedAlphabetical } from '../utils/folders'
import { DEFAULT_NOTE_TITLE } from '../utils/noteDefaults'
import { isDescendantTag, tagsWithChildrenSet, visibleTagsForNav } from '../utils/tagsTree'

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
/** В сайдбаре скрывать метки с нулём заметок в текущей области (все папки или выбранные). */
const TAGS_ONLY_WITH_NOTES_IN_SCOPE_KEY = 'note-ui-tags-only-with-notes-in-scope'
const CALENDAR_EXPANDED_KEY = 'note-ui-calendar-expanded'
/** Свёрнуто всё меню слева (папки, метки, календарь) — узкая колонка с «+». */
const SIDEBAR_NAV_FULL_COLLAPSE_KEY = 'note-ui-sidebar-nav-full-collapsed'
const RAIL_ASIDE_WIDTH_PX = 40
/** Средняя колонка «список заметок» свернута в узкую полосу с «+». */
const NOTES_LIST_COL_FULL_COLLAPSE_KEY = 'note-ui-notes-list-col-collapsed'

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

const colFolderPx = ref(readColW(COL_FOLDER_KEY, 200, 120, 420))
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
const calendarListExpanded = ref(readBoolKey(CALENDAR_EXPANDED_KEY, true))
const sidebarNavFullyCollapsed = ref(readBoolKey(SIDEBAR_NAV_FULL_COLLAPSE_KEY, false))

const showSidebarCollapsedRail = computed(
  () => sidebarNavFullyCollapsed.value && !isNarrowLayout.value
)

const foldersAsideOuterStyle = computed((): Record<string, string | number> => {
  if (isNarrowLayout.value) return {} as Record<string, string | number>
  if (showSidebarCollapsedRail.value) {
    return { width: `${RAIL_ASIDE_WIDTH_PX}px`, flexShrink: '0' }
  }
  return { width: `${colFolderPx.value}px`, flexShrink: '0' }
})

function toggleSidebarNavFullyCollapsed() {
  sidebarNavFullyCollapsed.value = !sidebarNavFullyCollapsed.value
  writeBoolKey(SIDEBAR_NAV_FULL_COLLAPSE_KEY, sidebarNavFullyCollapsed.value)
  void nextTick(() => clampTagsPanelHeight())
}

watch(sidebarNavFullyCollapsed, async (collapsed) => {
  if (!collapsed && !isNarrowLayout.value) {
    await nextTick()
    clampTagsPanelHeight()
  }
})

const notesListColFullyCollapsed = ref(readBoolKey(NOTES_LIST_COL_FULL_COLLAPSE_KEY, false))

const showNotesListCollapsedRail = computed(
  () => notesListColFullyCollapsed.value && !isNarrowLayout.value
)

const notesListColOuterStyle = computed((): Record<string, string | number> => {
  if (isNarrowLayout.value) return {} as Record<string, string | number>
  if (showNotesListCollapsedRail.value) return {} as Record<string, string | number>
  return { width: `${colListPx.value}px`, flexShrink: '0' }
})

function toggleNotesListColFullyCollapsed() {
  notesListColFullyCollapsed.value = !notesListColFullyCollapsed.value
  writeBoolKey(NOTES_LIST_COL_FULL_COLLAPSE_KEY, notesListColFullyCollapsed.value)
}

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

function onFolderColGutterDown(e: MouseEvent) {
  if (showSidebarCollapsedRail.value) return
  onGutterDown('folder', e)
}

function onListColGutterDown(e: MouseEvent) {
  if (showNotesListCollapsedRail.value) return
  onGutterDown('list', e)
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
  const calMin = calendarListExpanded.value ? 100 : 44
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
/** Пустой список при folderViewTrash === false — все папки. «+»: вкл/выкл в фильтре (ИЛИ). */
const filterFolderIds = ref<string[]>([])
/** Папки, заметки из которых исключены из списка (кнопка «−»). Плоский список без иерархии. */
const filterExcludeFolderIds = ref<string[]>([])
/** Без включающих корней — все метки. «+» и клик по имени: вкл/выкл корень; несколько корней — ИЛИ на сервере. */
const filterTagIds = ref<string[]>([])
/** Корни веток, исключаемые из списка; «−» вкл/выкл по корню, можно совмещать с «+» у родителя. */
const filterExcludeTagIds = ref<string[]>([])
/** Корни поддеревьев, снятых с исключения (красное), если они попадали только под родительское «−». */
const filterExcludeUndoTagIds = ref<string[]>([])

/** Применение пресета: не дёргаем многократные watch(load). */
const bulkPresetApplyDepth = ref(0)
const filterPresets = ref<NoteFilterPreset[]>([])
const presetSelectId = ref('')
const presetBaselineFingerprint = ref<string | null>(null)
const presetPickerOpen = ref(false)
const presetPickerRootRef = ref<HTMLElement | null>(null)

/** Список сужен метками или поиском при прежнем охвате папок («n из N» в сайдбаре и календаре). */
const listRefinementBeyondFolders = computed(
  () =>
    !!q.value.trim() ||
    filterTagIds.value.length > 0 ||
    filterExcludeTagIds.value.length > 0 ||
    filterExcludeUndoTagIds.value.length > 0,
)

/** «Все заметки» — нет позитивного отбора по папке; исключения «−» остаются. */
const isAllFoldersScope = computed(
  () => !folderViewTrash.value && filterFolderIds.value.length === 0,
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
  e.dataTransfer?.setData(MIME_TAG_IDS_JSON, JSON.stringify([tagId]))
  e.dataTransfer!.effectAllowed = 'copy'
}

function onNoteRowDragOver(e: DragEvent) {
  const types = e.dataTransfer?.types ? [...e.dataTransfer.types] : []
  if (!isTagAttachDragTypes(types)) return
  e.preventDefault()
  e.dataTransfer!.dropEffect = 'copy'
}

async function onNoteRowDrop(e: DragEvent, noteId: string) {
  e.preventDefault()
  const tagIds = readDroppedTagIds(e)
  if (!tagIds.length) return
  try {
    for (const tagId of tagIds) {
      await notesApi.attachTag(noteId, tagId)
    }
    error.value = ''
    await load()
    reminderRefreshSignal.value++
    bumpEditorSyncIfOpen(noteId)
  } catch (err) {
    error.value = errMessage(err)
  }
}

const folderNavMainStyle = computed(() => {
  if (!foldersListExpanded.value) {
    return {
      flex: '0 0 auto',
      height: 'auto',
      minHeight: '0',
      maxHeight: 'none' as const,
      overflow: 'hidden' as const,
      display: 'flex',
      flexDirection: 'column' as const,
    }
  }
  return {
    flex: '0 0 auto',
    height: `${folderNavMainPx.value}px`,
    minHeight: '72px',
    overflow: 'hidden' as const,
    display: 'flex',
    flexDirection: 'column' as const,
  }
})

const tagsPanelStyle = computed(() => {
  if (!tagsListExpanded.value) {
    return {
      flex: '0 0 auto',
      height: 'auto',
      minHeight: '0',
    }
  }
  return {
    flex: '0 0 auto',
    height: `${tagsPanelHeightPx.value}px`,
  }
})

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

const tagsSidebarOnlyWithNotes = ref(
  readBoolKey(TAGS_ONLY_WITH_NOTES_IN_SCOPE_KEY, false)
)

watch(tagsSidebarOnlyWithNotes, (v) =>
  writeBoolKey(TAGS_ONLY_WITH_NOTES_IN_SCOPE_KEY, v)
)

/** То же дерево меток с отсечкой нулевых счётчиков в текущей области. */
const tagsRenderedInSidebar = computed(() => {
  const nav = tagsVisibleInSidebar.value
  if (!tagsSidebarOnlyWithNotes.value) return nav
  const counts = tagCountById.value
  return nav.filter((t) => (counts[String(t.id)] ?? 0) > 0)
})

const folderScopeUiLabel = computed(() => {
  if (folderViewTrash.value) return 'Корзина'
  if (!filterFolderIds.value.length) return 'Все заметки'
  if (filterFolderIds.value.length === 1) {
    const id = filterFolderIds.value[0]
    const f = folders.value.find((x) => x.id === id)
    return f?.name ? `«${f.name}»` : 'Папка'
  }
  return `Несколько папок (${filterFolderIds.value.length})`
})

const tagsOnlyInScopeTitle = computed(() => {
  const area = folderScopeUiLabel.value
  return `Только метки с заметками в области «${area}» (счётчик > 0, учтены вложенные).`
})

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
}

function clearTagFilter() {
  filterTagIds.value = []
  filterExcludeTagIds.value = []
  filterExcludeUndoTagIds.value = []
}

/** Вкл/выкл корень в положительном фильтре (несколько «+», ИЛИ на сервере). */
function toggleTagIncludeRoot(id: string) {
  const cur = [...filterTagIds.value]
  const i = cur.indexOf(id)
  if (i >= 0) cur.splice(i, 1)
  else cur.push(id)
  filterTagIds.value = cur
}

/** Вкл/выкл корень в исключении (можно исключить вложенность при активном «+» у родителя). */
function toggleTagExcludeRoot(id: string) {
  const cur = [...filterExcludeTagIds.value]
  const i = cur.indexOf(id)
  if (i >= 0) cur.splice(i, 1)
  else cur.push(id)
  filterExcludeTagIds.value = cur
}

function onSidebarTagClick(t: Tag) {
  toggleTagIncludeRoot(t.id)
}

/** «+»: выбрал / снова нажал — снял. */
function applyTagIncludeFilterToggle(t: Tag) {
  toggleTagIncludeRoot(t.id)
}

/** «−»: исключил ветку; у потомков «красной» только от родителя — включает carve-out («снять красное»). */
function applyTagExcludeFilterToggle(t: Tag) {
  const flat = tags.value
  const id = t.id

  if (filterExcludeTagIds.value.includes(id)) {
    filterExcludeTagIds.value = filterExcludeTagIds.value.filter((x) => x !== id)
    filterExcludeUndoTagIds.value = filterExcludeUndoTagIds.value.filter(
      (u) => !isDescendantTag(flat, id, u),
    )
    return
  }
  if (filterExcludeUndoTagIds.value.includes(id)) {
    filterExcludeUndoTagIds.value = filterExcludeUndoTagIds.value.filter((x) => x !== id)
    return
  }
  const hasAncestorExclude = filterExcludeTagIds.value.some(
    (ex) => ex !== id && isDescendantTag(flat, ex, id),
  )
  if (hasAncestorExclude) {
    filterExcludeUndoTagIds.value = [...filterExcludeUndoTagIds.value, id]
    return
  }
  toggleTagExcludeRoot(id)
}

/** В строке подсветка «показываем ветку» — узел входит в выбранный под любым корнем (+). */
function tagRowSubtreeIncluded(tagId: string): boolean {
  const flat = tags.value
  return filterTagIds.value.some((inc) => isDescendantTag(flat, inc, tagId))
}

/** Строка в зоне исключения поддерева (учитываются carve-out «снять с подветки»). */
function tagRowSubtreeExcluded(tagId: string): boolean {
  const flat = tags.value
  if (filterExcludeUndoTagIds.value.some((u) => isDescendantTag(flat, u, tagId))) return false
  return filterExcludeTagIds.value.some((ex) => isDescendantTag(flat, ex, tagId))
}

/** Кнопка «−»: явное исключение или активный carve-out. */
function tagRowMinusPressed(tagId: string): boolean {
  return filterExcludeTagIds.value.includes(tagId) || filterExcludeUndoTagIds.value.includes(tagId)
}

watch(
  [filterExcludeTagIds, tags],
  ([roots, flat]) => {
    if (!roots.length) {
      if (filterExcludeUndoTagIds.value.length) filterExcludeUndoTagIds.value = []
      return
    }
    if (!flat.length || !filterExcludeUndoTagIds.value.length) return
    const next = filterExcludeUndoTagIds.value.filter((u) =>
      roots.some((ex) => isDescendantTag(flat, ex, u)),
    )
    if (next.length !== filterExcludeUndoTagIds.value.length) filterExcludeUndoTagIds.value = next
  },
  { deep: true },
)

const foldersSorted = computed(() => foldersSortedAlphabetical(folders.value))

function countInFolder(folderId: string): number {
  const fc = folderNoteCounts.value?.folder_counts ?? []
  const row = fc.find((x) => x.folder_id === folderId)
  return row?.count ?? 0
}

/** Совпадает с областью списка заметок: сумма выбранных папок / все − исключённые. */
function effectiveNotesTotalForFolderScope(): number {
  if (!folderNoteCounts.value || folderViewTrash.value) return 0
  if (filterFolderIds.value.length === 0) {
    let t = folderNoteCounts.value.total
    for (const id of filterExcludeFolderIds.value) {
      t -= countInFolder(id)
    }
    return Math.max(0, t)
  }
  const ids = filterFolderIds.value
  let sumSel = ids.length === 1 ? countInFolder(ids[0]!) : ids.reduce((s, id) => s + countInFolder(id), 0)
  for (const ex of filterExcludeFolderIds.value) {
    if (ids.includes(ex)) sumSel -= countInFolder(ex)
  }
  return Math.max(0, sumSel)
}

/** Строка в скобках у «Все метки»: в области папок vs сколько попало в список после меток/поиска. */
const scopeTagsAllRowParenText = computed(() => {
  if (!folderNoteCounts.value || folderViewTrash.value) return ''
  const base = effectiveNotesTotalForFolderScope()
  if (!listRefinementBeyondFolders.value) return String(base)
  return `${notes.value.length} из ${base}`
})

/** Скобки у «Все заметки» в папках: без отбора папки показывает «n из N» при фильтрах меток/поиска. */
const sidebarAllNotesParenText = computed(() => {
  if (!folderNoteCounts.value) return ''
  if (folderViewTrash.value) return String(folderNoteCounts.value.total)
  if (filterFolderIds.value.length > 0) return String(folderNoteCounts.value.total)
  const base = effectiveNotesTotalForFolderScope()
  if (!listRefinementBeyondFolders.value) return String(base)
  return `${notes.value.length} из ${base}`
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
  void nextTick(() => clampTagsPanelHeight())
}

function toggleTagsList(e: Event) {
  e.preventDefault()
  e.stopPropagation()
  tagsListExpanded.value = !tagsListExpanded.value
  writeBoolKey(TAGS_LIST_EXPANDED_KEY, tagsListExpanded.value)
  void nextTick(() => clampTagsPanelHeight())
}

function toggleCalendarList(e: Event) {
  e.preventDefault()
  e.stopPropagation()
  calendarListExpanded.value = !calendarListExpanded.value
  writeBoolKey(CALENDAR_EXPANDED_KEY, calendarListExpanded.value)
  void nextTick(() => clampTagsPanelHeight())
}

/** Активная заметка из URL /notes/:id */
const activeNoteId = computed(() =>
  route.name === 'note' && typeof route.params.id === 'string' ? route.params.id : null
)

const noteRouteOpen = computed(() => !!activeNoteId.value)

watch(isNarrowLayout, (narrow) => {
  if (!narrow) mobileNavOpen.value = false
  if (narrow) {
    sidebarNavFullyCollapsed.value = false
    notesListColFullyCollapsed.value = false
  }
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

function folderListParams(): {
  folder_id?: string | string[]
  exclude_folder_id?: string | string[]
} {
  if (folderViewTrash.value) return {}
  const out: {
    folder_id?: string | string[]
    exclude_folder_id?: string | string[]
  } = {}
  const ids = filterFolderIds.value
  if (ids.length) out.folder_id = ids.length === 1 ? ids[0]! : [...ids]
  const ex = filterExcludeFolderIds.value
  if (ex.length) out.exclude_folder_id = ex.length === 1 ? ex[0]! : [...ex]
  return out
}

/** Параметры /tags/counts в той же области папок, что и список заметок. */
function tagCountsRequestParams(): TagsNoteCountsParams | undefined {
  if (folderViewTrash.value) return undefined
  const ex = filterExcludeFolderIds.value
  const excludePart: { exclude_folder_id?: string | string[] } =
    ex.length === 0 ? {} : { exclude_folder_id: ex.length === 1 ? ex[0]! : [...ex] }
  const fids = filterFolderIds.value
  if (fids.length === 1) return { folder_id: fids[0]!, ...excludePart }
  if (fids.length > 1) return { folder_id: [...fids], ...excludePart }
  return Object.keys(excludePart).length ? excludePart : undefined
}

function clearFolderPicker() {
  folderViewTrash.value = false
  filterFolderIds.value = []
  filterExcludeFolderIds.value = []
}

function openTrashFolder() {
  folderViewTrash.value = true
  filterFolderIds.value = []
  filterExcludeFolderIds.value = []
}

/** В списке папок без Ctrl — тот же toggle, что кнопка «+». */
function toggleFolderIncludeRoot(folderId: string) {
  if (folderViewTrash.value) folderViewTrash.value = false
  const cur = [...filterFolderIds.value]
  const i = cur.indexOf(folderId)
  if (i >= 0) cur.splice(i, 1)
  else cur.push(folderId)
  filterFolderIds.value = cur
}

function toggleFolderExcludeRoot(folderId: string) {
  const cur = [...filterExcludeFolderIds.value]
  const i = cur.indexOf(folderId)
  if (i >= 0) cur.splice(i, 1)
  else cur.push(folderId)
  filterExcludeFolderIds.value = cur
}

function onSidebarFolderClick(f: Folder) {
  toggleFolderIncludeRoot(f.id)
}

function applyFolderIncludeFilterToggle(f: Folder) {
  toggleFolderIncludeRoot(f.id)
}

function applyFolderExcludeFilterToggle(f: Folder) {
  toggleFolderExcludeRoot(f.id)
}

function folderRowExcluded(folderId: string): boolean {
  return filterExcludeFolderIds.value.includes(folderId)
}

function folderRowIncludedHighlight(folderId: string): boolean {
  return filterFolderIds.value.includes(folderId) && !folderRowExcluded(folderId)
}

function tagFilterParams(): {
  tag_id?: string | string[]
  exclude_tag_id?: string | string[]
  exclude_tag_undo_id?: string | string[]
} {
  const out: {
    tag_id?: string | string[]
    exclude_tag_id?: string | string[]
    exclude_tag_undo_id?: string | string[]
  } = {}
  const ids = filterTagIds.value
  if (ids.length) out.tag_id = ids.length === 1 ? ids[0]! : [...ids]
  const xids = filterExcludeTagIds.value
  if (xids.length) out.exclude_tag_id = xids.length === 1 ? xids[0]! : [...xids]
  const uids = filterExcludeUndoTagIds.value
  if (uids.length) out.exclude_tag_undo_id = uids.length === 1 ? uids[0]! : [...uids]
  return out
}

function filterStateFingerprint(): string {
  return JSON.stringify({
    q: q.value.trim(),
    trash: folderViewTrash.value,
    folders: [...filterFolderIds.value].slice().sort(),
    exFolders: [...filterExcludeFolderIds.value].slice().sort(),
    tags: [...filterTagIds.value].slice().sort(),
    exTags: [...filterExcludeTagIds.value].slice().sort(),
    exUndo: [...filterExcludeUndoTagIds.value].slice().sort(),
  })
}

function fingerprintFromPresetPayload(p: NoteFilterPreset): string {
  return JSON.stringify({
    q: (p.search_query ?? '').trim(),
    trash: false,
    folders: [...p.folder_ids].map(String).sort(),
    exFolders: [...p.exclude_folder_ids].map(String).sort(),
    tags: [...p.tag_ids].map(String).sort(),
    exTags: [...p.exclude_tag_ids].map(String).sort(),
    exUndo: [...p.exclude_tag_undo_ids].map(String).sort(),
  })
}

function presetFiltersPayload(): {
  search_query: string | null
  folder_ids: string[]
  exclude_folder_ids: string[]
  tag_ids: string[]
  exclude_tag_ids: string[]
  exclude_tag_undo_ids: string[]
} {
  const qt = q.value.trim()
  return {
    search_query: qt ? qt : null,
    folder_ids: [...filterFolderIds.value],
    exclude_folder_ids: [...filterExcludeFolderIds.value],
    tag_ids: [...filterTagIds.value],
    exclude_tag_ids: [...filterExcludeTagIds.value],
    exclude_tag_undo_ids: [...filterExcludeUndoTagIds.value],
  }
}

const presetHasUnsavedChanges = computed(
  () =>
    !!presetSelectId.value &&
    !!presetBaselineFingerprint.value &&
    filterStateFingerprint() !== presetBaselineFingerprint.value,
)

const chosenPresetSummary = computed(
  (): NoteFilterPreset | null =>
    presetSelectId.value ? filterPresets.value.find((p) => p.id === presetSelectId.value) ?? null : null,
)

function closePresetPicker() {
  presetPickerOpen.value = false
}

function togglePresetPicker() {
  presetPickerOpen.value = !presetPickerOpen.value
}

function onPresetDocPointerDown(ev: MouseEvent | PointerEvent) {
  if (!presetPickerOpen.value) return
  const root = presetPickerRootRef.value
  if (root && !root.contains(ev.target as Node)) closePresetPicker()
}

function onPresetDocKeydown(ev: KeyboardEvent) {
  if (ev.key !== 'Escape' || !presetPickerOpen.value) return
  closePresetPicker()
}

watch(presetPickerOpen, (open) => {
  if (typeof document === 'undefined') return
  if (open) {
    document.addEventListener('pointerdown', onPresetDocPointerDown, true)
    document.addEventListener('keydown', onPresetDocKeydown, true)
  } else {
    document.removeEventListener('pointerdown', onPresetDocPointerDown, true)
    document.removeEventListener('keydown', onPresetDocKeydown, true)
  }
})

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

    const countsParams = tagCountsRequestParams()
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

async function loadFilterPresets() {
  if (!auth.user) return
  try {
    filterPresets.value = await noteFilterPresetsApi.list()
    if (presetSelectId.value && !filterPresets.value.some((x) => x.id === presetSelectId.value)) {
      presetSelectId.value = ''
      presetBaselineFingerprint.value = null
    }
  } catch {
    /* мягкий сбой сети */
  }
}

async function applyPresetFromList(p: NoteFilterPreset) {
  bulkPresetApplyDepth.value++
  try {
    folderViewTrash.value = false
    filterFolderIds.value = [...p.folder_ids]
    filterExcludeFolderIds.value = [...p.exclude_folder_ids]
    filterTagIds.value = [...p.tag_ids]
    filterExcludeTagIds.value = [...p.exclude_tag_ids]
    filterExcludeUndoTagIds.value = [...p.exclude_tag_undo_ids]
    q.value = p.search_query ?? ''
  } finally {
    bulkPresetApplyDepth.value--
  }
  presetBaselineFingerprint.value = fingerprintFromPresetPayload(p)
  await load()
}

async function choosePresetFromDropdown(p: NoteFilterPreset) {
  presetSelectId.value = p.id
  closePresetPicker()
  await applyPresetFromList(p)
}

function clearChosenPresetOnly() {
  presetSelectId.value = ''
  presetBaselineFingerprint.value = null
  closePresetPicker()
}

async function createNewPresetFromDropdown() {
  closePresetPicker()
  await saveNewFilterPresetAs()
}

async function saveNewFilterPresetAs() {
  const name = window.prompt('Название набора фильтров (папки, метки и строка поиска)', '')
  if (name === null) return
  const t = name.trim()
  if (!t) return
  if (!auth.user || folderViewTrash.value) return
  try {
    const created = await noteFilterPresetsApi.create({
      name: t,
      ...presetFiltersPayload(),
    })
    await loadFilterPresets()
    presetSelectId.value = created.id
    presetBaselineFingerprint.value = fingerprintFromPresetPayload(created)
    error.value = ''
  } catch (e) {
    error.value = errMessage(e)
  }
}

async function renameFilterPresetById(id: string) {
  const p = filterPresets.value.find((x) => x.id === id)
  if (!p || folderViewTrash.value) return
  const name = window.prompt('Новое имя набора', p.name)
  if (name === null) return
  const t = name.trim()
  if (!t || t === p.name) return
  try {
    const updated = await noteFilterPresetsApi.update(id, { name: t })
    const idx = filterPresets.value.findIndex((x) => x.id === id)
    if (idx >= 0) filterPresets.value.splice(idx, 1, updated)
    else filterPresets.value = await noteFilterPresetsApi.list()
    error.value = ''
  } catch (e) {
    error.value = errMessage(e)
  }
}

async function overwriteFilterPresetById(id: string) {
  const p = filterPresets.value.find((x) => x.id === id)
  if (!p || folderViewTrash.value) return
  try {
    const updated = await noteFilterPresetsApi.update(id, {
      name: p.name,
      ...presetFiltersPayload(),
    })
    const idx = filterPresets.value.findIndex((x) => x.id === id)
    if (idx >= 0) filterPresets.value.splice(idx, 1, updated)
    else filterPresets.value = await noteFilterPresetsApi.list()
    if (presetSelectId.value === id)
      presetBaselineFingerprint.value = fingerprintFromPresetPayload(updated)
    error.value = ''
  } catch (e) {
    error.value = errMessage(e)
  }
}

async function deleteFilterPresetById(id: string) {
  if (!id || folderViewTrash.value) return
  const p = filterPresets.value.find((x) => x.id === id)
  if (!window.confirm(`Удалить набор фильтров${p?.name ? ` «${p.name}»` : ''}?`)) return
  try {
    await noteFilterPresetsApi.remove(id)
    if (presetSelectId.value === id) {
      presetSelectId.value = ''
      presetBaselineFingerprint.value = null
    }
    await loadFilterPresets()
    error.value = ''
  } catch (e) {
    error.value = errMessage(e)
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
    filterFolderIds.value = filterFolderIds.value.filter((x) => x !== f.id)
    filterExcludeFolderIds.value = filterExcludeFolderIds.value.filter((x) => x !== f.id)
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

/** Нативный title: полный заголовок и текст (с ограничением по длине), даты внизу. */
const NOTE_ROW_TOOLTIP_BODY_MAX = 8000

function noteRowDatesLines(n: Note): string[] {
  const lines = [`Создано: ${fmtMsk(n.created_at)}`, `Изменено: ${fmtMsk(n.updated_at)}`]
  if (n.deleted_at) lines.push(`Удалено: ${fmtMsk(n.deleted_at)}`)
  return lines
}

function noteRowTooltip(n: Note): string {
  const titleFull = (n.title || '').trim() || DEFAULT_NOTE_TITLE
  const raw = (n.content_plain || '').replace(/\s+/g, ' ').trim()
  let bodyTip = ''
  if (raw) {
    bodyTip =
      raw.length > NOTE_ROW_TOOLTIP_BODY_MAX
        ? `${raw.slice(0, NOTE_ROW_TOOLTIP_BODY_MAX).trimEnd()}…`
        : raw
  }
  const lines: string[] = [titleFull]
  if (bodyTip) {
    lines.push('', bodyTip)
  }
  lines.push('', ...noteRowDatesLines(n))
  return lines.join('\n')
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
  await loadFilterPresets()
  await load()
  await nextTick()
  clampTagsPanelHeight()
  window.addEventListener('resize', clampTagsPanelHeight)
})

watch(folderViewTrash, (trash) => {
  if (bulkPresetApplyDepth.value > 0) return
  if (trash) {
    presetSelectId.value = ''
    presetBaselineFingerprint.value = null
    filterTagIds.value = []
    filterExcludeTagIds.value = []
    filterExcludeUndoTagIds.value = []
    filterExcludeFolderIds.value = []
  }
  void load()
})
watch(
  [filterFolderIds, filterExcludeFolderIds],
  () => {
    if (bulkPresetApplyDepth.value > 0) return
    if (folderViewTrash.value && filterFolderIds.value.length) {
      folderViewTrash.value = false
    }
    void load()
  },
  { deep: true }
)
watch(
  [filterTagIds, filterExcludeTagIds, filterExcludeUndoTagIds],
  () => {
    if (bulkPresetApplyDepth.value > 0) return
    if (folderViewTrash.value) {
      if (
        filterTagIds.value.length ||
        filterExcludeTagIds.value.length ||
        filterExcludeUndoTagIds.value.length
      ) {
        folderViewTrash.value = false
        filterFolderIds.value = []
        filterExcludeFolderIds.value = []
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
  if (presetPickerOpen.value && typeof document !== 'undefined') {
    document.removeEventListener('pointerdown', onPresetDocPointerDown, true)
    document.removeEventListener('keydown', onPresetDocKeydown, true)
  }
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
      <div class="header-toolbar">
        <button
          v-if="auth.user?.is_admin"
          type="button"
          class="btn admin-top-btn"
          title="Пользователи и доступ к созданию заметок"
          @click="adminUsersOpen = true"
        >
          Админка
        </button>
        <div class="header-search-block">
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
          <div v-if="auth.user && !folderViewTrash" class="preset-strip">
            <div ref="presetPickerRootRef" class="preset-picker">
              <div class="preset-combo">
                <span
                  v-if="presetHasUnsavedChanges && presetSelectId"
                  class="preset-unsaved-dot"
                  title="Есть несохранённые изменения"
                />
                <button
                  type="button"
                  class="preset-trigger"
                  aria-label="Сохранённые наборы фильтров"
                  :aria-expanded="presetPickerOpen"
                  aria-haspopup="listbox"
                  :title="chosenPresetSummary?.name || undefined"
                  @click="togglePresetPicker"
                >
                  <span
                    class="preset-trigger-label"
                    :class="{ 'preset-trigger-label--muted': !chosenPresetSummary }"
                  >
                    {{ chosenPresetSummary?.name ?? 'Выберите фильтр…' }}
                  </span>
                  <svg class="preset-chevron" viewBox="0 0 24 24" aria-hidden="true">
                    <path
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      d="M6 9l6 6 6-6"
                    />
                  </svg>
                </button>
              </div>
              <div
                v-show="presetPickerOpen"
                class="preset-dropdown"
                role="listbox"
                aria-label="Список сохранённых фильтров"
              >
                <button
                  v-if="presetSelectId"
                  type="button"
                  class="preset-dd-row preset-dd-row--muted"
                  role="option"
                  @click="clearChosenPresetOnly"
                >
                  <span class="preset-dd-name">Без сохранённого набора</span>
                </button>
                <div v-for="p in filterPresets" :key="p.id" class="preset-dd-item">
                  <button
                    type="button"
                    class="preset-dd-main"
                    role="option"
                    :title="p.name"
                    :aria-selected="p.id === presetSelectId"
                    :class="{ 'preset-dd-main--active': p.id === presetSelectId }"
                    @click="choosePresetFromDropdown(p)"
                  >
                    <span class="preset-dd-name">{{ p.name }}</span>
                  </button>
                  <div class="preset-row-actions" role="toolbar" :aria-label="'Действия: ' + p.name">
                    <button
                      type="button"
                      class="preset-row-act"
                      title="Перезаписать текущими фильтрами"
                      :disabled="folderViewTrash"
                      aria-label="Сохранить изменения в набор"
                      @click.stop="overwriteFilterPresetById(p.id)"
                    >
                      <svg class="preset-ico" viewBox="0 0 24 24" aria-hidden="true">
                        <path
                          fill="none"
                          stroke="currentColor"
                          stroke-width="1.75"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                          d="M19 21H8a3 3 0 01-3-3V5h9l6 6v10a3 3 0 01-3 3z"
                        />
                        <path
                          fill="none"
                          stroke="currentColor"
                          stroke-width="1.75"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                          d="M17 21v-9h-9"
                        />
                      </svg>
                    </button>
                    <button
                      type="button"
                      class="preset-row-act"
                      title="Переименовать"
                      :disabled="folderViewTrash"
                      aria-label="Переименовать набор"
                      @click.stop="renameFilterPresetById(p.id)"
                    >
                      <svg class="preset-ico" viewBox="0 0 24 24" aria-hidden="true">
                        <path
                          fill="none"
                          stroke="currentColor"
                          stroke-width="1.75"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                          d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"
                        />
                      </svg>
                    </button>
                    <button
                      type="button"
                      class="preset-row-act preset-row-act--danger"
                      title="Удалить набор"
                      :disabled="folderViewTrash"
                      aria-label="Удалить набор"
                      @click.stop="deleteFilterPresetById(p.id)"
                    >
                      <svg class="preset-ico" viewBox="0 0 24 24" aria-hidden="true">
                        <path
                          fill="none"
                          stroke="currentColor"
                          stroke-width="1.75"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                          d="M18 6L6 18M6 6l12 12"
                        />
                      </svg>
                    </button>
                  </div>
                </div>
                <div v-if="!filterPresets.length" class="preset-dd-empty">Нет сохранённых наборов</div>
                <div class="preset-dd-divider" role="presentation" />
                <button
                  type="button"
                  class="preset-dd-row preset-dd-row--create"
                  role="option"
                  :disabled="folderViewTrash"
                  @click="createNewPresetFromDropdown"
                >
                  <svg class="preset-ico preset-ico--leading" viewBox="0 0 24 24" aria-hidden="true">
                    <path
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      d="M12 5v14M5 12h14"
                    />
                  </svg>
                  <span class="preset-dd-name">Создать новый фильтр…</span>
                </button>
              </div>
            </div>
          </div>
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
      </div>
      <div class="header-user">
        <span class="user" v-if="auth.user">{{ auth.user.email }}</span>
        <button type="button" class="btn ghost" @click="logout">Выйти</button>
      </div>
    </header>

    <AdminUsersModal v-model:open="adminUsersOpen" />

    <div class="workspace-body">
      <aside
        class="folders-aside sidebar-panel"
        :class="{
          'folders-aside--drawer-open': isNarrowLayout && mobileNavOpen,
          'folders-aside--rail-collapsed': showSidebarCollapsedRail,
        }"
        :style="foldersAsideOuterStyle"
      >
        <button
          v-if="showSidebarCollapsedRail"
          type="button"
          class="folders-aside-rail-expand"
          title="Развернуть навигацию: папки, метки, календарь"
          aria-label="Развернуть боковую панель"
          @click="toggleSidebarNavFullyCollapsed"
        >
          +
        </button>
        <nav v-else ref="folderNavRef" class="folder-nav">
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
                  <button
                    v-if="!isNarrowLayout"
                    type="button"
                    class="btn-nav-panel-hide"
                    title="Скрыть панель: папки, метки и календарь"
                    aria-label="Скрыть боковую панель навигации"
                    @click="toggleSidebarNavFullyCollapsed"
                  >
                    −
                  </button>
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
                    <span v-if="folderNoteCounts" class="tag-count nav-scope-count"> ({{ sidebarAllNotesParenText }})</span>
                  </button>
                </div>
              </div>
              <div
                class="folder-nav-folders-scroll"
                :class="{ 'folder-nav-folders-scroll--collapsed': !foldersListExpanded }"
              >
                <div v-show="foldersListExpanded" class="folder-rows">
                  <div
                    v-for="f in foldersSorted"
                    :key="f.id"
                    class="nav-row folder-sidebar-row"
                    :class="{
                      'folder-sidebar-row--exclude': folderRowExcluded(f.id),
                      on: folderRowIncludedHighlight(f.id),
                    }"
                    @dragover="onFolderDragOver"
                    @drop="onFolderDrop($event, f.id)"
                  >
                    <button
                      type="button"
                      class="nav-row-label"
                      title="Тот же вкл/выкл, что «+»: папка в фильтре (ИЛИ с другими). Можно вместе с «−», чтобы временно исключить папку из «всех» или комбинации"
                      @click="onSidebarFolderClick(f)"
                    >
                      <span class="folder-label">{{ f.name }}</span>
                    </button>
                    <div class="nav-row-actions nav-row-actions--folder-filter">
                      <button
                        type="button"
                        class="btn-tag-filter-plus"
                        :class="{ on: filterFolderIds.includes(f.id) }"
                        title="Заметки из этой папки (ещё раз — убрать). Несколько папок объединяются по ИЛИ"
                        aria-label="Включить папку в фильтре"
                        :aria-pressed="filterFolderIds.includes(f.id)"
                        @click.stop="applyFolderIncludeFilterToggle(f)"
                      >
                        +
                      </button>
                      <button
                        type="button"
                        class="btn-tag-filter-minus"
                        :class="{ on: filterExcludeFolderIds.includes(f.id) }"
                        title="Скрыть заметки этой папки в списке (ещё раз — вернуть)"
                        aria-label="Исключить папку из списка"
                        :aria-pressed="filterExcludeFolderIds.includes(f.id)"
                        @click.stop="applyFolderExcludeFilterToggle(f)"
                      >
                        −
                      </button>
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
            <div class="folder-nav-tags-panel" :style="tagsPanelStyle">
                <div class="folder-nav-tags-sticky">
                  <div
                    class="folder-all-row tag-all-wrap folder-all-row--frame folder-scope-notes-parent tags-all-row-scope"
                  >
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
                      class="folder-filter tag-filter grow folder-filter-all nav-scope-tags-all-btn"
                      :class="{
                        on:
                          !filterTagIds.length &&
                          !filterExcludeTagIds.length &&
                          !filterExcludeUndoTagIds.length,
                      }"
                      @click="clearTagFilter"
                    >
                      <span class="nav-scope-tags-heading nowrap-scope-heading">
                        <template v-if="folderNoteCounts">
                          Все метки<span class="nav-scope-tags-count">&nbsp;({{ scopeTagsAllRowParenText }})</span>
                        </template>
                        <template v-else>Все метки</template>
                      </span>
                    </button>
                    <label class="tags-scope-only-wrap" :title="tagsOnlyInScopeTitle" @click.stop>
                      <input
                        v-model="tagsSidebarOnlyWithNotes"
                        type="checkbox"
                        aria-label="С заметками — только метки с заметками в текущей области списка"
                      />
                    </label>
                  </div>
                </div>
                <div
                  class="folder-nav-tags-scroll"
                  :class="{
                    'folder-nav-tags-scroll--collapsed': !tagsListExpanded,
                  }"
                >
                  <div
                    v-for="t in tagsRenderedInSidebar"
                    v-show="tagsListExpanded"
                    :key="t.id"
                    class="nav-row tag-sidebar-row"
                    :class="{
                      'tag-sidebar-row--exclude': tagRowSubtreeExcluded(t.id),
                      on: tagRowSubtreeIncluded(t.id) && !tagRowSubtreeExcluded(t.id),
                    }"
                    :style="{ paddingLeft: (0.28 + Math.max(0, t.depth - 1) * 0.38) + 'rem' }"
                    draggable="true"
                    @dragstart="onTagDragStart($event, t.id)"
                  >
                    <button
                      type="button"
                      class="nav-row-label nav-row-label--tag"
                      title="Тот же вкл/выкл, что «+»: метка в фильтре (ИЛИ с другими). Можно вместе с «−» на вложениях при «+» у родителя"
                      @click="onSidebarTagClick(t)"
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
                    <div class="nav-row-actions nav-row-actions--tag-filter">
                      <button
                        type="button"
                        class="btn-tag-filter-plus"
                        :class="{ on: filterTagIds.includes(t.id) }"
                        title="Выбрать ветку (ещё раз — убрать из выбора). Несколько «+» объединяются по ИЛИ"
                        :aria-pressed="filterTagIds.includes(t.id)"
                        @click.stop="applyTagIncludeFilterToggle(t)"
                      >
                        +
                      </button>
                      <button
                        type="button"
                        class="btn-tag-filter-minus"
                        :class="{ on: tagRowMinusPressed(t.id) }"
                        title="Исключить всю ветку. Если строка красная из‑за «−» у родителя — снимает красное с этой подветки без снятия исключения у родителя; ещё раз — вернуть исключение"
                        :aria-pressed="tagRowMinusPressed(t.id)"
                        @click.stop="applyTagExcludeFilterToggle(t)"
                      >
                        −
                      </button>
                    </div>
                    <span class="tag-count">({{ tagCountById[t.id] ?? 0 }})</span>
                  </div>
                </div>
              </div>
              <div
                v-show="tagsListExpanded"
                class="folder-nav-tags-cal-gutter"
                title="Потяните вниз — меньше меток, ниже — календарь и корзина; вверх — больше меток"
                @mousedown="onTagsCalendarGutterDown($event)"
              />
              <div class="folder-nav-calendar-block">
                <div class="folder-nav-calendar-sticky">
                  <div class="folder-all-row tag-all-wrap folder-all-row--frame">
                    <button
                      type="button"
                      class="section-chevron"
                      :class="{ 'section-chevron--collapsed': !calendarListExpanded }"
                      title="Показать или скрыть календарь"
                      @click="toggleCalendarList"
                    >
                      {{ calendarListExpanded ? '▾' : '▸' }}
                    </button>
                    <span class="folder-label nav-scope-label">Календарь</span>
                  </div>
                </div>
                <div v-show="calendarListExpanded" class="folder-nav-calendar-wrap">
                  <ReminderCalendar
                    embed-in-sidebar
                    :fraction-from-list-filter="listRefinementBeyondFolders && !folderViewTrash"
                    :refresh-signal="reminderRefreshSignal"
                    :scope-note-ids="notes.map((n) => n.id)"
                    @open-note="openNote"
                  />
                </div>
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
        :class="{ 'col-gutter--disabled': showSidebarCollapsedRail }"
        :title="
          showSidebarCollapsedRail ? 'Развернуть левую панель для изменения ширины.' : 'Потяните, чтобы изменить ширину колонки'
        "
        @mousedown="onFolderColGutterDown($event)"
      />

      <button
        v-if="showNotesListCollapsedRail"
        type="button"
        class="notes-list-rail-expand"
        title="Развернуть список заметок"
        aria-label="Развернуть список заметок"
        @click="toggleNotesListColFullyCollapsed"
      >
        +
      </button>
      <div
        v-else
        class="notes-list-col"
        :style="notesListColOuterStyle"
      >
        <div class="list-toolbar">
          <div class="list-toolbar-main-row">
            <span class="list-toolbar-scope" :title="folderScopeUiLabel">{{ folderScopeUiLabel }}</span>
            <div class="list-toolbar-sort-row">
              <div class="list-toolbar-sort">
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
              <button
                v-if="!isNarrowLayout"
                type="button"
                class="btn-notes-list-hide"
                title="Скрыть список заметок"
                aria-label="Скрыть список заметок"
                @click="toggleNotesListColFullyCollapsed"
              >
                −
              </button>
            </div>
          </div>
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
                :title="noteRowTooltip(n)"
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
        :class="{ 'col-gutter--disabled': showNotesListCollapsedRail }"
        :title="
          showNotesListCollapsedRail
            ? 'Разверните список заметок, чтобы менять ширину.'
            : 'Потяните, чтобы изменить ширину списка'
        "
        @mousedown="onListColGutterDown($event)"
      />

      <div class="editor-shell">
        <NoteEditorColumn
          :note-id="activeNoteId"
          :sorted-note-ids="sortedNotes.map((n) => n.id)"
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
  position: relative;
  z-index: 60;
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
.header-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.65rem;
  flex: 1 1 auto;
  min-width: 0;
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
.header-search-block {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem 0.55rem;
  flex: 1 1 220px;
  min-width: 140px;
  max-width: min(640px, 100%);
}
.preset-strip {
  display: flex;
  align-items: center;
  flex: 1 1 15rem;
  min-width: min(15rem, 100%);
  max-width: 100%;
}
.preset-combo {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  width: 100%;
  min-width: 0;
}
.preset-picker {
  position: relative;
  flex: 1 1 auto;
  min-width: 0;
  max-width: 100%;
}
.preset-trigger {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
  margin: 0;
  padding: 0.32rem 0.5rem;
  border: 1px solid rgba(148, 163, 184, 0.38);
  border-radius: 10px;
  background: rgba(248, 250, 252, 0.65);
  color: #0f172a;
  font-size: 0.72rem;
  font-weight: 500;
  cursor: pointer;
  text-align: left;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease,
    background 0.15s ease;
}
.preset-trigger:hover {
  border-color: rgba(37, 99, 235, 0.38);
}
.preset-trigger:focus-visible {
  outline: none;
  border-color: rgba(37, 99, 235, 0.55);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}
.preset-trigger-label {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.preset-trigger-label--muted {
  color: #64748b;
  font-weight: 400;
}
.preset-chevron {
  flex-shrink: 0;
  width: 0.95rem;
  height: 0.95rem;
  color: #64748b;
}
.preset-dropdown {
  position: absolute;
  left: 0;
  right: 0;
  top: calc(100% + 6px);
  z-index: 260;
  box-sizing: border-box;
  /* По ширине триггера / блока фильтров, без «лишней» минимальной ширины списка */
  width: auto;
  max-width: min(100%, calc(100vw - 24px));
  max-height: min(60vh, 18rem);
  overflow-y: auto;
  padding: 4px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.98);
  border: 1px solid rgba(148, 163, 184, 0.35);
  box-shadow:
    0 4px 6px -1px rgba(15, 23, 42, 0.08),
    0 16px 36px -10px rgba(15, 23, 42, 0.2);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}
.preset-dd-row {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  width: 100%;
  margin: 0;
  padding: 0.4rem 0.55rem;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #0f172a;
  font-size: 0.72rem;
  text-align: left;
  cursor: pointer;
}
.preset-dd-row:hover {
  background: rgba(15, 23, 42, 0.045);
}
.preset-dd-row:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.preset-dd-row--muted {
  color: #64748b;
  font-weight: 500;
}
.preset-dd-row--create {
  color: var(--accent, #2563eb);
  font-weight: 600;
}
.preset-dd-divider {
  height: 1px;
  margin: 4px 6px;
  background: rgba(148, 163, 184, 0.28);
}
.preset-dd-empty {
  padding: 0.35rem 0.55rem 0.2rem;
  font-size: 0.68rem;
  color: #94a3b8;
}
.preset-dd-item {
  position: relative;
  display: block;
  margin: 0;
  padding: 0;
  border-radius: 8px;
}
.preset-dd-item:hover {
  background: rgba(15, 23, 42, 0.04);
}
.preset-dd-item:focus-within {
  background: rgba(37, 99, 235, 0.06);
}
.preset-dd-main {
  box-sizing: border-box;
  display: block;
  width: 100%;
  margin: 0;
  padding: 0.4rem 0.55rem;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #0f172a;
  font-size: 0.72rem;
  font-weight: 500;
  text-align: left;
  cursor: pointer;
}
.preset-dd-main:focus-visible {
  outline: none;
}
.preset-dd-main--active {
  color: var(--accent, #2563eb);
}
.preset-dd-name {
  display: block;
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.preset-row-actions {
  position: absolute;
  top: 0;
  bottom: 0;
  right: 0;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 0 0.35rem 0 1.75rem;
  border-radius: 0 8px 8px 0;
  /* Ярлыки поверх строки справа, текст не зажимается второй колонкой */
  background: linear-gradient(
    to right,
    rgba(255, 255, 255, 0),
    rgba(255, 255, 255, 0.78) 30%,
    rgba(255, 255, 255, 0.97) 52%,
    rgba(255, 255, 255, 0.99) 100%
  );
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
  transition:
    opacity 0.14s ease,
    visibility 0.14s;
}
@media (hover: hover) {
  .preset-dd-item:hover .preset-row-actions,
  .preset-dd-item:focus-within .preset-row-actions {
    opacity: 1;
    visibility: visible;
    pointer-events: auto;
  }
}
@media (hover: none) {
  /* Тач: блок действий уже «над» текстом справа, не смещает текст */
  .preset-row-actions {
    opacity: 1;
    visibility: visible;
    pointer-events: auto;
    background: linear-gradient(
      to right,
      rgba(255, 255, 255, 0),
      rgba(255, 255, 255, 0.85) 35%,
      rgba(255, 255, 255, 0.98) 60%,
      rgba(255, 255, 255, 0.99) 100%
    );
  }
}
.preset-row-act {
  position: relative;
  z-index: 1;
  display: grid;
  place-items: center;
  width: 1.75rem;
  height: 1.75rem;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #475569;
  cursor: pointer;
  transition:
    background 0.12s ease,
    color 0.12s ease,
    transform 0.12s ease;
}
.preset-row-act:hover:not(:disabled) {
  background: rgba(15, 23, 42, 0.08);
  color: #0f172a;
}
.preset-row-act:active:not(:disabled) {
  transform: scale(0.93);
}
.preset-row-act--danger:hover:not(:disabled) {
  background: rgba(220, 38, 38, 0.1);
  color: #b91c1c;
}
.preset-row-act:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.preset-unsaved-dot {
  width: 8px;
  height: 8px;
  flex-shrink: 0;
  border-radius: 50%;
  background: linear-gradient(135deg, #f59e0b, #ea580c);
  box-shadow: 0 0 0 2px rgba(251, 146, 60, 0.35);
}
.preset-ico {
  width: 1rem;
  height: 1rem;
  display: block;
}
.preset-ico--leading {
  flex-shrink: 0;
}
.search-wrap {
  display: flex;
  align-items: center;
  flex: 1 1 min(420px, 100%);
  min-width: min(280px, 100%);
  max-width: none;
}
.search {
  width: 100%;
  min-width: 0;
  max-width: none;
  box-sizing: border-box;
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
  padding-left: 0.85rem;
  border-left: 1px solid rgba(148, 163, 184, 0.35);
  margin-left: auto;
  flex-shrink: 0;
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
.folders-aside--rail-collapsed {
  padding: 0.35rem 0.2rem;
}
.folders-aside-rail-expand {
  flex: 1 1 auto;
  min-height: 6rem;
  border: 1px solid var(--sidebar-edge);
  border-radius: 8px;
  background: #fff;
  font-size: 1.35rem;
  font-weight: 600;
  cursor: pointer;
  color: var(--accent, #2563eb);
  line-height: 1;
}
.folders-aside-rail-expand:hover {
  background: #f8fafc;
}
.notes-list-rail-expand {
  flex-shrink: 0;
  width: 40px;
  align-self: stretch;
  max-height: calc(100vh - 52px);
  margin: 0;
  border: none;
  border-right: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 0;
  background: linear-gradient(180deg, #fafbfc 0%, #f4f5f8 100%);
  font-size: 1.35rem;
  font-weight: 600;
  cursor: pointer;
  color: var(--accent, #2563eb);
  line-height: 1;
}
.notes-list-rail-expand:hover {
  background: #eef2f7;
}
.list-toolbar-main-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem 0.55rem;
  min-width: 0;
}
.list-toolbar-scope {
  flex: 1 1 auto;
  min-width: 0;
  font-weight: 600;
  font-size: 0.8125rem;
  letter-spacing: -0.02em;
  color: #111827;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.list-toolbar-sort-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex: 0 0 auto;
  margin-left: auto;
  max-width: 100%;
}
.list-toolbar-sort {
  display: flex;
  align-items: center;
  gap: 0.38rem;
  flex: 0 1 auto;
  min-width: 0;
}
.list-toolbar-sort-row .btn-notes-list-hide {
  flex-shrink: 0;
}
.btn-notes-list-hide {
  width: 1.65rem;
  height: 1.65rem;
  padding: 0;
  border: 1px solid rgba(148, 163, 184, 0.45);
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
  color: #475569;
}
.btn-notes-list-hide:hover {
  background: #f8fafc;
}
.folder-new-row .btn-nav-panel-hide {
  flex-shrink: 0;
}
.btn-nav-panel-hide {
  box-sizing: border-box;
  width: 1.65rem;
  height: 1.65rem;
  padding: 0;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #f8fafc;
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
  color: #475569;
}
.btn-nav-panel-hide:hover {
  background: #f1f5f9;
}
.col-gutter--disabled {
  pointer-events: none;
  opacity: 0.38;
  cursor: default;
}
.col-gutter--disabled:hover {
  background: transparent;
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
  font-size: 0.8125rem;
  letter-spacing: -0.02em;
  color: #111827;
}
.folder-filter-all.on .nav-scope-label {
  color: #111827;
}
.nav-scope-count {
  font-weight: 500;
  font-size: 0.72rem;
  color: #94a3b8;
  opacity: 1;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}
.folder-filter-all.on .nav-scope-count {
  color: #7c8a9e;
}
.folder-nav-folders-panel .folder-filter .tag-count.nav-scope-count,
.folder-nav-tags-panel .folder-filter .tag-count.nav-scope-count {
  font-size: 0.72rem;
  font-weight: 500;
  color: #94a3b8;
  opacity: 1;
  line-height: 1.2;
}
.folder-nav-folders-panel .folder-filter-all.on .nav-scope-count,
.folder-nav-tags-panel .folder-filter-all.on .nav-scope-count {
  color: #7c8a9e;
}

/* Строка «Все метки (N)» — одной линией, без переноса «Все / метки» */
.folder-nav-tags-panel .nav-scope-tags-all-btn {
  min-width: 0;
  flex-wrap: nowrap;
  justify-content: flex-start;
}
.folder-nav-tags-panel .nav-scope-tags-all-btn .nav-scope-tags-heading {
  flex: 1 1 auto;
  min-width: 0;
  text-align: left;
}
.nowrap-scope-heading {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
.nav-scope-tags-heading {
  font-weight: 600;
  font-size: 0.8125rem;
  letter-spacing: -0.02em;
  color: #111827;
}
.folder-nav-tags-panel .folder-filter-all.on .nav-scope-tags-heading {
  color: #111827;
}
.folder-nav-tags-panel .folder-filter-all.on .nav-scope-tags-count {
  color: #7c8a9e;
}
.nav-scope-tags-count {
  font-weight: 500;
  font-size: 0.72rem;
  color: #94a3b8;
  opacity: 1;
  font-variant-numeric: tabular-nums;
}

.folder-nav-calendar-sticky .nav-scope-label {
  flex: 1;
  min-width: 0;
  text-align: left;
  align-self: center;
  padding: 0.32rem 0.45rem;
}
.folder-all-row--frame.tags-all-row-scope.folder-scope-notes-parent {
  overflow: visible;
}
.folder-scope-notes-parent.tags-all-row-scope:has(.nav-scope-tags-all-btn:hover),
.folder-scope-notes-parent.tags-all-row-scope:has(.tags-scope-only-wrap:hover),
.folder-scope-notes-parent.tags-all-row-scope:has(.tags-scope-only-wrap:focus-within) {
  z-index: 2;
  position: relative;
}
.tags-scope-only-wrap {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  padding: 0 2px 0 4px;
  margin: 0;
  cursor: pointer;
  user-select: none;
  align-self: stretch;
  opacity: 1;
  pointer-events: auto;
}
.tags-scope-only-wrap input {
  margin: 0;
  cursor: pointer;
  width: 13px;
  height: 13px;
  flex-shrink: 0;
  accent-color: var(--accent, #2563eb);
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
.folder-nav-calendar-block {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.folder-nav-calendar-sticky {
  flex-shrink: 0;
  padding: 0.35rem 0.4rem 0.25rem;
  border-top: 1px solid #eceef2;
  background: transparent;
}
.folder-nav-folders-scroll--collapsed,
.folder-nav-tags-scroll--collapsed {
  flex: 0 0 0 !important;
  min-height: 0 !important;
  max-height: 0 !important;
  overflow: hidden !important;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
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
.folder-nav-tags-sticky {
  padding: 0.26rem 0.32rem 0.18rem;
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
.folder-nav-tags-scroll {
  padding: 0.16rem 0.26rem 0.2rem;
  gap: 2px;
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
  gap: 0.18rem;
}
.tag-sidebar-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
}
.folder-nav-tags-panel .nav-row.tag-sidebar-row {
  padding: 0.18rem 0.28rem;
  gap: 0.12rem;
  border-radius: 5px;
}
.folder-nav-tags-panel .nav-row.tag-sidebar-row .nav-row-label {
  font-size: 0.68rem;
  line-height: 1.28;
}
.folder-nav-tags-panel .nav-row.tag-sidebar-row .nav-row.on .nav-row-label {
  font-size: 0.68rem;
}
.folder-nav-tags-panel .nav-row.tag-sidebar-row .tag-count {
  font-size: 0.58rem;
  line-height: 1.15;
}
.folder-nav-tags-panel .section-chevron,
.folder-nav-tags-panel .section-chevron-spacer {
  width: 1.12rem;
  min-height: 1.42rem;
  font-size: 0.6rem;
}
.folder-nav-tags-panel .folder-filter-all.tag-filter {
  min-height: 0;
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
.folder-nav-tags-panel .tag-chevron {
  width: 0.95rem;
  min-width: 0.95rem;
  font-size: 0.55rem;
  line-height: 1.25;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.folder-nav-tags-panel .tag-chevron-spacer {
  width: 0.95rem;
  min-width: 0.95rem;
}
.nav-row-actions--tag-filter {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.nav-row-actions--folder-filter {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.folder-nav-tags-panel .btn-tag-filter-plus,
.folder-nav-tags-panel .btn-tag-filter-minus,
.folder-nav-folders-scroll .btn-tag-filter-plus,
.folder-nav-folders-scroll .btn-tag-filter-minus {
  box-sizing: border-box;
  flex-shrink: 0;
  width: 1rem;
  min-width: 1rem;
  height: 1rem;
  min-height: 1rem;
  padding: 0;
  border-radius: 4px;
  border: 1px solid rgba(148, 163, 184, 0.5);
  background: #fff;
  cursor: pointer;
  font-size: 0.68rem;
  font-weight: 700;
  line-height: 1;
  color: #64748b;
}
.folder-nav-tags-panel .btn-tag-filter-plus:hover:not(.on),
.folder-nav-folders-scroll .btn-tag-filter-plus:hover:not(.on) {
  border-color: rgba(37, 99, 235, 0.35);
  color: var(--accent, #2563eb);
  background: rgba(239, 246, 255, 0.6);
}
.folder-nav-tags-panel .btn-tag-filter-plus.on,
.folder-nav-folders-scroll .btn-tag-filter-plus.on {
  border-color: rgba(37, 99, 235, 0.62);
  background: rgba(37, 99, 235, 0.2);
  color: #1d4ed8;
  box-shadow: inset 0 0 0 1px rgba(37, 99, 235, 0.12);
}
.folder-nav-tags-panel .btn-tag-filter-minus:hover:not(.on),
.folder-nav-folders-scroll .btn-tag-filter-minus:hover:not(.on) {
  border-color: rgba(220, 38, 38, 0.38);
  color: var(--danger);
  background: rgba(254, 242, 242, 0.75);
}
.folder-nav-tags-panel .btn-tag-filter-minus.on,
.folder-nav-folders-scroll .btn-tag-filter-minus.on {
  border-color: rgba(220, 38, 38, 0.58);
  background: rgba(254, 202, 202, 0.65);
  color: #b91c1c;
  box-shadow: inset 0 0 0 1px rgba(220, 38, 38, 0.12);
}
.folder-nav-folders-scroll .nav-row.folder-sidebar-row.folder-sidebar-row--exclude {
  background: rgba(254, 226, 226, 0.45);
  border-color: rgba(220, 38, 38, 0.28);
}
.folder-nav-folders-scroll .nav-row.folder-sidebar-row.folder-sidebar-row--exclude .folder-label {
  font-weight: 600;
  color: #991b1b;
}
.folder-nav-folders-scroll .nav-row.folder-sidebar-row.folder-sidebar-row--exclude .tag-count {
  opacity: 0.9;
  color: #b91c1c;
}
.folder-nav-tags-panel .nav-row.tag-sidebar-row.tag-sidebar-row--exclude {
  background: rgba(254, 226, 226, 0.45);
  border-color: rgba(220, 38, 38, 0.28);
}
.folder-nav-tags-panel .nav-row.tag-sidebar-row.tag-sidebar-row--exclude .nav-row-label--tag {
  color: #991b1b;
}
.folder-nav-tags-panel .nav-row.tag-sidebar-row.tag-sidebar-row--exclude .tag-sidebar-name {
  font-weight: 600;
  color: #991b1b;
}
.folder-nav-tags-panel .nav-row.tag-sidebar-row.tag-sidebar-row--exclude .tag-count {
  opacity: 0.9;
  color: #b91c1c;
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
  padding: 0.42rem 0.6rem 0.42rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.25);
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
  flex: 1 1 8.5rem;
  min-width: 0;
  max-width: 15rem;
  padding: 0.34rem 0.45rem;
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
.list > li {
  min-width: 0;
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
  min-width: 0;
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
  overflow-wrap: anywhere;
  word-break: break-word;
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
  overflow-wrap: anywhere;
  word-break: break-word;
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
.workspace--narrow .header-toolbar {
  flex-wrap: nowrap;
  flex: 1 1 auto;
  gap: 0.35rem;
  min-width: 0;
}
.workspace--narrow .header-search-block {
  flex: 1 1 auto;
  min-width: 0;
  flex-direction: column;
  align-items: stretch;
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
