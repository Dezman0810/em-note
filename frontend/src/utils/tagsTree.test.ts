import { describe, expect, it } from 'vitest'
import { directTagIdsFromNotes } from './tagsTree'

describe('directTagIdsFromNotes', () => {
  it('не добавляет родителей — только id с самих заметок', () => {
    const ids = directTagIdsFromNotes([
      { tag_ids: ['child-a'] },
      { tag_ids: ['child-b', 'child-a'] },
      { tag_ids: [] },
    ])
    expect([...ids].sort()).toEqual(['child-a', 'child-b'])
    expect(ids.has('10.000-projects-parent')).toBe(false)
  })
})
