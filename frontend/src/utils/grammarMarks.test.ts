import { Schema } from '@tiptap/pm/model'
import { EditorState } from '@tiptap/pm/state'
import { describe, expect, it } from 'vitest'
import {
  applyTextKeepingMarksToTr,
  lockLineBreaks,
  mapTextBetweenOffset,
  punctuationOps,
  sameLetters,
  textEditOps,
} from './grammarMarks'

const schema = new Schema({
  nodes: {
    doc: { content: 'block+' },
    paragraph: { content: 'inline*', group: 'block' },
    text: { group: 'inline' },
  },
  marks: {
    highlight: {
      attrs: { color: { default: '#fff59d' } },
      inclusive: true,
      toDOM: () => ['mark', 0],
      parseDOM: [{ tag: 'mark' }],
    },
    textStyle: {
      attrs: { color: { default: null } },
      inclusive: true,
      toDOM: (mark) => ['span', { style: `color: ${mark.attrs.color}` }, 0],
      parseDOM: [{ tag: 'span' }],
    },
  },
})

function docOf(...paras: string[]) {
  return schema.node(
    'doc',
    null,
    paras.map((text) => schema.node('paragraph', null, text ? [schema.text(text)] : []))
  )
}

function applyTo(doc: ReturnType<Schema['node']>, from: number, to: number, next: string) {
  const state = EditorState.create({ schema, doc })
  const tr = state.tr
  const ok = applyTextKeepingMarksToTr(tr, schema, from, to, next)
  return { ok, next: state.apply(tr) }
}

describe('punctuationOps', () => {
  it('вставляет запятую, не трогая слова', () => {
    expect(punctuationOps('Итак друзья', 'Итак, друзья')).toEqual([
      { kind: 'insert', at: 4, text: ',' },
    ])
  })

  it('меняет запятую на точку', () => {
    expect(punctuationOps('привет,', 'привет.')).toEqual([
      { kind: 'insert', at: 6, text: '.' },
      { kind: 'delete', at: 6, length: 1 },
    ])
  })

  it('не предлагает замену другого слова', () => {
    expect(punctuationOps('могу', 'мочь')).toBeNull()
    expect(sameLetters('могу', 'мочь')).toBe(false)
  })

  it('ставит точку в конце фразы', () => {
    expect(punctuationOps('надо проверить отчёт', 'надо проверить отчёт.')).toEqual([
      { kind: 'insert', at: 20, text: '.' },
    ])
  })

  it('сохраняет перенос строки', () => {
    expect(punctuationOps('надо проверить\nрелиз', 'надо проверить.\nрелиз')).toEqual([
      { kind: 'insert', at: 14, text: '.' },
    ])
  })
})

describe('textEditOps', () => {
  it('правит орфографию по буквам', () => {
    expect(textEditOps('превет', 'привет')).toEqual([
      { kind: 'insert', at: 2, text: 'и' },
      { kind: 'delete', at: 2, length: 1 },
    ])
  })
})

describe('lockLineBreaks', () => {
  it('не даёт пропасть абзацу', () => {
    expect(lockLineBreaks('надо\nрелиз', 'надо. релиз')).toBe('надо. релиз\n')
  })
})

describe('mapTextBetweenOffset', () => {
  it('мапит смещение внутри абзаца', () => {
    const doc = docOf('Итак друзья')
    expect(doc.textBetween(1, 12, '\n', '\n')).toBe('Итак друзья')
    expect(mapTextBetweenOffset(doc, 1, 12, 0)).toBe(1)
    expect(mapTextBetweenOffset(doc, 1, 12, 4)).toBe(5)
  })

  it('мапит конец первой строки перед переносом', () => {
    const doc = docOf('надо', 'релиз')
    const from = 1
    const to = doc.content.size - 1
    expect(doc.textBetween(from, to, '\n', '\n')).toBe('надо\nрелиз')
    expect(mapTextBetweenOffset(doc, from, to, 4)).toBe(5)
  })

  it('мапит начало второй строки после переноса', () => {
    const doc = docOf('надо', 'релиз')
    const from = 1
    const to = doc.content.size - 1
    expect(mapTextBetweenOffset(doc, from, to, 5)).toBe(7)
  })
})

describe('applyTextKeepingMarksToTr', () => {
  it('вставляет запятую и копирует заливку и цвет', () => {
    const highlight = schema.marks.highlight.create({ color: '#fff59d' })
    const color = schema.marks.textStyle.create({ color: '#b71c1c' })
    const doc = schema.node('doc', null, [
      schema.node('paragraph', null, [schema.text('Итак друзья', [highlight, color])]),
    ])
    const { ok, next } = applyTo(doc, 1, 12, 'Итак, друзья')
    expect(ok).toBe(true)
    expect(next.doc.textContent).toBe('Итак, друзья')
    const comma = next.doc.nodeAt(5)
    expect(comma?.isText).toBe(true)
    expect(comma?.text).toContain(',')
    expect(comma?.marks.some((m) => m.type.name === 'highlight' && m.attrs.color === '#fff59d')).toBe(
      true
    )
    expect(comma?.marks.some((m) => m.type.name === 'textStyle' && m.attrs.color === '#b71c1c')).toBe(
      true
    )
  })

  it('не выносит первую букву из абзаца, если выделение с 0', () => {
    const highlight = schema.marks.highlight.create({ color: '#fff59d' })
    const color = schema.marks.textStyle.create({ color: '#2563eb' })
    const doc = schema.node('doc', null, [
      schema.node('paragraph', null, [schema.text('превет', [highlight, color])]),
    ])
    const { ok, next } = applyTo(doc, 0, doc.content.size, 'Привет')
    expect(ok).toBe(true)
    expect(next.doc.childCount).toBe(1)
    expect(next.doc.textContent).toBe('Привет')
    expect(next.doc.child(0).firstChild?.marks.some((m) => m.type.name === 'highlight')).toBe(true)
    expect(next.doc.child(0).firstChild?.marks.some((m) => m.type.name === 'textStyle')).toBe(true)
  })

  it('вставляет орфографию во втором абзаце, не сбрасывая заливку', () => {
    const highlight = schema.marks.highlight.create({ color: '#fff59d' })
    const doc = schema.node('doc', null, [
      schema.node('paragraph', null, [schema.text('надо')]),
      schema.node('paragraph', null, [schema.text('превет', [highlight])]),
    ])
    const from = 1
    const to = doc.content.size - 1
    const { ok, next } = applyTo(doc, from, to, 'надо\nпривет')
    expect(ok).toBe(true)
    expect(next.doc.textBetween(1, next.doc.content.size - 1, '\n', '\n')).toBe('надо\nпривет')
    const second = next.doc.child(1)
    expect(second.textContent).toBe('привет')
    expect(second.firstChild?.marks.some((m) => m.type.name === 'highlight')).toBe(true)
  })
})
