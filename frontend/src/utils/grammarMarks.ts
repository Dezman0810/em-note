import type { Editor } from '@tiptap/core'
import type { Node as PMNode } from '@tiptap/pm/model'

const ALNUM = /[0-9A-Za-zА-Яа-яЁё]/

export type PunctOp =
  | { kind: 'insert'; at: number; text: string }
  | { kind: 'delete'; at: number; length: number }

export function isAlnumChar(ch: string): boolean {
  return ALNUM.test(ch)
}

export function sameLetters(left: string, right: string): boolean {
  const key = (value: string) =>
    [...value]
      .filter((ch) => isAlnumChar(ch))
      .join('')
      .toLocaleLowerCase()
      .replace(/ё/g, 'е')
  return key(left) === key(right)
}

/** Только знаки: буквы те же, меняются запятые/точки/пробелы. */
export function punctuationOps(oldText: string, newText: string): PunctOp[] | null {
  if (oldText === newText) return []
  if (!sameLetters(oldText, newText)) return null
  const ops: PunctOp[] = []
  let i = 0
  let j = 0
  while (i < oldText.length || j < newText.length) {
    if (i < oldText.length && j < newText.length && oldText[i] === newText[j]) {
      i += 1
      j += 1
      continue
    }
    if (j < newText.length && newText[j] !== '\n' && !isAlnumChar(newText[j])) {
      let k = j
      while (k < newText.length && newText[k] !== '\n' && !isAlnumChar(newText[k])) {
        if (i < oldText.length && oldText[i] === newText[k]) break
        k += 1
      }
      if (k === j) return null
      ops.push({ kind: 'insert', at: i, text: newText.slice(j, k) })
      j = k
      continue
    }
    if (i < oldText.length && oldText[i] !== '\n' && !isAlnumChar(oldText[i])) {
      let k = i
      while (k < oldText.length && oldText[k] !== '\n' && !isAlnumChar(oldText[k])) {
        if (j < newText.length && newText[j] === oldText[k]) break
        k += 1
      }
      if (k === i) return null
      ops.push({ kind: 'delete', at: i, length: k - i })
      i = k
      continue
    }
    return null
  }
  return ops
}

/** Смещение в textBetween(from, to, '\\n', '\\n') → позиция в документе. */
export function mapTextBetweenOffset(doc: PMNode, from: number, to: number, offset: number): number {
  if (offset <= 0) return from
  let acc = 0
  let mapped = from
  let separated = true
  doc.nodesBetween(from, to, (node, pos) => {
    if (acc >= offset) return false
    if (node.isText) {
      const start = Math.max(from, pos)
      const end = Math.min(to, pos + node.nodeSize)
      const sliceLen = Math.max(0, end - start)
      if (acc + sliceLen >= offset) {
        mapped = start + (offset - acc)
        acc = offset
        return false
      }
      acc += sliceLen
      mapped = end
      separated = false
      return
    }
    if (node.isLeaf) {
      if (acc + 1 >= offset) {
        mapped = pos
        acc = offset
        return false
      }
      acc += 1
      mapped = pos + node.nodeSize
      separated = false
      return
    }
    if (!separated && node.isBlock) {
      acc += 1
      if (acc >= offset) return false
      separated = true
    }
    return
  })
  return mapped
}

export function applyPunctuationKeepingMarks(
  editor: Editor,
  from: number,
  to: number,
  nextText: string
): boolean {
  const oldText = editor.state.doc.textBetween(from, to, '\n', '\n')
  if (oldText === nextText) return false
  const ops = punctuationOps(oldText, nextText)
  if (!ops || !ops.length) return false
  const mapped = ops.map((op) => {
    if (op.kind === 'delete') {
      return {
        kind: 'delete' as const,
        from: mapTextBetweenOffset(editor.state.doc, from, to, op.at),
        to: mapTextBetweenOffset(editor.state.doc, from, to, op.at + op.length),
      }
    }
    return {
      kind: 'insert' as const,
      pos: mapTextBetweenOffset(editor.state.doc, from, to, op.at),
      text: op.text,
    }
  })
  mapped.sort((a, b) => {
    const pa = a.kind === 'delete' ? a.from : a.pos
    const pb = b.kind === 'delete' ? b.from : b.pos
    if (pb !== pa) return pb - pa
    if (a.kind === 'delete' && b.kind !== 'delete') return -1
    if (b.kind === 'delete' && a.kind !== 'delete') return 1
    return 0
  })
  return editor
    .chain()
    .focus()
    .command(({ tr }) => {
      const schema = editor.schema
      for (const op of mapped) {
        if (op.kind === 'delete') {
          if (op.to > op.from) tr.delete(op.from, op.to)
          continue
        }
        if (!op.text) continue
        const marks = tr.doc.resolve(op.pos).marks()
        tr.insert(op.pos, schema.text(op.text, marks))
      }
      return true
    })
    .run()
}
