<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import NoteEditorColumn from '../components/NoteEditorColumn.vue'
import AppSectionNav from '../components/AppSectionNav.vue'
import { errMessage, foldersApi, notesApi, tagsApi } from '../api/client'
import type { Folder, Note, Tag } from '../api/types'
import { useAuthStore } from '../stores/auth'
import { fmtCompactMsk } from '../utils/datetime'
import { DEFAULT_NOTE_TITLE } from '../utils/noteDefaults'
import { noteBodyPreview, noteRowTooltip, sortNotes, type NoteSort } from '../utils/noteList'
import { useNoteLayout } from '../composables/useNoteLayout'
import { useTheme } from '../composables/useTheme'
import {
  isTagAttachDragTypes,
  MIME_TAG_ID,
  MIME_TAG_IDS_JSON,
  readDroppedTagIds,
} from '../utils/dndTags'
import {
  isStrictDescendantOf,
  tagsWithChildrenSet,
  visibleTagsForNav,
} from '../utils/tagsTree'

/** Порядок PATCH при групповом переносе: сначала более глубокие узлы. */
function sortTagIdsByDepthDesc(flat: Tag[], ids: string[]): string[] {
  const byId = new Map(flat.map((x) => [x.id, x]))
  function depthOf(id: string): number {
    let d = 0
    let cur: string | null = id
    const seen = new Set<string>()
    while (cur != null && !seen.has(cur)) {
      seen.add(cur)
      d += 1
      const next: string | null = byId.get(cur)?.parent_id ?? null
      cur = next
    }
    return d
  }
  return [...ids].sort((a, b) => depthOf(b) - depthOf(a))
}

const TAG_ASIDE_W_KEY = 'note-ui-tags-aside-w'
const TAG_LIST_W_KEY = 'note-ui-tags-list-w'
const TAG_ASIDE_SPLIT_H_KEY = 'note-ui-tags-aside-split-h'
const TAG_NAV_COLLAPSED_KEY = 'note-ui-tag-collapsed'

function readStoredNumber(key: string, fallback: number, min: number, max: number): number {
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

const colAsidePx = ref(readStoredNumber(TAG_ASIDE_W_KEY, 272, 200, 440))
const colListPx = ref(readStoredNumber(TAG_LIST_W_KEY, 300, 180, 640))
const asideFilterBlockPx = ref(readStoredNumber(TAG_ASIDE_SPLIT_H_KEY, 220, 96, 520))

const asideNavRef = ref<HTMLElement | null>(null)

type GutterDrag = null | 'aside' | 'list' | 'asideV'
const gutterDrag = ref<GutterDrag>(null)
let gutterStartX = 0
let gutterStartAside = 0
let gutterStartList = 0
let gutterStartY = 0
let gutterStartAsideFilterH = 0

function persistLayout() {
  try {
    localStorage.setItem(TAG_ASIDE_W_KEY, String(colAsidePx.value))
    localStorage.setItem(TAG_LIST_W_KEY, String(colListPx.value))
    localStorage.setItem(TAG_ASIDE_SPLIT_H_KEY, String(asideFilterBlockPx.value))
  } catch {
    /* */
  }
}

function onGutterDown(which: 'aside' | 'list', e: MouseEvent) {
  e.preventDefault()
  gutterDrag.value = which
  gutterStartX = e.clientX
  gutterStartAside = colAsidePx.value
  gutterStartList = colListPx.value
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('mousemove', onGutterMove)
  window.addEventListener('mouseup', onGutterUp)
}

function asideFilterMax(): number {
  const nav = asideNavRef.value
  if (!nav) return 520
  const minManage = 120
  const GUTTER = 6
  return Math.max(96, nav.clientHeight - minManage - GUTTER)
}

function onAsideVGutterDown(e: MouseEvent) {
  e.preventDefault()
  gutterDrag.value = 'asideV'
  gutterStartY = e.clientY
  gutterStartAsideFilterH = asideFilterBlockPx.value
  document.body.style.cursor = 'row-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('mousemove', onGutterMove)
  window.addEventListener('mouseup', onGutterUp)
}

function onGutterMove(e: MouseEvent) {
  if (!gutterDrag.value) return
  if (gutterDrag.value === 'asideV') {
    const dy = e.clientY - gutterStartY
    const maxH = asideFilterMax()
    asideFilterBlockPx.value = Math.min(maxH, Math.max(96, gutterStartAsideFilterH + dy))
    return
  }
  const dx = e.clientX - gutterStartX
  if (gutterDrag.value === 'aside') {
    colAsidePx.value = Math.min(440, Math.max(200, gutterStartAside + dx))
  } else {
    colListPx.value = Math.min(640, Math.max(180, gutterStartList + dx))
  }
}

function onGutterUp() {
  const was = gutterDrag.value
  gutterDrag.value = null
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  window.removeEventListener('mousemove', onGutterMove)
  window.removeEventListener('mouseup', onGutterUp)
  if (was === 'asideV') {
    const maxH = asideFilterMax()
    asideFilterBlockPx.value = Math.min(maxH, Math.max(96, asideFilterBlockPx.value))
  }
  persistLayout()
}

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const { label: themeLabel, icon: themeIcon, cycleTheme } = useTheme()
const { innerScroll, setInnerScroll } = useNoteLayout()

const tags = ref<Tag[]>([])
const tagCountById = ref<Record<string, number>>({})
const name = ref('')
/** Только первый запрос списка меток скрывает дерево; последующие load() обновляют данные без мигания. */
const initialTagsLoading = ref(true)
const notesLoading = ref(false)
const error = ref('')

const selectedTagId = ref<string | null>(null)
const activeNoteId = ref<string | null>(null)
/** Синхронизация редактора при DnD метки на строку заметки (как в NotesView). */
const editorSyncSignal = ref(0)
const notes = ref<Note[]>([])
const folders = ref<Folder[]>([])

/** Id меток в перетаскивании (подсветка строк). */
const dragPayloadIds = ref<string[]>([])
/** Копия нагрузки на время DnD — drop читает её, если dragend успел обнулить dragPayloadIds. */
const dragOperationIds = ref<string[] | null>(null)
const structureDragDropDone = ref(false)
const dropHintId = ref<string | null>(null)
/** Мультивыбор в блоке «Структура» (Ctrl/Cmd + клик). */
const structureMultiSelection = ref<Set<string>>(new Set())

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

/** Структура для DnD: тот же порядок и свёртки, что и в списке меток выше. */
const treeRows = computed(() => visibleTagsForNav(tags.value, collapsedTagIds.value))

const asideFilterStyle = computed(() => ({
  flex: '0 0 auto' as const,
  height: `${asideFilterBlockPx.value}px`,
  minHeight: '96px',
  overflowY: 'auto' as const,
}))

const asideManageStyle = computed(() => ({
  flex: '1 1 auto',
  minHeight: '0',
  overflowY: 'auto' as const,
}))

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
  const fid = selectedTagId.value
  if (willCollapse && fid && isStrictDescendantOf(tags.value, tagId, fid)) {
    pickTagFromSidebar(null)
  }
}

