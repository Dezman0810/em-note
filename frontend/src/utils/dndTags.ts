/** Одна метка из сайдбара «Заметки» или фильтра «Метки». */
export const MIME_TAG_ID = 'application/x-em-note-tag-id'

/** JSON-массив id меток (из структуры меток — мультивыбор). */
export const MIME_TAG_IDS_JSON = 'application/x-em-tag-ids'

export function isTagAttachDragTypes(types: readonly string[]): boolean {
  return types.includes(MIME_TAG_ID) || types.includes(MIME_TAG_IDS_JSON)
}

/** Собрать id меток при отпускании на заметку или поле меток в редакторе. */
export function readDroppedTagIds(e: DragEvent): string[] {
  const ts = e.dataTransfer
  if (!ts) return []
  const json = ts.getData(MIME_TAG_IDS_JSON)
  if (json) {
    try {
      const arr = JSON.parse(json) as unknown
      if (Array.isArray(arr)) {
        const out = [...new Set(arr.map(String).filter(Boolean))]
        if (out.length) return out
      }
    } catch {
      /* */
    }
  }
  const one = ts.getData(MIME_TAG_ID).trim()
  if (one) return [one]
  const raw = ts.getData('text/plain')
  if (raw) {
    try {
      const arr = JSON.parse(raw) as unknown
      if (Array.isArray(arr)) {
        return [...new Set(arr.map(String).filter(Boolean))]
      }
    } catch {
      /* */
    }
  }
  return []
}
