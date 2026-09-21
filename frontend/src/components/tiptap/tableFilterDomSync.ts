import type { EditorView } from '@tiptap/pm/view'
import type { Node as PMNode } from '@tiptap/pm/model'

import {
  getBodyRowStartIndex,
  getTableIndexInDoc,
  rowMatchesTableFilters,
  tableHasActiveFilters,
  tableHasHeaderRow,
} from './noteTableFilterLogic'
import type { TableColumnFilters } from './noteTableFilterLogic'
import { getFiltersFromTableNode, isTableFilterEnabled } from './noteTableFilterCommands'

const FILTER_STYLE_CLASS = 'note-table-filter-rules'

export type ResolvedNoteTable = {
  wrapper: HTMLElement
  tableEl: HTMLTableElement
  tableNode: PMNode
  tableIndex: number
  tablePos: number
}

export function listNoteTablesInView(view: EditorView): ResolvedNoteTable[] {
  const out: ResolvedNoteTable[] = []
  const seen = new Set<HTMLTableElement>()
  const wrappers = view.dom.querySelectorAll<HTMLElement>('.tableWrapper')

  for (const wrapper of wrappers) {
    const tableEl = wrapper.querySelector('table')
    if (!tableEl || seen.has(tableEl)) continue
    const resolved = resolveNoteTableFromElement(view, wrapper, tableEl)
    if (resolved) {
      seen.add(tableEl)
      out.push(resolved)
    }
  }

  return out
}

export function resolveNoteTableFromElement(
  view: EditorView,
  wrapper: HTMLElement,
  tableEl: HTMLTableElement
): ResolvedNoteTable | null {
  try {
    const pos = view.posAtDOM(tableEl, 0)
    const $pos = view.state.doc.resolve(pos)
    for (let d = $pos.depth; d >= 1; d--) {
      if ($pos.node(d).type.name === 'table') {
        const tablePos = $pos.before(d)
        return {
          wrapper,
          tableEl,
          tableNode: $pos.node(d),
          tableIndex: getTableIndexInDoc(view.state.doc, tablePos),
          tablePos,
        }
      }
    }
  } catch {
    /* posAtDOM может не сработать во время перерисовки */
  }
  return null
}

function wrapperScopeId(wrapper: HTMLElement, tablePos: number): string {
  const id = `note-filter-pos-${tablePos}`
  wrapper.dataset.noteFilterScopeId = id
  return id
}

export function clearTableFilterStyle(wrapper: HTMLElement): void {
  wrapper.querySelector(`style.${FILTER_STYLE_CLASS}`)?.remove()
  delete wrapper.dataset.noteFilterHidden
}

function computeHiddenRowNumbers(tableNode: PMNode, filters: TableColumnFilters): number[] {
  const bodyStart = getBodyRowStartIndex(tableNode)
  const hidden: number[] = []
  for (let ri = bodyStart; ri < tableNode.childCount; ri++) {
    if (!rowMatchesTableFilters(tableNode, ri, filters)) {
      hidden.push(ri + 1)
    }
  }
  return hidden
}

function applyHiddenRowsToWrapper(wrapper: HTMLElement, tablePos: number, hiddenRows: number[]): void {
  const signature = hiddenRows.join(',')
  if (wrapper.dataset.noteFilterHidden === signature) return
  wrapper.dataset.noteFilterHidden = signature

  if (hiddenRows.length === 0) {
    clearTableFilterStyle(wrapper)
    return
  }

  let styleEl = wrapper.querySelector(`style.${FILTER_STYLE_CLASS}`) as HTMLStyleElement | null
  if (!styleEl) {
    styleEl = document.createElement('style')
    styleEl.className = FILTER_STYLE_CLASS
    wrapper.appendChild(styleEl)
  }

  const scopeId = wrapperScopeId(wrapper, tablePos)
  styleEl.textContent = hiddenRows
    .map(
      (n) =>
        `.tableWrapper[data-note-filter-scope-id="${scopeId}"] tbody tr:nth-child(${n}) { display: none !important; }`
    )
    .join('\n')
}

function clearPersistedTableFilters(view: EditorView, tablePos: number, tableNode: PMNode): void {
  if (tableNode.attrs.columnFilters == null) return
  const tr = view.state.tr
  tr.setNodeMarkup(tablePos, undefined, { ...tableNode.attrs, columnFilters: null })
  view.dispatch(tr)
}

/** Фильтрация через style на .tableWrapper — не трогаем tr (иначе зависание PM). */
export function syncTableFilterDom(view: EditorView): void {
  if (view.isDestroyed) return

  for (const { wrapper, tableNode, tablePos } of listNoteTablesInView(view)) {
    if (!isTableFilterEnabled(tableNode)) {
      clearTableFilterStyle(wrapper)
      continue
    }

    const filters = getFiltersFromTableNode(tableNode)
    if (!tableHasActiveFilters(filters)) {
      clearTableFilterStyle(wrapper)
      continue
    }

    let hidden = computeHiddenRowNumbers(tableNode, filters)
    const bodyStart = getBodyRowStartIndex(tableNode)
    const bodyRowCount = Math.max(0, tableNode.childCount - bodyStart)

    if (bodyRowCount > 0 && hidden.length >= bodyRowCount) {
      clearTableFilterStyle(wrapper)
      clearPersistedTableFilters(view, tablePos, tableNode)
      continue
    }

    if (tableHasHeaderRow(tableNode) || wrapper.querySelector('tbody tr:first-child th')) {
      hidden = hidden.filter((n) => n !== 1)
    }

    applyHiddenRowsToWrapper(wrapper, tablePos, hidden)
  }
}

export function cleanupLegacyTableFilterStyles(root: ParentNode): void {
  root.querySelectorAll<HTMLElement>('.tableWrapper').forEach((wrapper) => {
    clearTableFilterStyle(wrapper)
    delete wrapper.dataset.noteFilterScopeId
  })
}