function isDescendantOf(ancestorId: string, tagId: string): boolean {
  let cur: string | null = tagId
  const byId = new Map(tags.value.map((t) => [t.id, t]))
  while (cur) {
    if (cur === ancestorId) return true
    cur = byId.get(cur)?.parent_id ?? null
  }
  return false
}

/** Сразу показать перенос в дереве; при ошибке API последующий load() откатит. */
function applyReparentLocal(childIds: string[], newParentId: string | null) {
  const set = new Set(childIds)
  let next = tags.value.map((t) => (set.has(t.id) ? { ...t, parent_id: newParentId } : t))
  const byId = new Map(next.map((t) => [t.id, t]))
  function depthOf(id: string, stack = new Set<string>()): number {
    if (stack.has(id)) return 1
    stack.add(id)
    const t = byId.get(id)
    if (!t) return 1
    const p = t.parent_id
    if (p == null) return 1
    return 1 + depthOf(String(p), stack)
  }
  next = next.map((t) => ({ ...t, depth: depthOf(t.id) }))
  tags.value = next
}

async function loadFolders() {
  try {
    folders.value = await foldersApi.list()
  } catch (e) {
    error.value = errMessage(e)
  }
}

async function load() {
  error.value = ''
  try {
    const [list, counts] = await Promise.all([tagsApi.list(), tagsApi.noteCounts()])
    tags.value = Array.isArray(list) ? [...list] : []
    const map: Record<string, number> = {}
    for (const c of counts) {
      map[String(c.tag_id)] = c.count
    }
    tagCountById.value = { ...map }
    if (selectedTagId.value && !tags.value.some((t) => t.id === selectedTagId.value)) {
      selectedTagId.value = null
      activeNoteId.value = null
      structureMultiSelection.value = new Set()
      syncQuery()
    }
    await nextTick()
  } catch (e) {
    error.value = errMessage(e)
    try {
      const fallback = await tagsApi.list()
      tags.value = Array.isArray(fallback) ? [...fallback] : []
    } catch {
      tags.value = []
    }
  } finally {
    initialTagsLoading.value = false
  }
}

async function loadNotes() {
  if (!selectedTagId.value) {
    notes.value = []
    return
  }
  notesLoading.value = true
  error.value = ''
  try {
    const list = await notesApi.list({ tag_id: selectedTagId.value })
    notes.value = Array.isArray(list) ? [...list] : []
    if (activeNoteId.value && !notes.value.some((n) => n.id === activeNoteId.value)) {
      activeNoteId.value = null
      syncQuery()
    }
    await nextTick()
  } catch (e) {
    error.value = errMessage(e)
    notes.value = []
  } finally {
    notesLoading.value = false
  }
}

function syncQuery() {
  const q: Record<string, string> = {}
  if (selectedTagId.value) q.tag = selectedTagId.value
  if (activeNoteId.value) q.note = activeNoteId.value
  void router.replace({ name: 'tags', query: Object.keys(q).length ? q : {} })
}

function pickTag(id: string | null) {
  selectedTagId.value = id
  activeNoteId.value = null
  syncQuery()
}

/** Выбор метки из верхнего фильтра — сбрасывает мультивыделение в структуре. */
function pickTagFromSidebar(id: string | null) {
  structureMultiSelection.value = new Set()
  pickTag(id)
}

function onStructureRowClick(t: Tag, e: MouseEvent) {
  if (e.ctrlKey || e.metaKey) {
    e.preventDefault()
    const prev = structureMultiSelection.value
    const next = new Set(prev)
    if (next.has(t.id)) {
      next.delete(t.id)
      structureMultiSelection.value = next
      if (selectedTagId.value === t.id) {
        const rest = [...next]
        pickTag(rest[0] ?? null)
      }
    } else {
      next.add(t.id)
      structureMultiSelection.value = next
      // Первый Ctrl+клик с пустым выделением — как первая выбранная метка (фильтр + в наборе для DnD).
      if (prev.size === 0) pickTag(t.id)
    }
    return
  }
  structureMultiSelection.value = new Set([t.id])
  pickTag(t.id)
}

