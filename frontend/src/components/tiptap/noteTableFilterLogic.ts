import type { Node as PMNode } from '@tiptap/pm/model'
import { TableMap } from '@tiptap/pm/tables'

export const EMPTY_CELL_LABEL = '(Пусто)'

/** Активный фильтр столбца: выбранные значения. Пустой Set — ничего не показывать. */
export type ColumnFilterSelection = Set<string>

/** null — фильтр по столбцу выключен (показываем все значения). */
export type TableColumnFilters = Record<number, ColumnFilterSelection | null>

export function normalizeCellDisplayText(raw: string): string {
  const t = raw.replace(/\s+/g, ' ').trim()
  return t.length ? t : EMPTY_CELL_LABEL
}

export function extractCellPlainText(cell: PMNode): string {
  let out = ''
  cell.descendants((node) => {
    if (node.isText) out += node.text ?? ''
  })
  return normalizeCellDisplayText(out)
}

export function tableHasHeaderRow(table: PMNode): boolean {
  const firstRow = table.firstChild
  if (!firstRow || firstRow.type.name !== 'tableRow') return false
  for (let i = 0; i < firstRow.childCount; i++) {
    if (firstRow.child(i).type.name === 'tableHeader') return true
  }
  return false
}

export function getTableColumnCount(table: PMNode): number {
  return TableMap.get(table).width
}

/** Тексты ячеек строки по логическим столбцам (colspan дублирует текст). */
export function getRowCellTexts(row: PMNode): string[] {
  const texts: string[] = []
  for (let i = 0; i < row.childCount; i++) {
    const cell = row.child(i)
    const text = extractCellPlainText(cell)
    const span = Math.max(1, Number(cell.attrs.colspan) || 1)
    for (let j = 0; j < span; j++) texts.push(text)
  }
  return texts
}

export function getHeaderLabels(table: PMNode): string[] {
  const colCount = getTableColumnCount(table)
  const firstRow = table.firstChild
  if (!firstRow || firstRow.type.name !== 'tableRow') {
    return Array.from({ length: colCount }, (_, i) => `Столбец ${i + 1}`)
  }
  const texts = getRowCellTexts(firstRow)
  const hasHeader = tableHasHeaderRow(table)
  return Array.from({ length: colCount }, (_, i) => {
    const label = texts[i] ?? ''
    if (hasHeader) return label === EMPTY_CELL_LABEL ? '—' : label
    return `Столбец ${i + 1}`
  })
}

export function getBodyRowStartIndex(table: PMNode): number {
  return tableHasHeaderRow(table) ? 1 : 0
}

export function getColumnUniqueValues(table: PMNode, colIndex: number): string[] {
  const values = new Set<string>()
  const start = getBodyRowStartIndex(table)
  for (let ri = start; ri < table.childCount; ri++) {
    const row = table.child(ri)
    if (row.type.name !== 'tableRow') continue
    const texts = getRowCellTexts(row)
    values.add(texts[colIndex] ?? EMPTY_CELL_LABEL)
  }
  return Array.from(values).sort((a, b) => a.localeCompare(b, 'ru'))
}

export function columnFilterIsActive(filter: ColumnFilterSelection | null | undefined): boolean {
  return filter != null
}

export function tableHasActiveFilters(filters: TableColumnFilters | undefined): boolean {
  if (!filters) return false
  return Object.values(filters).some(columnFilterIsActive)
}

export function rowMatchesTableFilters(
  table: PMNode,
  rowIndex: number,
  filters: TableColumnFilters
): boolean {
  const row = table.child(rowIndex)
  if (!row || row.type.name !== 'tableRow') return true
  const texts = getRowCellTexts(row)
  for (const [colKey, selected] of Object.entries(filters)) {
    if (selected == null) continue
    const col = Number(colKey)
    if (!Number.isFinite(col)) continue
    const cellText = texts[col] ?? EMPTY_CELL_LABEL
    if (!selected.has(cellText)) return false
  }
  return true
}

export function countVisibleBodyRows(table: PMNode, filters: TableColumnFilters): number {
  const start = getBodyRowStartIndex(table)
  let n = 0
  for (let ri = start; ri < table.childCount; ri++) {
    if (rowMatchesTableFilters(table, ri, filters)) n++
  }
  return n
}

export function getTableIndexInDoc(doc: PMNode, targetPos: number): number {
  let index = 0
  doc.descendants((node, pos) => {
    if (node.type.name !== 'table') return
    if (pos === targetPos) return false
    index++
  })
  return index
}

export function listTablesInDoc(doc: PMNode): { pos: number; tableIndex: number; node: PMNode }[] {
  const out: { pos: number; tableIndex: number; node: PMNode }[] = []
  let tableIndex = 0
  doc.descendants((node, pos) => {
    if (node.type.name !== 'table') return
    out.push({ pos, tableIndex, node })
    tableIndex++
  })
  return out
}
