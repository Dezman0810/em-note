import { describe, expect, it } from 'vitest'
import type { Note } from '../api/types'
import { noteBodyPreview, noteRowTooltip, sortNotes } from './noteList'

function note(over: Partial<Note> & { id: string }): Note {
  return {
    owner_id: 'u1',
    title: '',
    content_json: '{}',
    content_plain: '',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    deleted_at: null,
    folder_id: null,
    accent_color: '',
    reminder_at: null,
    tag_ids: [],
    ...over,
  } as Note
}

describe('sortNotes', () => {
  const a = note({ id: 'a', title: 'Банан', created_at: '2026-01-03T00:00:00Z', updated_at: '2026-01-05T00:00:00Z' })
  const b = note({ id: 'b', title: 'арбуз', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-09T00:00:00Z' })
  const c = note({ id: 'c', title: 'Вишня', created_at: '2026-01-02T00:00:00Z', updated_at: '2026-01-07T00:00:00Z' })
  const all = [a, b, c]

  it('сортирует по дате создания в обе стороны', () => {
    expect(sortNotes(all, 'created_asc').map((n) => n.id)).toEqual(['b', 'c', 'a'])
    expect(sortNotes(all, 'created_desc').map((n) => n.id)).toEqual(['a', 'c', 'b'])
  })

  it('сортирует по дате изменения в обе стороны', () => {
    expect(sortNotes(all, 'updated_asc').map((n) => n.id)).toEqual(['a', 'c', 'b'])
    expect(sortNotes(all, 'updated_desc').map((n) => n.id)).toEqual(['b', 'c', 'a'])
  })

  it('сортирует по заголовку без учёта регистра, по-русски', () => {
    expect(sortNotes(all, 'title_asc').map((n) => n.id)).toEqual(['b', 'a', 'c'])
    expect(sortNotes(all, 'title_desc').map((n) => n.id)).toEqual(['c', 'a', 'b'])
  })

  it('не меняет исходный массив', () => {
    const input = [...all]
    sortNotes(input, 'title_asc')
    expect(input.map((n) => n.id)).toEqual(['a', 'b', 'c'])
  })

  it('битую дату считает нулём, а не роняет сортировку', () => {
    const broken = note({ id: 'x', created_at: 'не дата' })
    const out = sortNotes([a, broken], 'created_asc')
    expect(out.map((n) => n.id)).toEqual(['x', 'a'])
  })
})

describe('noteBodyPreview', () => {
  it('сжимает пробелы и переносы в одну строку', () => {
    expect(noteBodyPreview(note({ id: 'a', content_plain: ' раз\n\n  два\tтри ' }))).toBe('раз два три')
  })

  it('пустой текст даёт пустую строку', () => {
    expect(noteBodyPreview(note({ id: 'a', content_plain: '   ' }))).toBe('')
  })

  it('длинный текст обрезает с многоточием', () => {
    const out = noteBodyPreview(note({ id: 'a', content_plain: 'я'.repeat(500) }))
    expect(out.endsWith('…')).toBe(true)
    expect(out.length).toBeLessThanOrEqual(141)
  })
})

describe('noteRowTooltip', () => {
  it('без заголовка показывает название по умолчанию', () => {
    expect(noteRowTooltip(note({ id: 'a' })).split('\n')[0]).toBe('Без названия')
  })

  it('добавляет папку и метки, когда они переданы', () => {
    const tip = noteRowTooltip(note({ id: 'a', title: 'Отчёт' }), {
      folderName: 'Работа',
      tagLabels: ['срочно', 'клиент'],
    })
    expect(tip).toContain('Папка: Работа')
    expect(tip).toContain('Метки: срочно, клиент')
  })

  it('без папки и меток этих строк нет', () => {
    const tip = noteRowTooltip(note({ id: 'a', title: 'Отчёт' }))
    expect(tip).not.toContain('Папка:')
    expect(tip).not.toContain('Метки:')
  })

  it('всегда показывает даты создания и изменения', () => {
    const tip = noteRowTooltip(note({ id: 'a' }))
    expect(tip).toContain('Создано:')
    expect(tip).toContain('Изменено:')
  })

  it('для удалённой заметки добавляет дату удаления', () => {
    const tip = noteRowTooltip(note({ id: 'a', deleted_at: '2026-02-02T10:00:00Z' }))
    expect(tip).toContain('Удалено:')
  })
})