function isRowDragging(tid: string): boolean {
  return dragPayloadIds.value.includes(tid)
}

function isStructureMultiSelected(tid: string): boolean {
  return structureMultiSelection.value.has(tid)
}

function getDragPayloadIds(t: Tag): string[] {
  const sel = structureMultiSelection.value
  /* Есть мультивыделение — всегда тащим все выбранные метки (любая строка-«ручка»). */
  if (sel.size > 0) {
    return sortTagIdsByDepthDesc(tags.value, [...sel])
  }
  return [t.id]
}

function getActiveDragPayload(): string[] {
  const op = dragOperationIds.value
  if (op?.length) return op
  return dragPayloadIds.value
}

function endStructureDragSession() {
  dragOperationIds.value = null
  dragPayloadIds.value = []
  dropHintId.value = null
}

function readPayloadFromDrag(e: DragEvent): string[] {
  const refIds = dragOperationIds.value
  if (refIds?.length) return [...new Set(refIds)]
  const raw = e.dataTransfer?.getData('text/plain') || ''
  if (raw) {
    try {
      const arr = JSON.parse(raw) as unknown
      if (Array.isArray(arr)) {
        const out = arr.map(String).filter(Boolean)
        if (out.length) return [...new Set(out)]
      }
    } catch {
      /* */
    }
  }
  return []
}

function bumpEditorIfOpen(noteId: string) {
  if (noteId === activeNoteId.value) editorSyncSignal.value++
}

function onFilterTagDragStart(e: DragEvent, tagId: string) {
  e.stopPropagation()
  e.dataTransfer?.setData(MIME_TAG_ID, tagId)
  e.dataTransfer?.setData(MIME_TAG_IDS_JSON, JSON.stringify([tagId]))
  e.dataTransfer!.effectAllowed = 'copy'
}

function onNoteTagAttachDragOver(e: DragEvent) {
  const types = e.dataTransfer?.types ? [...e.dataTransfer.types] : []
  if (!isTagAttachDragTypes(types)) return
  e.preventDefault()
  e.dataTransfer!.dropEffect = 'copy'
}

async function onNoteTagAttachDrop(e: DragEvent, noteId: string) {
  e.preventDefault()
  const tagIds = readDroppedTagIds(e)
  if (!tagIds.length) return
  try {
    for (const tagId of tagIds) {
      await notesApi.attachTag(noteId, tagId)
    }
    error.value = ''
    await load()
    await loadNotes()
    bumpEditorIfOpen(noteId)
  } catch (err) {
    error.value = errMessage(err)
  }
}

function openNote(id: string) {
  activeNoteId.value = id
  syncQuery()
}

function applyRouteQuery() {
  structureMultiSelection.value = new Set()
  const t = route.query.tag
  const n = route.query.note
  if (typeof t === 'string') {
    selectedTagId.value = t
  } else {
    selectedTagId.value = null
  }
  if (typeof n === 'string') {
    activeNoteId.value = n
  } else {
    activeNoteId.value = null
  }
}

const noteSort = ref<NoteSort>('updated_desc')

const sortedNotes = computed(() => sortNotes(notes.value, noteSort.value))

type TagNoteRowView = {
  id: string
  note: Note
  title: string
  preview: string
  tooltip: string
  folderName: string
}

/** Как в разделе «Заметки»: строки списка считаем один раз, а не в шаблоне на каждый рендер. */
const noteRows = computed<TagNoteRowView[]>(() => {
  const folderNameById = new Map(folders.value.map((f) => [f.id, f.name]))
  return sortedNotes.value.map((n) => ({
    id: n.id,
    note: n,
    title: n.title || DEFAULT_NOTE_TITLE,
    preview: noteBodyPreview(n),
    tooltip: noteRowTooltip(n),
    folderName: n.folder_id ? (folderNameById.get(n.folder_id) ?? '') : '',
  }))
})

const sortedNoteIds = computed(() => sortedNotes.value.map((n) => n.id))

function tagNameTakenGlobally(raw: string): boolean {
  const n = raw.trim().toLowerCase()
  if (!n) return false
  return tags.value.some((t) => t.name.trim().toLowerCase() === n)
}

function tagNameTakenByOtherTag(raw: string, excludeTagId: string): boolean {
  const n = raw.trim().toLowerCase()
  if (!n) return false
  return tags.value.some(
    (t) => t.id !== excludeTagId && t.name.trim().toLowerCase() === n
  )
}

async function renameTag(t: Tag) {
  const current = prompt('Новое имя метки', t.name)
  if (current == null) return
  const trimmed = current.trim()
  if (!trimmed) return
  if (trimmed === t.name) return
  if (tagNameTakenByOtherTag(trimmed, t.id)) {
    error.value = 'Метка с таким именем уже существует'
    return
  }
  try {
    error.value = ''
    const updated = await tagsApi.update(t.id, { name: trimmed })
    tags.value = tags.value.map((x) => (x.id === updated.id ? updated : x))
    await load()
    await loadNotes()
  } catch (e) {
    error.value = errMessage(e)
    await load()
  }
}

