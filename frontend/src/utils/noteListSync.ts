import type { Note, TagNoteCount } from '../api/types'

/** Подсказка редактору: что обновить в списке без полной перезагрузки. */
export type NoteListRefreshHint = {
  patchNote?: Note
  /** Счётчики меток / папок в боковой панели */
  counts?: boolean
  /** Календарь напоминаний */
  reminders?: boolean
  /** Полная перезагрузка списка (удаление, восстановление и т.п.) */
  full?: boolean
}

function tagIdsEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false
  }
  return true
}

/** Поля, влияющие на строку списка заметок. */
export function noteListItemEqual(a: Note, b: Note): boolean {
  return (
    a.id === b.id &&
    a.title === b.title &&
    a.updated_at === b.updated_at &&
    a.created_at === b.created_at &&
    a.folder_id === b.folder_id &&
    a.reminder_at === b.reminder_at &&
    a.deleted_at === b.deleted_at &&
    a.content_plain === b.content_plain &&
    tagIdsEqual(a.tag_ids, b.tag_ids)
  )
}

export function notesListEqual(prev: readonly Note[], next: readonly Note[]): boolean {
  if (prev.length !== next.length) return false
  for (let i = 0; i < prev.length; i++) {
    if (!noteListItemEqual(prev[i]!, next[i]!)) return false
  }
  return true
}

export type NotesListApplyResult = {
  changed: boolean
  newIds: string[]
  updatedIds: string[]
}

export function diffNotesList(prev: readonly Note[], next: readonly Note[]): NotesListApplyResult {
  const prevById = new Map(prev.map((n) => [n.id, n]))
  const newIds: string[] = []
  const updatedIds: string[] = []
  for (const n of next) {
    const old = prevById.get(n.id)
    if (!old) newIds.push(n.id)
    else if (!noteListItemEqual(old, n)) updatedIds.push(n.id)
  }
  return { changed: !notesListEqual(prev, next), newIds, updatedIds }
}

export function tagCountMapEqual(
  prev: Record<string, number>,
  next: Record<string, number>
): boolean {
  const pk = Object.keys(prev)
  const nk = Object.keys(next)
  if (pk.length !== nk.length) return false
  for (const k of pk) {
    if (prev[k] !== next[k]) return false
  }
  return true
}

export function tagCountsToMap(counts: TagNoteCount[]): Record<string, number> {
  const map: Record<string, number> = {}
  for (const c of counts) {
    map[String(c.tag_id)] = c.count
  }
  return map
}

/** Снимок напоминаний для решения, нужно ли обновлять календарь. */
export function remindersSnapshot(notes: readonly Note[]): string {
  return notes
    .map((n) => `${n.id}\t${n.reminder_at ?? ''}`)
    .sort()
    .join('\n')
}

export function remindersEqual(a: readonly Note[], b: readonly Note[]): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) {
    const x = a[i]!
    const y = b[i]!
    if (x.id !== y.id || x.reminder_at !== y.reminder_at || x.title !== y.title) return false
  }
  return true
}

export function mergeRefreshHints(
  a?: NoteListRefreshHint,
  b?: NoteListRefreshHint
): NoteListRefreshHint | undefined {
  if (!a) return b
  if (!b) return a
  return {
    patchNote: b.patchNote ?? a.patchNote,
    counts: a.counts || b.counts,
    reminders: a.reminders || b.reminders,
    full: a.full || b.full,
  }
}
