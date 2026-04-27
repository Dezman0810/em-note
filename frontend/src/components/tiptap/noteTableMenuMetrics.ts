import type { EditorState } from '@tiptap/pm/state'

const CELL_MIN = 44

export type NoteTableCellMetrics = {
  row: number
  col: number
  colspan: number
  colRangeLabel: string
  widthPx: number | null
  minHeightPx: number | null
  cellKind: 'tableCell' | 'tableHeader'
}

export function getNoteTableCellMetrics(state: EditorState): NoteTableCellMetrics | null {
  const $from = state.selection.$from
  for (let d = $from.depth; d >= 1; d--) {
    const here = $from.node(d)
    if (here.type.name !== 'tableCell' && here.type.name !== 'tableHeader') continue
    const row = $from.node(d - 1)
    const table = $from.node(d - 2)
    if (!row || row.type.name !== 'tableRow' || !table || table.type.name !== 'table') continue

    const rowIndex = $from.index(d - 1)
    const cellChildIndex = $from.index(d)
    let colStart = 0
    for (let ci = 0; ci < cellChildIndex; ci++) {
      colStart += row.child(ci).attrs.colspan || 1
    }
    const colspan = here.attrs.colspan || 1
    const colwidth = here.attrs.colwidth as number[] | null | undefined
    const widthPx = colwidth?.[0] != null ? Number(colwidth[0]) : null
    const minHeightRaw = here.attrs.minHeight as number | null | undefined
    const minHeightPx = minHeightRaw != null && minHeightRaw > 0 ? minHeightRaw : null

    const colEnd = colStart + colspan
    const colRangeLabel = colspan > 1 ? `${colStart + 1}–${colEnd}` : String(colStart + 1)

    return {
      row: rowIndex + 1,
      col: colStart + 1,
      colspan,
      colRangeLabel,
      widthPx: Number.isFinite(widthPx as number) ? (widthPx as number) : null,
      minHeightPx,
      cellKind: here.type.name as 'tableCell' | 'tableHeader',
    }
  }
  return null
}

/** Сумма ширин по первой строке (оценка; для «авто» столбцов — минимум ячейки). */
export function getNoteTableApproxWidthPx(state: EditorState, cellMinWidth: number): number | null {
  const $from = state.selection.$from
  for (let d = $from.depth; d >= 1; d--) {
    if ($from.node(d).type.name !== 'table') continue
    const table = $from.node(d)
    const row = table.firstChild
    if (!row || row.type.name !== 'tableRow') return null
    let sum = 0
    for (let i = 0; i < row.childCount; i++) {
      const cell = row.child(i)
      const span = cell.attrs.colspan || 1
      const cw = cell.attrs.colwidth as number[] | null | undefined
      if (cw?.length) {
        for (let j = 0; j < span; j++) {
          const part = cw[j]
          sum += part != null && part > 0 ? part : cellMinWidth
        }
      } else {
        sum += span * cellMinWidth
      }
    }
    return sum
  }
  return null
}

export { CELL_MIN }
