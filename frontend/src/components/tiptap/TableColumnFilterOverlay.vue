<script setup lang="ts">
import type { Editor } from '@tiptap/core'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  columnFilterIsActive,
  getColumnUniqueValues,
  getHeaderLabels,
} from './noteTableFilterLogic'
import {
  clearAllTableFiltersOnNode,
  clearTableColumnFilterOnNode,
  getFiltersFromTableNode,
  isTableFilterEnabled,
  setTableColumnFilterOnNode,
} from './noteTableFilterCommands'
import { refreshTableFilterDecorations } from './tableFilterSession'
import { listNoteTablesInView, type ResolvedNoteTable } from './tableFilterDomSync'

const props = defineProps<{
  editor: Editor
  editable: boolean
  hostEl: HTMLElement | null
}>()

type HeaderCellLayout = {
  tableIndex: number
  colIndex: number
  label: string
  left: number
  top: number
  width: number
  height: number
}

const layoutTick = ref(0)
const openFilter = ref<{ tableIndex: number; colIndex: number } | null>(null)
const searchQuery = ref('')
const draftSelection = ref<Set<string>>(new Set())
const panelPos = ref({ left: 0, top: 0 })

let raf = 0
function scheduleLayout() {
  if (raf) return
  raf = requestAnimationFrame(() => {
    raf = 0
    layoutTick.value++
  })
}

function onDocChange() {
  scheduleLayout()
}

function onWindowChange() {
  scheduleLayout()
}

onMounted(() => {
  props.editor.on('transaction', onDocChange)
  window.addEventListener('scroll', onWindowChange, true)
  window.addEventListener('resize', onWindowChange)
  document.addEventListener('mousedown', onHostClickOutside)
  scheduleLayout()
})

onBeforeUnmount(() => {
  props.editor.off('transaction', onDocChange)
  window.removeEventListener('scroll', onWindowChange, true)
  window.removeEventListener('resize', onWindowChange)
  document.removeEventListener('mousedown', onHostClickOutside)
  if (raf) cancelAnimationFrame(raf)
})

watch(
  () => props.editable,
  () => {
    openFilter.value = null
    scheduleLayout()
  }
)

watch(
  () => props.hostEl,
  (el, _prev, onCleanup) => {
    scheduleLayout()
    if (!el) return
    el.addEventListener('scroll', onWindowChange, { passive: true })
    onCleanup(() => el.removeEventListener('scroll', onWindowChange))
  },
  { immediate: true }
)

const headerCells = computed((): HeaderCellLayout[] => {
  void layoutTick.value
  if (!props.editable) return []
  const host = props.hostEl
  const view = props.editor.view
  if (!host || !view || view.isDestroyed) return []

  const hostRect = host.getBoundingClientRect()
  const tables = listNoteTablesInView(view)
  const out: HeaderCellLayout[] = []

  for (const { tableEl, tableNode, tableIndex } of tables) {
    if (!isTableFilterEnabled(tableNode)) continue
    const labels = getHeaderLabels(tableNode)
    const headerRow = tableEl.querySelector('tr')
    if (!headerRow) continue
    const domCells = headerRow.querySelectorAll<HTMLTableCellElement>('th, td')
    let colIndex = 0
    domCells.forEach((cellEl) => {
      const colspan = Math.max(1, cellEl.colSpan || 1)
      const rect = cellEl.getBoundingClientRect()
      for (let c = 0; c < colspan && colIndex < labels.length; c++) {
        const sliceWidth = rect.width / colspan
        out.push({
          tableIndex,
          colIndex,
          label: labels[colIndex] ?? `Столбец ${colIndex + 1}`,
          left: rect.left - hostRect.left + c * sliceWidth,
          top: rect.top - hostRect.top,
          width: sliceWidth,
          height: rect.height,
        })
        colIndex++
      }
    })
  }

  return out
})

function isFilterActive(tableIndex: number, colIndex: number): boolean {
  const resolved = getResolvedTable(tableIndex)
  if (!resolved) return false
  const f = getFiltersFromTableNode(resolved.tableNode)[colIndex]
  return columnFilterIsActive(f)
}

function getResolvedTable(tableIndex: number): ResolvedNoteTable | null {
  const view = props.editor.view
  if (!view || view.isDestroyed) return null
  return listNoteTablesInView(view).find((t) => t.tableIndex === tableIndex) ?? null
}

