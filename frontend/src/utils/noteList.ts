/**
 * Общее для списков заметок в разделах «Заметки» и «Метки»: сортировка,
 * превью текста и подсказка строки. Раньше этот код был скопирован в оба view.
 */
import type { Note } from '../api/types'
import { fmtMsk } from './datetime'
import { DEFAULT_NOTE_TITLE } from './noteDefaults'

export type NoteSort =
  | 'updated_desc'
  | 'updated_asc'
  | 'created_desc'
  | 'created_asc'
  | 'title_asc'
  | 'title_desc'

/** Нативный title: полный заголовок и текст (с ограничением по длине), даты внизу. */
const TOOLTIP_BODY_MAX = 8000
const PREVIEW_MAX = 140

/** Один Collator на всё приложение: создавать его на каждое сравнение дорого. */
const ruCollator = new Intl.Collator('ru', { sensitivity: 'base' })

/**
 * Сортировка без повторного разбора даты: `new Date()` внутри компаратора
 * вызывался O(n log n) раз, теперь метки времени считаются по одному разу на заметку.
 */
export function sortNotes(notes: readonly Note[], sort: NoteSort): Note[] {
  const list = [...notes]
  if (sort === 'title_asc' || sort === 'title_desc') {
    const dir = sort === 'title_asc' ? 1 : -1
    list.sort((a, b) => dir * ruCollator.compare(a.title || '', b.title || ''))
    return list
  }
  const byCreated = sort === 'created_asc' || sort === 'created_desc'
  const dir = sort.endsWith('_asc') ? 1 : -1
  const stamp = new Map<string, number>()
  for (const n of list) {
    const raw = byCreated ? n.created_at : n.updated_at
    const t = Date.parse(raw)
    stamp.set(n.id, Number.isNaN(t) ? 0 : t)
  }
  list.sort((a, b) => dir * ((stamp.get(a.id) ?? 0) - (stamp.get(b.id) ?? 0)))
  return list
}

export function noteBodyPreview(n: Note): string {
  const raw = (n.content_plain || '').replace(/\s+/g, ' ').trim()
  if (!raw) return ''
  if (raw.length <= PREVIEW_MAX) return raw
  return raw.slice(0, PREVIEW_MAX).trimEnd() + '…'
}

export function noteRowDatesLines(n: Note): string[] {
  const lines = [`Создано: ${fmtMsk(n.created_at)}`, `Изменено: ${fmtMsk(n.updated_at)}`]
  if (n.deleted_at) lines.push(`Удалено: ${fmtMsk(n.deleted_at)}`)
  return lines
}

/** Папка и метки приходят уже посчитанными: строка списка собирается один раз. */
export function noteRowTooltip(
  n: Note,
  opts?: { folderName?: string; tagLabels?: string[] }
): string {
  const titleFull = (n.title || '').trim() || DEFAULT_NOTE_TITLE
  const raw = (n.content_plain || '').replace(/\s+/g, ' ').trim()
  const lines: string[] = [titleFull]
  if (raw) {
    lines.push(
      '',
      raw.length > TOOLTIP_BODY_MAX ? `${raw.slice(0, TOOLTIP_BODY_MAX).trimEnd()}…` : raw
    )
  }
  if (opts?.folderName) lines.push('', `Папка: ${opts.folderName}`)
  if (opts?.tagLabels?.length) lines.push('', `Метки: ${opts.tagLabels.join(', ')}`)
  lines.push('', ...noteRowDatesLines(n))
  return lines.join('\n')
}
