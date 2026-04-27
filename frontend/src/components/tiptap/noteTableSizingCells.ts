import { TableCell, TableHeader } from '@tiptap/extension-table'

const minHeightAttr = {
  minHeight: {
    default: null as number | null,
    parseHTML: (element: HTMLElement) => {
      const mh = element.style?.minHeight?.trim()
      if (mh?.endsWith('px')) return parseInt(mh, 10)
      return null
    },
    renderHTML: (attributes: { minHeight?: number | null }) => {
      if (attributes.minHeight == null || attributes.minHeight < 1) return {}
      return { style: `min-height: ${attributes.minHeight}px` }
    },
  },
}

/** Ячейки/заголовки с минимальной высотой строки (px), в дополнение к colwidth из TableKit. */
export const NoteTableCell = TableCell.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      ...minHeightAttr,
    }
  },
})

export const NoteTableHeader = TableHeader.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      ...minHeightAttr,
    }
  },
})
