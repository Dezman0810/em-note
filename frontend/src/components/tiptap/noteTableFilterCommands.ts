import type { Editor } from '@tiptap/core'
import type { EditorState } from '@tiptap/pm/state'
import type { Node as PMNode } from '@tiptap/pm/model'

import type { TableColumnFilters } from './noteTableFilterLogic'
import { tableHasActiveFilters } from './noteTableFilterLogic'
import type { PersistedColumnFilters } from './noteTableFilterTable'

export function attrsToTableColumnFilters(raw: unknown): TableColumnFilters {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const out: TableColumnFilters = {}
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    const col = Number(k)
    if (!Number.isFinite(col)) continue
    if (v == null) continue
    if (Array.isArray(v)) out[col] = new Set(v.map((x) => String(x)))
  }
  return out
}

export function tableColumnFiltersToAttrs(filters: TableColumnFilters): PersistedColumnFilters | null {
  const out: PersistedColumnFilters = {}
  for (const [k, v] of Object.entries(filters)) {
    if (v == null || v.size === 0) continue
    out[String(k)] = [...v]
  }
  return Object.keys(out).length > 0 ? out : null
}

export function isTableFilterEnabled(tableNode: PMNode): boolean {
  return tableNode.attrs.filterEnabled === true
}

export function getFiltersFromTableNode(tableNode: PMNode): TableColumnFilters {
  if (!isTableFilterEnabled(tableNode)) return {}
  return attrsToTableColumnFilters(tableNode.attrs.columnFilters)
}

export function findTableAtState(state: EditorState, pos?: number): { tablePos: number; tableNode: PMNode } | null {
  const $from = pos != null ? state.doc.resolve(pos) : state.selection.$from
  for (let d = $from.depth; d >= 1; d--) {
    if ($from.node(d).type.name === 'table') {
      return { tablePos: $from.before(d), tableNode: $from.node(d) }
    }
  }
  return null
}

function updateTableAttrs(
  editor: Editor,
  tablePos: number,
  tableNode: PMNode,
  patch: Record<string, unknown>
): boolean {
  const { view } = editor
  if (!view || view.isDestroyed) return false
  const tr = view.state.tr
  tr.setNodeMarkup(tablePos, undefined, { ...tableNode.attrs, ...patch })
  view.dispatch(tr)
  return true
}

export function setTableFilterEnabled(editor: Editor | null | undefined, enabled: boolean): boolean {
  const ed = editor
  if (!ed) return false
  const found = findTableAtState(ed.state)
  if (!found) return false
  return updateTableAttrs(ed, found.tablePos, found.tableNode, { filterEnabled: enabled })
}

export function setTableColumnFilterOnNode(
  editor: Editor | null | undefined,
  tablePos: number,
  tableNode: PMNode,
  colIndex: number,
  value: Set<string> | null
): boolean {
  const ed = editor
  if (!ed) return false
  const current = attrsToTableColumnFilters(tableNode.attrs.columnFilters)
  const next: TableColumnFilters = { ...current }
  if (value == null || value.size === 0) {
    delete next[colIndex]
  } else {
    next[colIndex] = value
  }
  return updateTableAttrs(ed, tablePos, tableNode, {
    columnFilters: tableColumnFiltersToAttrs(next),
  })
}

export function clearTableColumnFilterOnNode(
  editor: Editor | null | undefined,
  tablePos: number,
  tableNode: PMNode,
  colIndex: number
): boolean {
  return setTableColumnFilterOnNode(editor, tablePos, tableNode, colIndex, null)
}

export function clearAllTableFiltersOnNode(
  editor: Editor | null | undefined,
  tablePos: number,
  tableNode: PMNode
): boolean {
  return updateTableAttrs(editor, tablePos, tableNode, { columnFilters: null })
}

export function tableNodeHasActiveFilters(tableNode: PMNode): boolean {
  return isTableFilterEnabled(tableNode) && tableHasActiveFilters(getFiltersFromTableNode(tableNode))
}
