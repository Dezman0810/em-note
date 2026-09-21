import { Table } from '@tiptap/extension-table'

/** Сохранённые фильтры столбцов в JSON заметки: ключ — индекс столбца, значение — список значений. */
export type PersistedColumnFilters = Record<string, string[]>

export const NoteTable = Table.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      filterEnabled: {
        default: false,
        parseHTML: (element: HTMLElement) => element.getAttribute('data-filter-enabled') === 'true',
        renderHTML: (attributes: { filterEnabled?: boolean }) =>
          attributes.filterEnabled ? { 'data-filter-enabled': 'true' } : {},
      },
      columnFilters: {
        default: null as PersistedColumnFilters | null,
        parseHTML: (element: HTMLElement) => {
          const raw = element.getAttribute('data-column-filters')
          if (!raw) return null
          try {
            const parsed = JSON.parse(raw) as unknown
            if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
            return parsed as PersistedColumnFilters
          } catch {
            return null
          }
        },
        renderHTML: (attributes: { columnFilters?: PersistedColumnFilters | null }) => {
          if (!attributes.columnFilters || Object.keys(attributes.columnFilters).length === 0) return {}
          return { 'data-column-filters': JSON.stringify(attributes.columnFilters) }
        },
      },
    }
  },
})
