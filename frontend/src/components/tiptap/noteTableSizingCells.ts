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

/**
 * Заливка ячейки — отдельно от заливки текста (highlight): красится вся ячейка,
 * включая пустое место. Дублируем в data-атрибут, чтобы цвет переживал копирование
 * через HTML, где инлайновый style может быть вычищен.
 */
const backgroundAttr = {
  backgroundColor: {
    default: null as string | null,
    parseHTML: (element: HTMLElement) => {
      const fromData = element.getAttribute('data-background-color')?.trim()
      if (fromData) return fromData
      const style = element.style?.backgroundColor?.trim()
      return style || null
    },
    renderHTML: (attributes: { backgroundColor?: string | null }) => {
      const color = attributes.backgroundColor
      if (!color) return {}
      return {
        style: `background-color: ${color}`,
        'data-background-color': color,
      }
    },
  },
}

/** Ячейки/заголовки с минимальной высотой строки (px) и заливкой, в дополнение к colwidth из TableKit. */
export const NoteTableCell = TableCell.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      ...minHeightAttr,
      ...backgroundAttr,
    }
  },
})

export const NoteTableHeader = TableHeader.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      ...minHeightAttr,
      ...backgroundAttr,
    }
  },
})
