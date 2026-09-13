<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { errMessage, mindmapsApi } from '../api/client'
import type { NoteMindmapDetail, NoteMindmapListItem } from '../api/types'
import NoteEditorColumn from '../components/NoteEditorColumn.vue'
import MindmapStandaloneEditor from '../components/MindmapStandaloneEditor.vue'
import BlockTitleField from '../components/BlockTitleField.vue'
import AppSectionNav from '../components/AppSectionNav.vue'
import { useTheme } from '../composables/useTheme'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const { label: themeLabel, icon: themeIcon, cycleTheme } = useTheme()

const LIST_COLLAPSED_KEY = 'note-ui-mindmaps-list-collapsed'
const LIST_WIDTH_KEY = 'note-ui-mindmaps-list-width'
const SCHEMA_COL_KEY = 'note-ui-mindmaps-col-name'
const LIST_MIN = 220
const LIST_MAX = 760
const SCHEMA_COL_MIN = 88
const SCHEMA_COL_MAX = 520

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

function readPx(key: string, fallback: number, min: number, max: number): number {
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

const items = ref<NoteMindmapListItem[]>([])
const loading = ref(false)
const error = ref('')
const qSchema = ref('')
const qNote = ref('')
const qTag = ref('')
const listCollapsed = ref(readBoolKey(LIST_COLLAPSED_KEY, false))
const listWidthPx = ref(readPx(LIST_WIDTH_KEY, 360, LIST_MIN, LIST_MAX))
const schemaColPx = ref(readPx(SCHEMA_COL_KEY, 170, SCHEMA_COL_MIN, SCHEMA_COL_MAX))

type DragKind = null | 'list' | 'schemaCol'
const drag = ref<DragKind>(null)
let dragStartX = 0
let dragStartList = 0
let dragStartSchemaCol = 0

const listPaneStyle = computed(() => {
  if (listCollapsed.value) return {} as Record<string, string>
  return { width: `${listWidthPx.value}px` }
})

const colsStyle = computed(() => ({
  gridTemplateColumns: `${schemaColPx.value}px 6px minmax(0, 1fr)`,
}))

function persistLayout() {
  try {
    localStorage.setItem(LIST_WIDTH_KEY, String(listWidthPx.value))
    localStorage.setItem(SCHEMA_COL_KEY, String(schemaColPx.value))
  } catch {
    /* */
  }
}

function toggleListCollapsed() {
  listCollapsed.value = !listCollapsed.value
  writeBoolKey(LIST_COLLAPSED_KEY, listCollapsed.value)
}

function onDragMove(e: MouseEvent) {
  if (drag.value === 'list') {
    listWidthPx.value = Math.min(
      LIST_MAX,
      Math.max(LIST_MIN, dragStartList + (e.clientX - dragStartX))
    )
    return
  }
  if (drag.value === 'schemaCol') {
    schemaColPx.value = Math.min(
      SCHEMA_COL_MAX,
      Math.max(SCHEMA_COL_MIN, dragStartSchemaCol + (e.clientX - dragStartX))
    )
  }
}

function onDragUp() {
  if (!drag.value) return
  drag.value = null
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragUp)
  persistLayout()
}

function startDrag(kind: 'list' | 'schemaCol', e: MouseEvent) {
  if (listCollapsed.value) return
  e.preventDefault()
  drag.value = kind
  dragStartX = e.clientX
  dragStartList = listWidthPx.value
  dragStartSchemaCol = schemaColPx.value
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragUp)
}

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragUp)
})

const detail = ref<NoteMindmapDetail | null>(null)
const detailLoading = ref(false)
const saveState = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')
const saveError = ref('')
const lastMap = ref<{ noteId: string; index: number } | null>(null)

const showingSchema = computed(() => route.name === 'mindmap-edit')
const showingNote = computed(() => route.name === 'mindmap-note')
const noteId = computed(() => String(route.params.noteId || ''))
const schemaIndex = computed(() => Number(route.params.index))

const filtered = computed(() => {
  const schemaNeedle = qSchema.value.trim().toLowerCase()
  const noteNeedle = qNote.value.trim().toLowerCase()
  const tagNeedle = qTag.value.trim().toLowerCase()
  return items.value.filter((row) => {
    if (schemaNeedle && !row.caption.toLowerCase().includes(schemaNeedle)) return false
    if (noteNeedle && !(row.note_title || '').toLowerCase().includes(noteNeedle)) return false
    if (
      tagNeedle &&
      !(row.tag_names || []).some((name) => name.toLowerCase().includes(tagNeedle))
    ) {
      return false
    }
    return true
  })
})

