import { Schema } from '@tiptap/pm/model'
import { EditorState, TextSelection } from '@tiptap/pm/state'
import { describe, expect, it } from 'vitest'
import { wrapSelectedLinesAsList } from './wrapSelectedLinesAsList'

const schema = new Schema({
  nodes: {
    doc: { content: 'block+' },
    paragraph: {
      content: 'inline*',
      group: 'block',
      toDOM: () => ['p', 0],
    },
    bulletList: {
      content: 'listItem+',
      group: 'block',
      toDOM: () => ['ul', 0],
    },
    orderedList: {
      content: 'listItem+',
      group: 'block',
      toDOM: () => ['ol', 0],
    },
    listItem: {
      content: 'paragraph',
      defining: true,
      toDOM: () => ['li', 0],
    },
    taskList: {
      content: 'taskItem+',
      group: 'block',
      toDOM: () => ['ul', 0],
    },
    taskItem: {
      content: 'paragraph',
      defining: true,
      attrs: { checked: { default: false } },
      toDOM: () => ['li', 0],
    },
    text: { group: 'inline' },
    hardBreak: {
      inline: true,
      group: 'inline',
      selectable: false,
      toDOM: () => ['br'],
    },
  },
})

function applyWrap(doc: ReturnType<Schema['node']>, from: number, to: number, kind: 'taskList' | 'bulletList' | 'orderedList') {
  const state = EditorState.create({
    schema,
    doc,
    selection: TextSelection.create(doc, from, to),
  })
  const tr = state.tr
  const ok = wrapSelectedLinesAsList(state, tr, kind)
  return { ok, next: state.apply(tr) }
}

describe('wrapSelectedLinesAsList', () => {
  it('пять абзацев → нумерованный список 1–5', () => {
    const paras = ['один', 'два', 'три', 'четыре', 'пять'].map((t) =>
      schema.node('paragraph', null, [schema.text(t)])
    )
    const doc = schema.node('doc', null, paras)
    const { ok, next } = applyWrap(doc, 1, doc.content.size - 1, 'orderedList')
    expect(ok).toBe(true)
    expect(next.doc.child(0).type.name).toBe('orderedList')
    expect(next.doc.child(0).childCount).toBe(5)
    expect(next.doc.child(0).child(0).textContent).toBe('один')
    expect(next.doc.child(0).child(4).textContent).toBe('пять')
  })

  it('пять абзацев → маркированный список', () => {
    const paras = ['a', 'b', 'c', 'd', 'e'].map((t) =>
      schema.node('paragraph', null, [schema.text(t)])
    )
    const doc = schema.node('doc', null, paras)
    const { ok, next } = applyWrap(doc, 1, doc.content.size - 1, 'bulletList')
    expect(ok).toBe(true)
    expect(next.doc.child(0).type.name).toBe('bulletList')
    expect(next.doc.child(0).childCount).toBe(5)
  })

  it('маркеры можно сменить на номера не разбирая в абзацы', () => {
    const paras = ['a', 'b'].map((t) => schema.node('paragraph', null, [schema.text(t)]))
    const doc = schema.node('doc', null, paras)
    const bullets = applyWrap(doc, 1, doc.content.size - 1, 'bulletList')
    const inside = bullets.next.doc.resolve(2)
    const state2 = EditorState.create({
      schema,
      doc: bullets.next.doc,
      selection: TextSelection.near(inside),
    })
    const tr2 = state2.tr
    expect(wrapSelectedLinesAsList(state2, tr2, 'orderedList')).toBe(true)
    const numbered = state2.apply(tr2)
    expect(numbered.doc.child(0).type.name).toBe('orderedList')
    expect(numbered.doc.child(0).childCount).toBe(2)
  })

  it('пять строк через hardBreak → пять чек-боксов', () => {
    const lines = ['один', 'два', 'три', 'четыре', 'пять']
    const inline: ReturnType<Schema['node']>[] = []
    lines.forEach((t, i) => {
      inline.push(schema.text(t))
      if (i < lines.length - 1) inline.push(schema.node('hardBreak'))
    })
    const doc = schema.node('doc', null, [schema.node('paragraph', null, inline)])
    const { ok, next } = applyWrap(doc, 1, doc.content.size - 1, 'taskList')
    expect(ok).toBe(true)
    expect(next.doc.child(0).type.name).toBe('taskList')
    expect(next.doc.child(0).childCount).toBe(5)
  })
})
