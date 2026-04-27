import type { ResolvedPos } from '@tiptap/pm/model'
import type { EditorState } from '@tiptap/pm/state'

/** Мин. высота ячейки (px). */
const CELL_MIN = 44

/** Мин. ширина столбца при ручном вводе; должна совпадать с cellMinWidth в TableKit. */
export const TABLE_COL_WIDTH_MIN = 20

/** Верхняя граница ширины столбца (px), защита от случайных огромных значений. */
export const TABLE_COL_WIDTH_MAX = 1600

/** Верхняя граница мин. высоты ячейки (px). */
export const TABLE_ROW_MAX_HEIGHT = 1200

export type NoteTableCellMetrics = {
  row: number
  col: number
  colspan: number
  colRangeLabel: string
  widthPx: number | null
  minHeightPx: number | null
  cellKind: 'tableCell' | 'tableHeader'
}

function cellMetricsFromResolved($from: ResolvedPos): NoteTableCellMetrics | null {
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

export function getNoteTableCellMetrics(state: EditorState): NoteTableCellMetrics | null {
  return cellMetricsFromResolved(state.selection.$from)
}

/** Метрики ячейки по позиции в документе (например сохранённый якорь при открытом меню). */
export function getNoteTableCellMetricsAt(state: EditorState, pos: number): NoteTableCellMetrics | null {
  try {
    const clamped = Math.max(1, Math.min(pos, state.doc.content.size))
    return cellMetricsFromResolved(state.doc.resolve(clamped))
  } catch {
    return null
  }
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