async function create() {
  if (!name.value.trim()) return
  const parentId = selectedTagId.value?.trim() || null
  if (tagNameTakenGlobally(name.value)) {
    error.value = 'Метка с таким именем уже существует'
    return
  }
  try {
    error.value = ''
    const created = await tagsApi.create({
      name: name.value.trim(),
      parent_id: parentId,
    })
    name.value = ''
    await load()
    // Не переключаем фильтр на созданную метку — иначе следующая «+» уйдёт вложенной в неё.
    structureMultiSelection.value = new Set([created.id])
    await nextTick()
    document.getElementById(`tag-row-${created.id}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  } catch (e) {
    error.value = errMessage(e)
  }
}

async function createNote() {
  if (!selectedTagId.value) {
    error.value = 'Сначала выберите метку слева'
    return
  }
  try {
    error.value = ''
    const n = await notesApi.create({
      title: DEFAULT_NOTE_TITLE,
      content_json: '{}',
      content_plain: '',
    })
    await notesApi.attachTag(n.id, selectedTagId.value)
    await load()
    await loadNotes()
    openNote(n.id)
  } catch (e) {
    error.value = errMessage(e)
  }
}

function pruneStructureSelectionToExistingTags() {
  const ids = new Set(tags.value.map((x) => x.id))
  const next = new Set<string>()
  for (const id of structureMultiSelection.value) {
    if (ids.has(id)) next.add(id)
  }
  structureMultiSelection.value = next
}

async function remove(t: Tag) {
  if (!confirm(`Удалить метку «${t.name}»? Дочерние станут на ступень выше.`)) return
  const removedId = t.id
  const promoteTo = t.parent_id
  try {
    await tagsApi.remove(removedId)
    const next = new Set(structureMultiSelection.value)
    next.delete(removedId)
    structureMultiSelection.value = next
    if (selectedTagId.value === removedId) pickTagFromSidebar(null)
    /* Сразу убираем из списка и поднимаем прямых потомков — без ожидания GET (как в списке папок). */
    tags.value = tags.value
      .filter((x) => x.id !== removedId)
      .map((x) => (x.parent_id === removedId ? { ...x, parent_id: promoteTo } : x))
    await load()
    pruneStructureSelectionToExistingTags()
    await loadNotes()
  } catch (e) {
    error.value = errMessage(e)
    await load()
  }
}

async function setParent(childId: string, newParentId: string | null) {
  if (childId === newParentId) return
  if (newParentId && isDescendantOf(childId, newParentId)) {
    error.value = 'Нельзя вложить метку саму в себя'
    return
  }
  error.value = ''
  applyReparentLocal([childId], newParentId)
  try {
    await tagsApi.update(childId, { parent_id: newParentId })
    await load()
  } catch (e) {
    error.value = errMessage(e)
    await load()
  }
}

async function setParentBatch(childIds: string[], newParentId: string | null) {
  const uniq = [...new Set(childIds)]
  const toMove: string[] = []
  for (const childId of uniq) {
    if (childId === newParentId) continue
    if (newParentId && isDescendantOf(childId, newParentId)) {
      error.value = 'Нельзя вложить метку внутрь выбранной ветки'
      return
    }
    toMove.push(childId)
  }
  error.value = ''
  const ordered = sortTagIdsByDepthDesc(tags.value, toMove)
  applyReparentLocal(ordered, newParentId)
  try {
    for (const childId of ordered) {
      await tagsApi.update(childId, { parent_id: newParentId })
    }
    await load()
  } catch (e) {
    error.value = errMessage(e)
    await load()
  }
}

function onDragStart(t: Tag, e: DragEvent) {
  structureDragDropDone.value = false
  const ids = getDragPayloadIds(t)
  dragOperationIds.value = ids
  dragPayloadIds.value = ids
  try {
    e.dataTransfer?.setData('text/plain', JSON.stringify(ids))
  } catch {
    e.dataTransfer?.setData('text/plain', (ids[0] ?? t.id) || '')
  }
  e.dataTransfer?.setData(MIME_TAG_ID, ids[0] ?? t.id)
  e.dataTransfer?.setData(MIME_TAG_IDS_JSON, JSON.stringify(ids))
  e.dataTransfer!.effectAllowed = 'move'
}

function onDragEnd() {
  if (!structureDragDropDone.value) {
    endStructureDragSession()
  }
  structureDragDropDone.value = false
}

function canDropPayloadOnTarget(targetId: string): boolean {
  const payload = getActiveDragPayload()
  if (!payload.length) return false
  return payload.every((id) => id !== targetId && !isDescendantOf(id, targetId))
}

function onDragOverRow(t: Tag, e: DragEvent) {
  e.preventDefault()
  if (!canDropPayloadOnTarget(t.id)) {
    e.dataTransfer!.dropEffect = 'none'
    return
  }
  dropHintId.value = t.id
  e.dataTransfer!.dropEffect = 'move'
}

function onDragLeaveRow(t: Tag) {
  if (dropHintId.value === t.id) dropHintId.value = null
}

async function onDropOnRow(t: Tag, e: DragEvent) {
  e.preventDefault()
  e.stopPropagation()
  structureDragDropDone.value = true
  const payload = readPayloadFromDrag(e)
  endStructureDragSession()
  if (!payload.length) return
  if (payload.length === 1) await setParent(payload[0], t.id)
  else await setParentBatch(payload, t.id)
}

function onDragOverRoot(e: DragEvent) {
  e.preventDefault()
  if (!getActiveDragPayload().length) {
    e.dataTransfer!.dropEffect = 'none'
    return
  }
  dropHintId.value = '__root__'
  e.dataTransfer!.dropEffect = 'move'
}

function onDragLeaveRoot() {
  if (dropHintId.value === '__root__') dropHintId.value = null
}

async function onDropRoot(e: DragEvent) {
  e.preventDefault()
  e.stopPropagation()
  structureDragDropDone.value = true
  const payload = readPayloadFromDrag(e)
  endStructureDragSession()
  if (!payload.length) return
  if (payload.length === 1) await setParent(payload[0], null)
  else await setParentBatch(payload, null)
}

function logout() {
  auth.logout()
  router.push('/login')
}

/** За одно действие в редакторе просьб обновиться приходит несколько — склеиваем в одну. */
let editorRefreshTimer: ReturnType<typeof setTimeout> | null = null
function onEditorRefresh() {
  if (editorRefreshTimer) clearTimeout(editorRefreshTimer)
  editorRefreshTimer = setTimeout(() => {
    editorRefreshTimer = null
    void (async () => {
      await load()
      await loadNotes()
    })()
  }, 150)
}

watch(selectedTagId, () => {
  void loadNotes()
})

onMounted(async () => {
  await loadFolders()
  await load()
  applyRouteQuery()
  if (selectedTagId.value) await loadNotes()
})

watch(
  () => route.fullPath,
  () => {
    applyRouteQuery()
  }
)

onBeforeUnmount(() => {
  if (editorRefreshTimer) clearTimeout(editorRefreshTimer)
  editorRefreshTimer = null
  window.removeEventListener('mousemove', onGutterMove)
  window.removeEventListener('mouseup', onGutterUp)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
})
</script>

<template>
  <div class="workspace" :class="{ 'workspace--fit': innerScroll }">
    <header class="workspace-header">
      <div class="header-left">
        <button
          type="button"
          class="logo logo-wordmark logo-home-btn"
          lang="ru"
          @click="router.push({ name: 'notes' })"
        >
          <span class="logo-brand"><span class="logo-brand-accent">Em</span><span class="logo-brand-dash">-</span><span>Note</span></span>
        </button>
      </div>
      <div class="actions">
        <button
          type="button"
          class="btn primary"
          :disabled="!selectedTagId"
          :title="!selectedTagId ? 'Выберите метку' : ''"
          @click="createNote"
        >
          Новая в метке
        </button>
      </div>
      <div class="header-end">
        <label
          class="note-fit-toggle"
          title="Заметка на высоту экрана: шапка и доступы всегда видны, скролл внутри текста"
        >
          <input
            type="checkbox"
            :checked="innerScroll"
            @change="setInnerScroll(($event.target as HTMLInputElement).checked)"
          />
          <span class="note-fit-toggle-text">Скролл в заметке</span>
        </label>
        <AppSectionNav active="tags" />
        <div class="header-user">
          <span v-if="auth.user" class="user">{{ auth.user.email }}</span>
          <button
            type="button"
            class="theme-toggle"
            :aria-label="themeLabel"
            :title="themeLabel"
            @click="cycleTheme"
          >
            <span class="theme-toggle-glyph" aria-hidden="true">{{ themeIcon }}</span>
          </button>
          <button type="button" class="btn ghost" @click="logout">Выйти</button>
        </div>
      </div>
    </header>

    <div class="workspace-body">
      <aside
        class="tags-aside sidebar-panel"
        :style="{ width: colAsidePx + 'px', flexShrink: 0 }"
      >
        <p v-if="error && !initialTagsLoading" class="err aside-err">{{ error }}</p>
        <div ref="asideNavRef" class="aside-inner-nav">
          <div class="aside-block">
            <h2 class="aside-title">Фильтр по метке</h2>
          </div>
          <div class="tag-filter-block" :style="asideFilterStyle">
            <p v-if="initialTagsLoading" class="muted small-pad">Загрузка меток…</p>
            <template v-else>
              <button
                type="button"
                class="folder-filter tag-filter"
                :class="{ on: selectedTagId === null }"
                @click="pickTagFromSidebar(null)"
              >
                Выберите метку…
              </button>
              <button
                v-for="t in tagsVisibleInSidebar"
                :key="t.id"
                type="button"
                class="folder-filter tag-filter tag-sidebar-row"
                :class="{ on: selectedTagId === t.id }"
                :style="{ paddingLeft: (0.35 + Math.max(0, t.depth - 1) * 0.55) + 'rem' }"
                draggable="true"
                @dragstart="onFilterTagDragStart($event, t.id)"
                @click="pickTagFromSidebar(t.id)"
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
            </template>
          </div>
          <div
            class="folder-nav-v-gutter"
            title="Потяните: больше места для списка меток или для структуры"
            @mousedown="onAsideVGutterDown($event)"
          />
          <div class="aside-manage" :style="asideManageStyle">
            <h2 class="aside-title manage-title">Структура</h2>
            <form class="create" @submit.prevent="create">
              <input
                v-model="name"
                :placeholder="
                  selectedTagId
                    ? `Новая метка внутри «${tags.find((x) => x.id === selectedTagId)?.name ?? '…'}»`
                    : 'Новая метка в корень'
                "
              />
              <button type="submit" class="btn-sm primary" aria-label="Добавить метку" title="Добавить метку">+</button>
            </form>
            <p class="muted small structure-hint">
              Стрелка — свернуть ветку. Ctrl+клик — выделить несколько; перетащите любую из них на цель
              или в «В корень» — перенесутся все выделенные.
            </p>
            <div
              class="drop-root"
              :class="{ 'drop-active': dropHintId === '__root__' }"
              @dragover="onDragOverRoot"
              @dragleave="onDragLeaveRoot"
              @drop="onDropRoot"
            >
              В корень
            </div>
            <ul v-if="!initialTagsLoading" class="tree compact-tree">
              <li
                v-for="t in treeRows"
                :key="t.id"
                :id="`tag-row-${t.id}`"
                class="row"
                :class="{
                  hilite: selectedTagId === t.id,
                  'structure-multi': isStructureMultiSelected(t.id),
                  dragging: isRowDragging(t.id),
                  'drop-target': dropHintId === t.id,
                }"
                :style="{ paddingLeft: `${Math.max(0, t.depth - 1) * 12}px` }"
                draggable="true"
                @dragstart="onDragStart(t, $event)"
                @dragend="onDragEnd"
                @dragover="onDragOverRow(t, $event)"
                @dragleave="onDragLeaveRow(t)"
                @drop="onDropOnRow(t, $event)"
                @click="onStructureRowClick(t, $event)"
              >
                <span
                  v-if="tagsWithKids.has(t.id)"
                  draggable="false"
                  class="tag-chevron structure-chevron"
                  title="Свернуть / развернуть вложенные"
                  role="button"
                  tabindex="0"
                  @click="toggleTagNavCollapse(t.id, $event)"
                  @keydown.enter.prevent="toggleTagNavCollapse(t.id, $event)"
                  @keydown.space.prevent="toggleTagNavCollapse(t.id, $event)"
                >
                  {{ collapsedTagIds[t.id] ? '▸' : '▾' }}
                </span>
                <span
                  v-else
                  draggable="false"
                  class="tag-chevron tag-chevron-spacer structure-chevron"
                  aria-hidden="true"
                />
                <span draggable="false" class="drag-hint" title="Перетащить (все выделенные — Ctrl+клик)">
                  ⠿
                </span>
                <span draggable="false" class="name">{{ t.name }}</span>
                <span draggable="false" class="note-count-badge">{{ tagCountById[t.id] ?? 0 }}</span>
                <button
                  type="button"
                  draggable="false"
                  class="tag-rename-btn"
                  aria-label="Переименовать метку"
                  title="Переименовать"
                  @click.stop="renameTag(t)"
                >
                  ✎
                </button>
                <button
                  type="button"
                  draggable="false"
                  class="linkish"
                  aria-label="Удалить метку"
                  title="Удалить метку"
                  @click.stop="remove(t)"
                >
                  ×
                </button>
              </li>
            </ul>
          </div>
        </div>
      </aside>

      <div
        class="col-gutter"
        title="Ширина колонки меток"
        @mousedown="onGutterDown('aside', $event)"
      />

      <div class="notes-list-col" :style="{ width: colListPx + 'px', flexShrink: 0 }">
        <div class="list-toolbar">
          <label class="sort-lab" for="tag-note-sort">Сортировка</label>
          <select id="tag-note-sort" v-model="noteSort" class="sort-select">
            <option value="updated_desc">Изменение — новые сверху</option>
            <option value="updated_asc">Изменение — старые сверху</option>
            <option value="created_desc">Создание — новые сверху</option>
            <option value="created_asc">Создание — старые сверху</option>
            <option value="title_asc">Название А → Я</option>
            <option value="title_desc">Название Я → А</option>
          </select>
        </div>
        <div class="list-scroll">
          <p v-if="!selectedTagId" class="empty hint-pad">
            Выберите метку слева — здесь появятся все заметки с этой меткой.
          </p>
          <template v-else>
            <p v-if="notesLoading" class="muted load-hint">Загрузка заметок…</p>
            <ul v-else class="list">
              <li v-for="row in noteRows" :key="row.id">
                <button
                  type="button"
                  class="note-item"
                  :class="{ current: row.id === activeNoteId }"
                  :title="row.tooltip"
                  @click="openNote(row.id)"
                  @dragover="onNoteTagAttachDragOver"
                  @drop="onNoteTagAttachDrop($event, row.id)"
                >
                  <span class="note-title">{{ row.title }}</span>
                  <span v-if="row.preview" class="note-preview">{{ row.preview }}</span>
                  <span class="meta">
                    <span v-if="row.folderName" class="folder-badge">{{ row.folderName }}</span>
                    <span class="dates dates-compact">
                      <span class="date-bit"
                        ><span class="meta-prefix">Изм.</span
                        >{{ fmtCompactMsk(row.note.updated_at) }}</span
                      >
                    </span>
                  </span>
                </button>
              </li>
            </ul>
            <p v-if="!notesLoading && sortedNotes.length === 0" class="empty">
              Нет заметок с этой меткой.
            </p>
          </template>
        </div>
      </div>

      <div
        class="col-gutter"
        title="Ширина списка заметок"
        @mousedown="onGutterDown('list', $event)"
      />

      <div class="editor-shell">
        <NoteEditorColumn
          v-if="activeNoteId"
          :key="activeNoteId"
          :note-id="activeNoteId"
          :sorted-note-ids="sortedNoteIds"
          :editor-sync-signal="editorSyncSignal"
          @refresh="onEditorRefresh"
        />
        <div v-else class="editor-placeholder">
          <p class="ph-int">Выберите заметку в списке</p>
          <p v-if="selectedTagId" class="muted ph-sub">или создайте новую кнопкой «Новая в метке».</p>
        </div>
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
.workspace--fit {
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
}
.workspace-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem 1rem;
  padding: 0.5rem 1rem 0.55rem;
  border-bottom: 1px solid var(--border);
  background: var(--surface-translucent);
  backdrop-filter: blur(10px);
  flex-shrink: 0;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.logo {
  margin: 0;
  line-height: 1.05;
}
.logo-home-btn {
  display: inline-flex;
  background: transparent;
  border: none;
  padding: 0;
  cursor: pointer;
  font: inherit;
}
.logo-wordmark {
  font-family: 'Sora', 'Inter', system-ui, sans-serif;
  font-size: var(--fs-xl);
  font-weight: 700;
  letter-spacing: -0.055em;
  color: var(--text-1);
}
.logo-brand {
  display: inline-flex;
  align-items: baseline;
}
.logo-brand-accent {
  color: var(--accent-text);
  font-weight: 700;
}
.logo-brand-dash {
  color: var(--text-4);
  font-weight: 600;
  margin: 0 0.02em;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  flex: 1 1 auto;
  min-width: 0;
}
.header-user {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  padding-left: 0.85rem;
  border-left: 1px solid var(--border);
  flex-shrink: 0;
}
.user {
  font-family: inherit;
  font-size: var(--fs-2xs);
  font-weight: 400;
  line-height: var(--lh-tight);
  color: var(--text-muted);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* Базовые `.btn` и его варианты — в assets/ui.css. */
.btn-sm {
  padding: 0.28rem 0.44rem;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  font-weight: 600;
  font-size: var(--fs-2xs);
}
.btn-sm.primary {
  background: var(--accent);
  color: var(--text-on-accent);
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
  align-self: stretch;
  position: relative;
  z-index: 2;
}
.col-gutter:hover {
  background: var(--accent-subtle-hover);
}
.sidebar-panel {
  box-shadow: inset -1px 0 0 var(--shadow-tint-weak);
}
.tags-aside {
  border-right: 1px solid var(--border-subtle);
  background: linear-gradient(190deg, var(--surface-3) 0%, var(--surface-4) 100%);
  padding: 0.55rem 0.5rem;
  display: flex;
  flex-direction: column;
  min-height: 0;
  max-height: calc(100vh - 52px);
  overflow: hidden;
}
.aside-err {
  font-size: var(--fs-xs);
  color: var(--danger-text);
  margin: 0 0 0.35rem;
}
.aside-inner-nav {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  gap: 0;
}
.aside-block {
  flex-shrink: 0;
}
.aside-title {
  margin: 0 0 0.35rem;
  font-size: var(--fs-2xs);
  font-weight: 650;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-4);
}
.manage-title {
  margin-top: 0.15rem;
}
.tag-filter-block {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding-bottom: 0.25rem;
}
.small-pad {
  padding: 0.25rem 0.15rem;
}
.folder-nav-v-gutter {
  flex-shrink: 0;
  height: 6px;
  margin: 0 -0.1rem;
  border-radius: 3px;
  cursor: row-resize;
}
.folder-nav-v-gutter:hover {
  background: var(--accent-subtle-hover);
}
.aside-manage {
  border-top: 1px solid var(--border);
  padding-top: 0.35rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
.create {
  display: flex;
  gap: 0.3rem;
}
.create input {
  flex: 1;
  min-width: 0;
  padding: 0.32rem 0.4rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  font: inherit;
  font-size: var(--fs-2xs);
  background: var(--panel);
}
.drop-root {
  padding: 0.45rem 0.5rem;
  border: 2px dashed var(--border);
  border-radius: 8px;
  font-size: var(--fs-xs);
  color: var(--text-muted);
  text-align: center;
}
.drop-root.drop-active {
  border-color: var(--accent);
  color: var(--accent-text);
  background: var(--accent-subtle);
}
.compact-tree {
  list-style: none;
  margin: 0;
  padding: 0 0 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.row {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.3rem 0.4rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-veil);
  cursor: pointer;
  font-size: var(--fs-2xs);
}
.row.hilite {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent);
}
.row.structure-multi {
  background: var(--accent-subtle);
}
.row.structure-multi:not(.hilite) {
  border-color: var(--accent-border);
}
.row.structure-multi.hilite {
  box-shadow:
    0 0 0 1px var(--accent),
    0 0 0 3px var(--accent-ring);
}
.row.dragging {
  opacity: 0.55;
}
.structure-hint.small {
  margin: 0.35rem 0 0;
  font-size: var(--fs-2xs);
  line-height: var(--lh-normal);
}
.row.drop-target {
  border-color: var(--accent);
  background: var(--accent-subtle);
}
.drag-hint {
  cursor: grab;
  opacity: 0.4;
  user-select: none;
}
.name {
  font-weight: 500;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
.note-count-badge {
  font-size: var(--fs-2xs);
  font-weight: 600;
  padding: 0.06rem 0.28rem;
  border-radius: 6px;
  background: var(--accent-subtle-hover);
  color: var(--accent-text);
}
.tag-rename-btn {
  flex-shrink: 0;
  width: 1.35rem;
  height: 1.35rem;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: var(--fs-2xs);
  line-height: 1;
  padding: 0;
}
.tag-rename-btn:hover {
  color: var(--accent-text);
  background: var(--accent-subtle-hover);
}
.linkish {
  background: none;
  border: none;
  color: var(--danger-text);
  cursor: pointer;
  font: inherit;
  padding: 0 0.15rem;
}
.folder-filter {
  display: block;
  width: 100%;
  text-align: left;
  padding: 0.36rem 0.5rem;
  border: 1px solid transparent;
  border-radius: 10px;
  background: var(--surface-veil);
  cursor: pointer;
  font: inherit;
  font-size: var(--fs-2xs);
  color: var(--text-3);
}
.folder-filter:hover:not(.on) {
  background: var(--surface-translucent);
  border-color: var(--border);
}
.folder-filter.on {
  background: var(--surface-translucent);
  border-color: var(--accent-border);
  color: var(--accent-text);
  font-weight: 600;
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
  font-size: 0.62rem;
}
.tag-chevron {
  flex-shrink: 0;
  width: 1.2rem;
  text-align: center;
  font-size: var(--fs-2xs);
  color: var(--text-4);
  border-radius: 4px;
  cursor: pointer;
}
.tag-chevron-spacer {
  visibility: hidden;
  pointer-events: none;
}
.structure-chevron {
  flex-shrink: 0;
  align-self: center;
}
.tag-count {
  font-weight: 500;
  opacity: 0.72;
  flex-shrink: 0;
  margin-left: auto;
}
.notes-list-col {
  border-right: 1px solid var(--border-subtle);
  background: linear-gradient(180deg, var(--surface-2) 0%, var(--surface-canvas) 100%);
  display: flex;
  flex-direction: column;
  min-height: 0;
  max-height: calc(100vh - 52px);
}
.list-toolbar {
  padding: 0.5rem 0.55rem 0.4rem;
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
  background: var(--surface-veil);
}
.sort-lab {
  font-size: var(--fs-2xs);
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-muted);
  display: block;
  margin-bottom: 0.25rem;
}
.sort-select {
  width: 100%;
  padding: 0.34rem 0.45rem;
  border-radius: 10px;
  border: 1px solid var(--border);
  font: inherit;
  font-size: var(--fs-2xs);
  background: var(--surface-1);
}
.list-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 0.35rem 0.45rem 0.75rem;
}
.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.list > li {
  min-width: 0;
}
.note-item {
  width: 100%;
  min-width: 0;
  text-align: left;
  padding: 0.45rem 0.5rem;
  border-radius: 10px;
  border: 1px solid var(--border-subtle);
  background: var(--surface-translucent);
  cursor: pointer;
  font: inherit;
  color: inherit;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.note-item:hover {
  background: var(--surface-1);
  border-color: var(--accent-border-soft);
}
.note-item.current {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent-glow);
}
.note-title {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
  word-break: break-word;
  font-weight: 600;
  font-size: var(--fs-xs);
  line-height: var(--lh-snug);
}
.note-preview {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
  word-break: break-word;
  font-size: var(--fs-2xs);
  color: var(--text-muted);
  line-height: var(--lh-snug);
}
.meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  font-size: var(--fs-2xs);
  color: var(--note-list-meta);
}
.folder-badge {
  padding: 0.06rem 0.35rem;
  border-radius: 6px;
  background: var(--surface-wash);
}
.dates-compact {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: var(--fs-tiny);
}
.meta-prefix {
  opacity: 0.75;
  margin-right: 0.12rem;
  font-size: var(--fs-micro);
}
.editor-shell {
  flex: 1;
  min-width: 0;
  min-height: 0;
  max-height: calc(100vh - 52px);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.workspace--fit .editor-shell {
  max-height: none;
}
.editor-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  color: var(--text-muted);
}
.ph-int {
  font-size: var(--fs-base);
  font-weight: 600;
  margin: 0 0 0.5rem;
  color: var(--text-3);
}
.ph-sub {
  margin: 0;
  font-size: var(--fs-sm);
  max-width: 320px;
  text-align: center;
}
.empty {
  margin: 0.5rem 0;
  color: var(--text-muted);
  font-size: var(--fs-sm);
}
.hint-pad {
  padding: 0.75rem 0.35rem;
  line-height: var(--lh-normal);
}
.load-hint {
  padding: 0.5rem;
}
.muted {
  color: var(--text-muted);
}
.err {
  color: var(--danger-text);
}

/* Мобильный расклад: три колонки складываются в столбик, ширины из inline-стилей
   перебиваются, чтобы страница не уезжала в горизонтальный скролл. */
@media (max-width: 768px) {
  .workspace-header {
    padding: var(--space-3) var(--space-5) var(--space-4);
    gap: var(--space-3) var(--space-4);
  }
  .actions {
    width: 100%;
    margin-left: 0;
  }
  .header-user {
    margin-left: auto;
  }
  .user {
    max-width: 45vw;
  }
  .workspace-body {
    flex-direction: column;
  }
  .tags-aside,
  .notes-list-col {
    width: 100% !important;
    border-right: none;
    border-bottom: 1px solid var(--border-subtle);
  }
  .tags-aside {
    max-height: 45vh;
  }
  .notes-list-col {
    max-height: 50vh;
  }
  .sidebar-panel {
    box-shadow: none;
  }
  /* Тянуть границы колонок пальцем всё равно нельзя. */
  .col-gutter,
  .folder-nav-v-gutter {
    display: none;
  }
  .editor-shell {
    min-height: 60vh;
  }
  .sort-select {
    min-height: var(--tap-min);
    font-size: var(--fs-xs);
  }
}
</style>