function rowKey(row: Pick<NoteMindmapListItem, 'note_id' | 'schema_index'>) {
  return `${row.note_id}:${row.schema_index}`
}

function isSchemaSelected(row: NoteMindmapListItem) {
  return showingSchema.value && row.note_id === noteId.value && row.schema_index === schemaIndex.value
}

function isNoteSelected(row: NoteMindmapListItem) {
  return showingNote.value && row.note_id === noteId.value
}

function applyDetailToList(current: NoteMindmapListItem, next: NoteMindmapDetail) {
  const i = items.value.findIndex(
    (row) => row.note_id === current.note_id && row.schema_index === current.schema_index
  )
  if (i < 0) return
  items.value[i] = {
    note_id: next.note_id,
    note_title: next.note_title,
    schema_index: next.schema_index,
    block_id: next.block_id,
    caption: next.caption,
    element_count: next.element_count,
    can_edit: next.can_edit,
    my_access: next.my_access,
    updated_at: next.updated_at,
    tag_names: next.tag_names || [],
  }
}

async function loadList() {
  loading.value = true
  error.value = ''
  try {
    items.value = await mindmapsApi.list()
  } catch (e) {
    error.value = errMessage(e)
    items.value = []
  } finally {
    loading.value = false
  }
}

async function loadDetail() {
  if (!showingSchema.value || !noteId.value || !Number.isInteger(schemaIndex.value)) {
    if (!showingNote.value) detail.value = null
    return
  }
  detailLoading.value = true
  saveState.value = 'idle'
  saveError.value = ''
  try {
    detail.value = await mindmapsApi.get(noteId.value, schemaIndex.value)
    lastMap.value = { noteId: noteId.value, index: schemaIndex.value }
  } catch (e) {
    error.value = errMessage(e)
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

async function onSceneChange(scene: string) {
  const current = detail.value
  if (!current?.can_edit) return
  saveState.value = 'saving'
  saveError.value = ''
  try {
    detail.value = await mindmapsApi.update(current.note_id, current.schema_index, {
      scene,
      block_id: current.block_id,
    })
    saveState.value = 'saved'
    if (detail.value) applyDetailToList(current, detail.value)
  } catch (e) {
    saveState.value = 'error'
    saveError.value = errMessage(e)
  }
}

async function onTitleSave(title: string) {
  const current = detail.value
  if (!current?.can_edit) return
  saveState.value = 'saving'
  saveError.value = ''
  try {
    detail.value = await mindmapsApi.update(current.note_id, current.schema_index, {
      title,
      block_id: current.block_id,
    })
    saveState.value = 'saved'
    if (detail.value) applyDetailToList(current, detail.value)
  } catch (e) {
    saveState.value = 'error'
    saveError.value = errMessage(e)
  }
}

function openSchema(row: NoteMindmapListItem) {
  lastMap.value = { noteId: row.note_id, index: row.schema_index }
  void router.push({
    name: 'mindmap-edit',
    params: { noteId: row.note_id, index: String(row.schema_index) },
  })
}

function openNote(id: string) {
  void router.push({ name: 'mindmap-note', params: { noteId: id } })
}

function onNoteClose() {
  const back = lastMap.value
  if (back && back.noteId === noteId.value) {
    void router.push({
      name: 'mindmap-edit',
      params: { noteId: back.noteId, index: String(back.index) },
    })
    return
  }
  void router.push({ name: 'mindmaps' })
}

async function onNoteRefresh() {
  await loadList()
}

function logout() {
  auth.logout()
  void router.push({ name: 'login' })
}

watch(
  () => [route.name, noteId.value, schemaIndex.value] as const,
  () => {
    void loadDetail()
  }
)

onMounted(() => {
  void loadList()
  void loadDetail()
})
</script>

<template>
  <div class="workspace">
    <header class="workspace-header">
      <div class="header-left">
        <button
          type="button"
          class="logo logo-wordmark logo-home-btn"
          lang="ru"
          @click="router.push({ name: 'notes' })"
        >
          <span class="logo-brand"
            ><span class="logo-brand-accent">Em</span><span class="logo-brand-dash">-</span
            ><span>Note</span></span
          >
        </button>
      </div>
      <div class="header-end">
        <AppSectionNav active="mindmaps" />
        <div class="header-user">
          <span v-if="auth.user" class="user">{{ auth.user.email }}</span>
          <button type="button" class="theme-toggle" :aria-label="themeLabel" :title="themeLabel" @click="cycleTheme">
            <span class="theme-toggle-glyph" aria-hidden="true">{{ themeIcon }}</span>
          </button>
          <button type="button" class="btn ghost" @click="logout">Выйти</button>
        </div>
      </div>
    </header>

    <div class="split">
      <button
        v-if="listCollapsed"
        type="button"
        class="list-rail-expand"
        title="Развернуть список карт"
        aria-label="Развернуть список карт"
        @click="toggleListCollapsed"
      >
        +
      </button>
      <aside v-else class="list-pane" :style="listPaneStyle">
        <div class="list-toolbar">
          <div class="search-row">
            <input
              v-model="qSchema"
              type="search"
              class="search"
              placeholder="Карта"
              aria-label="Поиск по имени карты"
            />
            <input
              v-model="qNote"
              type="search"
              class="search"
              placeholder="Заметка"
              aria-label="Поиск по имени заметки"
            />
            <input
              v-model="qTag"
              type="search"
              class="search"
              placeholder="Метка"
              aria-label="Поиск по метке заметки"
            />
            <p class="muted count">{{ filtered.length }}</p>
            <button
              type="button"
              class="btn-list-hide"
              title="Скрыть список карт"
              aria-label="Скрыть список карт"
              @click="toggleListCollapsed"
            >
              −
            </button>
          </div>
        </div>
        <div class="cols-head" :style="colsStyle">
          <div class="col-title">Карта</div>
          <div
            class="col-split"
            title="Потяните, чтобы изменить ширину названия карты"
            @mousedown="startDrag('schemaCol', $event)"
          />
          <div class="col-title">Заметка</div>
        </div>
        <p v-if="error && !showingSchema && !showingNote" class="err pad">{{ error }}</p>
        <p v-if="loading" class="muted pad">Загрузка…</p>
        <p v-else-if="!filtered.length" class="empty">
          Нет карт по этому фильтру. Карта появляется здесь, когда она есть в доступной заметке.
        </p>
        <ul v-else class="rows" role="listbox" aria-label="Карты">
          <li
            v-for="row in filtered"
            :key="rowKey(row)"
            class="row"
            :class="{ on: isSchemaSelected(row), 'on-note': isNoteSelected(row) }"
            :style="colsStyle"
          >
            <button
              type="button"
              class="row-schema"
              :title="row.caption"
              @click="openSchema(row)"
            >
              {{ row.caption }}
            </button>
            <span class="col-split-spacer" aria-hidden="true" />
            <button
              type="button"
              class="row-note"
              :title="`Открыть заметку «${row.note_title || 'Без названия'}»`"
              @click="openNote(row.note_id)"
            >
              {{ row.note_title || 'Без названия' }}
            </button>
          </li>
        </ul>
      </aside>
      <div
        v-if="!listCollapsed"
        class="col-gutter"
        title="Потяните, чтобы расширить список"
        @mousedown="startDrag('list', $event)"
      />

      <section class="preview-pane">
        <template v-if="showingNote">
          <NoteEditorColumn
            :note-id="noteId"
            embedded
            embedded-back-label="← К картам"
            @close="onNoteClose"
            @refresh="onNoteRefresh"
          />
        </template>
        <template v-else-if="showingSchema">
          <div class="preview-bar">
            <div class="preview-title" v-if="detail">
              <BlockTitleField
                :model-value="detail.caption"
                :disabled="!detail.can_edit"
                placeholder="Карта"
                aria-label="Название карты"
                @save="onTitleSave"
              />
              <span class="muted">{{ detail.note_title || 'Без названия' }}</span>
            </div>
            <span v-if="saveState === 'saving'" class="muted">Сохранение…</span>
            <span v-else-if="saveState === 'saved'" class="ok">Сохранено в заметку</span>
            <span v-else-if="saveState === 'error'" class="err">{{ saveError }}</span>
            <button
              v-if="detail || noteId"
              type="button"
              class="btn secondary"
              @click="openNote(detail?.note_id || noteId)"
            >
              Открыть заметку
            </button>
          </div>
          <p v-if="detailLoading" class="muted pad">Загрузка карты…</p>
          <p v-else-if="!detail" class="err pad">{{ error || 'Карта не найдена' }}</p>
          <MindmapStandaloneEditor
            v-else
            :key="`${detail.note_id}:${detail.schema_index}`"
            :scene="detail.scene"
            :read-only="!detail.can_edit"
            :block-id="detail.block_id"
            @change="onSceneChange"
          />
        </template>
        <div v-else class="preview-empty">
          <p>Выберите карту слева — она откроется здесь.</p>
          <p class="muted">Можно развернуть на весь экран, как в заметке, или открыть саму заметку на этом экране.</p>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.workspace {
  height: 100vh;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
  background: var(--bg);
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
  gap: 0.55rem;
  min-width: 0;
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
}
.logo-brand-accent {
  color: var(--accent-text);
}
.logo-brand-dash {
  color: var(--text-4);
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
.split {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
}
.list-rail-expand {
  flex-shrink: 0;
  width: 40px;
  align-self: stretch;
  margin: 0;
  border: none;
  border-right: 1px solid var(--border-subtle);
  border-radius: 0;
  background: linear-gradient(180deg, var(--surface-2) 0%, var(--surface-canvas, var(--bg)) 100%);
  font-size: var(--fs-xl);
  font-weight: 600;
  cursor: pointer;
  color: var(--accent-text);
  line-height: 1;
}
.list-rail-expand:hover {
  background: var(--surface-4, var(--surface-2));
}
.list-pane {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--surface-1);
  min-height: 0;
  min-width: 0;
}
.col-gutter {
  width: 5px;
  flex-shrink: 0;
  cursor: col-resize;
  background: transparent;
  align-self: stretch;
  position: relative;
  z-index: 2;
  border-right: 1px solid var(--border);
}
.col-gutter:hover {
  background: var(--hover-wash, var(--surface-2));
}
.list-toolbar {
  padding: 0.55rem 0.6rem 0.5rem;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.search-row {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0.35rem;
}
.btn-list-hide {
  width: 1.65rem;
  height: 1.65rem;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-1);
  cursor: pointer;
  font-size: var(--fs-base);
  line-height: 1;
  color: var(--text-3);
  flex-shrink: 0;
}
.btn-list-hide:hover {
  background: var(--surface-2);
}
.search {
  flex: 1 1 0;
  min-width: 0;
  box-sizing: border-box;
  padding: 0.38rem 0.45rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text-1);
  font: inherit;
  font-size: var(--fs-xs);
}
.count {
  margin: 0;
  flex-shrink: 0;
  font-size: var(--fs-2xs);
}
.cols-head {
  display: grid;
  align-items: center;
  padding: 0.25rem 0.35rem 0.2rem;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.col-title {
  font-size: var(--fs-2xs);
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-4);
  padding: 0.2rem 0.35rem;
}
.col-split {
  width: 6px;
  height: 1.15rem;
  margin: 0 auto;
  cursor: col-resize;
  border-radius: 99px;
  background: var(--border);
}
.col-split:hover {
  background: var(--accent);
}
.col-split-spacer {
  width: 6px;
}
.rows {
  list-style: none;
  margin: 0;
  padding: 0.35rem;
  overflow: auto;
  min-height: 0;
}
.row {
  display: grid;
  align-items: center;
  padding: 0.12rem 0;
  border: 1px solid transparent;
  border-radius: 10px;
}
.row:hover {
  background: var(--sidebar-hover, var(--surface-2));
}
.row.on,
.row.on-note {
  background: var(--accent-subtle);
  border-color: var(--accent-border);
}
.row-schema,
.row-note {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
  padding: 0.32rem 0.35rem;
  border-radius: 8px;
}
.row-schema {
  font-weight: 700;
  font-size: var(--fs-sm);
}
.row-note {
  font-size: var(--fs-xs);
  color: var(--text-muted);
}
.row-schema:hover,
.row-note:hover {
  background: var(--panel);
}
.preview-pane {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg);
}
.preview-pane :deep(.editor-column) {
  max-height: none;
  height: 100%;
  min-height: 0;
}
.preview-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.55rem 0.75rem;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--border);
  background: var(--surface-1);
  flex-shrink: 0;
}
.preview-title {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1 1 12rem;
  gap: 0.2rem;
}
.preview-title :deep(.block-title-wrap) {
  max-width: min(36rem, 100%);
}
.preview-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  padding: 2rem;
  text-align: center;
  color: var(--text-1);
}
.muted {
  color: var(--text-muted);
  font-size: var(--fs-sm);
}
.empty {
  margin: 0.75rem;
  padding: 0.85rem;
  border-radius: 12px;
  background: var(--panel);
  color: var(--text-muted);
  font-size: var(--fs-sm);
}
.err {
  color: var(--danger-text, #b42318);
  font-size: var(--fs-sm);
}
.ok {
  color: var(--accent-text);
  font-size: var(--fs-sm);
}
.pad {
  padding: 0.85rem;
}
@media (max-width: 800px) {
  .split {
    flex-direction: column;
  }
  .list-pane {
    width: 100% !important;
    min-width: 0;
    max-height: 42%;
    border-right: 0;
    border-bottom: 1px solid var(--border);
  }
  .col-gutter,
  .list-rail-expand,
  .btn-list-hide {
    display: none;
  }
}
</style>