function openDropdown(cell: HeaderCellLayout, btnEl: HTMLElement) {
  if (
    openFilter.value?.tableIndex === cell.tableIndex &&
    openFilter.value?.colIndex === cell.colIndex
  ) {
    openFilter.value = null
    return
  }

  const resolved = getResolvedTable(cell.tableIndex)
  if (!resolved) return
  const allValues = getColumnUniqueValues(resolved.tableNode, cell.colIndex)

  const current = getFiltersFromTableNode(resolved.tableNode)[cell.colIndex]
  draftSelection.value = current ? new Set(current) : new Set(allValues)
  searchQuery.value = ''
  openFilter.value = { tableIndex: cell.tableIndex, colIndex: cell.colIndex }

  const btnRect = btnEl.getBoundingClientRect()
  panelPos.value = {
    left: btnRect.left,
    top: btnRect.bottom + 4,
  }
}

function filteredValues(tableIndex: number, colIndex: number): string[] {
  const resolved = getResolvedTable(tableIndex)
  if (!resolved) return []
  const all = getColumnUniqueValues(resolved.tableNode, colIndex)
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return all
  return all.filter((v) => v.toLowerCase().includes(q))
}

function applyDraftFilter() {
  const open = openFilter.value
  if (!open) return
  const resolved = getResolvedTable(open.tableIndex)
  if (!resolved) return
  const allValues = getColumnUniqueValues(resolved.tableNode, open.colIndex)

  const selected = draftSelection.value
  const allSelected = allValues.length > 0 && allValues.every((v) => selected.has(v))
  if (selected.size === 0 || allSelected) {
    clearTableColumnFilterOnNode(
      props.editor,
      resolved.tablePos,
      resolved.tableNode,
      open.colIndex
    )
  } else {
    setTableColumnFilterOnNode(
      props.editor,
      resolved.tablePos,
      resolved.tableNode,
      open.colIndex,
      new Set(selected)
    )
  }
  refreshTableFilterDecorations(props.editor)
  openFilter.value = null
  scheduleLayout()
}

function toggleDraftValue(value: string, checked: boolean) {
  const next = new Set(draftSelection.value)
  if (checked) next.add(value)
  else next.delete(value)
  draftSelection.value = next
}

function selectAllDraft(tableIndex: number, colIndex: number) {
  draftSelection.value = new Set(filteredValues(tableIndex, colIndex))
}

function clearDraftSelection() {
  draftSelection.value = new Set()
}

function resetTableFilters(tableIndex: number) {
  const resolved = getResolvedTable(tableIndex)
  if (!resolved) return
  clearAllTableFiltersOnNode(props.editor, resolved.tablePos, resolved.tableNode)
  refreshTableFilterDecorations(props.editor)
  openFilter.value = null
  scheduleLayout()
}

const openPanelTitle = computed(() => {
  const open = openFilter.value
  if (!open) return ''
  const cell = headerCells.value.find(
    (c) => c.tableIndex === open.tableIndex && c.colIndex === open.colIndex
  )
  return cell?.label ?? `Столбец ${open.colIndex + 1}`
})

watch(openFilter, (v) => {
  if (!v) searchQuery.value = ''
})

function onHostClickOutside(e: MouseEvent) {
  const t = e.target
  if (!(t instanceof Element)) return
  if (t.closest('.note-table-filter-panel') || t.closest('.note-table-filter-btn')) return
  openFilter.value = null
}
</script>

