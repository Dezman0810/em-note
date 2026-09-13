import { describe, expect, it } from 'vitest'
import type { Tag } from '../api/types'
import { directTagIdsFromNotes, tagIdsInSubtrees } from './tagsTree'

function tag(id: string, parent_id: string | null, depth: number): Tag {
  return { id, user_id: 'u', parent_id, name: id, slug: id, depth, created_at: '' }
}

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

describe('tagIdsInSubtrees', () => {
  const flat = [
    tag('root', null, 0),
    tag('a', 'root', 1),
    tag('a1', 'a', 2),
    tag('b', 'root', 1),
  ]

  it('включает корень и всех потомков', () => {
    expect([...tagIdsInSubtrees(flat, ['a'])].sort()).toEqual(['a', 'a1'])
  })

  it('пустые корни — пустое множество', () => {
    expect(tagIdsInSubtrees(flat, []).size).toBe(0)
  })

  it('корень дерева покрывает всех', () => {
    expect(tagIdsInSubtrees(flat, ['root']).size).toBe(4)
  })
})
