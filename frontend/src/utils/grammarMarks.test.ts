import { Schema } from '@tiptap/pm/model'
import { describe, expect, it } from 'vitest'
import { mapTextBetweenOffset, punctuationOps, sameLetters } from './grammarMarks'

const schema = new Schema({
  nodes: {
    doc: { content: 'block+' },
    paragraph: { content: 'inline*', group: 'block' },
    text: { group: 'inline' },
  },
})

function docOf(...paras: string[]) {
  return schema.node(
    'doc',
    null,
    paras.map((text) => schema.node('paragraph', null, text ? [schema.text(text)] : []))
  )
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

  it('сохраняет перенос строки', () => {
    expect(punctuationOps('надо проверить\nрелиз', 'надо проверить.\nрелиз')).toEqual([
      { kind: 'insert', at: 14, text: '.' },
    ])
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
})