<template>
  <div v-if="headerCells.length" class="note-table-filter-layer" aria-hidden="true">
    <button
      v-for="cell in headerCells"
      :key="`${cell.tableIndex}-${cell.colIndex}`"
      type="button"
      class="note-table-filter-btn"
      :class="{ 'note-table-filter-btn--active': isFilterActive(cell.tableIndex, cell.colIndex) }"
      :style="{
        left: `${cell.left + cell.width - 22}px`,
        top: `${cell.top + 4}px`,
      }"
      :title="`Фильтр: ${cell.label}`"
      :aria-label="`Фильтр столбца ${cell.label}`"
      @mousedown.prevent
      @click="openDropdown(cell, $event.currentTarget as HTMLElement)"
    >
      ▾
    </button>
  </div>

  <Teleport to="body">
    <div
      v-if="openFilter"
      class="note-table-filter-panel"
      role="dialog"
      :style="{ left: `${panelPos.left}px`, top: `${panelPos.top}px` }"
      @mousedown.stop
    >
      <div class="note-table-filter-panel-head">
        <span class="note-table-filter-panel-title">{{ openPanelTitle }}</span>
        <button type="button" class="note-table-filter-panel-close" @click="openFilter = null">×</button>
      </div>
      <input
        v-model="searchQuery"
        type="search"
        class="note-table-filter-search"
        placeholder="Поиск значений…"
        autocomplete="off"
      />
      <div class="note-table-filter-actions">
        <button type="button" class="note-table-filter-link" @click="selectAllDraft(openFilter.tableIndex, openFilter.colIndex)">
          Выбрать все
        </button>
        <button type="button" class="note-table-filter-link" @click="clearDraftSelection">Снять все</button>
        <button
          type="button"
          class="note-table-filter-link"
          @click="resetTableFilters(openFilter.tableIndex)"
        >
          Сбросить таблицу
        </button>
      </div>
      <ul class="note-table-filter-list">
        <li v-for="value in filteredValues(openFilter.tableIndex, openFilter.colIndex)" :key="value">
          <label class="note-table-filter-item">
            <input
              type="checkbox"
              :checked="draftSelection.has(value)"
              @change="toggleDraftValue(value, ($event.target as HTMLInputElement).checked)"
            />
            <span>{{ value }}</span>
          </label>
        </li>
        <li v-if="filteredValues(openFilter.tableIndex, openFilter.colIndex).length === 0" class="note-table-filter-empty">
          Нет значений
        </li>
      </ul>
      <div class="note-table-filter-foot">
        <button type="button" class="note-table-filter-apply" @click="applyDraftFilter">Применить</button>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.note-table-filter-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 12;
}

.note-table-filter-btn {
  position: absolute;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--panel);
  color: var(--text-3);
  font-size: 11px;
  line-height: 1;
  cursor: pointer;
  pointer-events: auto;
  display: flex;
  align-items: center;
  justify-content: center;
}

.note-table-filter-btn:hover {
  border-color: var(--accent-border);
  color: var(--accent);
}

.note-table-filter-btn--active {
  background: var(--accent-subtle);
  border-color: var(--accent-border);
  color: var(--accent);
}

.note-table-filter-panel {
  position: fixed;
  z-index: 1200;
  width: min(280px, calc(100vw - 16px));
  max-height: min(360px, calc(100vh - 24px));
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  box-shadow: 0 8px 28px rgb(15 23 42 / 0.18);
  overflow: hidden;
}

.note-table-filter-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.45rem 0.55rem;
  border-bottom: 1px solid var(--border);
}

.note-table-filter-panel-title {
  font-size: var(--fs-xs);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.note-table-filter-panel-close {
  border: none;
  background: transparent;
  font-size: 1.1rem;
  line-height: 1;
  cursor: pointer;
  color: var(--text-3);
}

.note-table-filter-search {
  margin: 0.45rem 0.55rem 0;
  padding: 0.35rem 0.45rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  font: inherit;
  font-size: var(--fs-xs);
  background: var(--bg);
}

.note-table-filter-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem 0.55rem;
  padding: 0.35rem 0.55rem;
}

.note-table-filter-link {
  border: none;
  background: none;
  padding: 0;
  font: inherit;
  font-size: var(--fs-2xs);
  color: var(--accent);
  cursor: pointer;
}

.note-table-filter-list {
  list-style: none;
  margin: 0;
  padding: 0 0.35rem;
  overflow: auto;
  flex: 1;
  min-height: 0;
}

.note-table-filter-item {
  display: flex;
  align-items: flex-start;
  gap: 0.4rem;
  padding: 0.22rem 0.2rem;
  font-size: var(--fs-xs);
  cursor: pointer;
}

.note-table-filter-item input {
  margin-top: 0.15rem;
  flex-shrink: 0;
}

.note-table-filter-empty {
  padding: 0.5rem;
  font-size: var(--fs-xs);
  color: var(--text-3);
}

.note-table-filter-foot {
  padding: 0.45rem 0.55rem;
  border-top: 1px solid var(--border);
}

.note-table-filter-apply {
  width: 100%;
  padding: 0.35rem 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--accent-border);
  background: var(--accent-subtle);
  color: var(--accent);
  font: inherit;
  font-size: var(--fs-xs);
  cursor: pointer;
}

.note-table-filter-apply:hover {
  background: var(--accent-subtle-hover);
}
</style>
