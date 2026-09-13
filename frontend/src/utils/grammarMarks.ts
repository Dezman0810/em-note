import type { Editor } from '@tiptap/core'
import type { Mark, Node as PMNode, Schema } from '@tiptap/pm/model'
import type { Transaction } from '@tiptap/pm/state'

const ALNUM = /[0-9A-Za-zА-Яа-яЁё]/

export type PunctOp =
  | { kind: 'insert'; at: number; text: string }
  | { kind: 'delete'; at: number; length: number }

type MappedChar = {
  pos: number
  endPos: number
  ch: string
  virtual: boolean
}

type MappedOp =
  | { kind: 'insert'; pos: number; text: string; marks: readonly Mark[] }
  | { kind: 'delete'; from: number; to: number }

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

function coalesceOps(ops: PunctOp[]): PunctOp[] {
  const out: PunctOp[] = []
  for (const op of ops) {
    const last = out[out.length - 1]
    if (op.kind === 'insert' && last?.kind === 'insert' && last.at === op.at) {
      last.text += op.text
      continue
    }
    if (op.kind === 'delete' && last?.kind === 'delete' && last.at + last.length === op.at) {
      last.length += op.length
      continue
    }
    out.push(op.kind === 'insert' ? { ...op } : { ...op })
  }
  return out
}

function lcsOps(oldText: string, newText: string): PunctOp[] {
  const n = oldText.length
  const m = newText.length
  const dp: Uint16Array[] = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1))
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] =
        oldText[i] === newText[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
    }
  }
  const ops: PunctOp[] = []
  let i = 0
  let j = 0
  while (i < n || j < m) {
    if (i < n && j < m && oldText[i] === newText[j]) {
      i += 1
      j += 1
      continue
    }
    if (j < m && (i === n || dp[i][j + 1] >= (i < n ? dp[i + 1][j] : 0))) {
      ops.push({ kind: 'insert', at: i, text: newText[j] })
      j += 1
      continue
    }
    ops.push({ kind: 'delete', at: i, length: 1 })
    i += 1
  }
  return coalesceOps(ops)
}

function greedyOps(oldText: string, newText: string): PunctOp[] {
  const ops: PunctOp[] = []
  let i = 0
  let j = 0
  const window = 64
  while (i < oldText.length || j < newText.length) {
    if (i < oldText.length && j < newText.length && oldText[i] === newText[j]) {
      i += 1
      j += 1
      continue
    }
    let found: { i: number; j: number } | null = null
    outer: for (let d = 1; d <= window; d++) {
      for (let di = 0; di <= d; di++) {
        const dj = d - di
        const ni = i + di
        const nj = j + dj
        if (ni < oldText.length && nj < newText.length && oldText[ni] === newText[nj]) {
          found = { i: ni, j: nj }
          break outer
        }
      }
    }
    if (!found) {
      if (i < oldText.length) ops.push({ kind: 'delete', at: i, length: oldText.length - i })
      if (j < newText.length) ops.push({ kind: 'insert', at: i, text: newText.slice(j) })
      break
    }
    if (found.i > i) ops.push({ kind: 'delete', at: i, length: found.i - i })
    if (found.j > j) ops.push({ kind: 'insert', at: i, text: newText.slice(j, found.j) })
    i = found.i
    j = found.j
  }
  return coalesceOps(ops)
}

/** Любая правка: запятая, точка, орфография. Переносы строк выравниваются отдельно. */
export function textEditOps(oldText: string, newText: string): PunctOp[] {
  if (oldText === newText) return []
  if (oldText.length * newText.length <= 250_000) return lcsOps(oldText, newText)
  return greedyOps(oldText, newText)
}

/** Только знаки: буквы те же, меняются запятые/точки/пробелы. */
export function punctuationOps(oldText: string, newText: string): PunctOp[] | null {
  if (oldText === newText) return []
  if (!sameLetters(oldText, newText)) return null
  return textEditOps(oldText, newText)
}

export function lockLineBreaks(oldText: string, newText: string): string {
  const oldLines = oldText.split('\n')
  const lines = newText.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n')
  if (lines.length === oldLines.length) return lines.join('\n')
  if (lines.length > oldLines.length) {
    const head = lines.slice(0, oldLines.length - 1)
    const tail = lines.slice(oldLines.length - 1).join(' ')
    return [...head, tail].join('\n')
  }
  const out = lines.slice()
  while (out.length < oldLines.length) out.push('')
  return out.join('\n')
}

export function mapTextBetweenChars(doc: PMNode, from: number, to: number): MappedChar[] {
  const chars: MappedChar[] = []
  let separated = true
  let lastEnd = from
  doc.nodesBetween(from, to, (node, pos) => {
    if (node.isText) {
      const start = Math.max(from, pos)
      const end = Math.min(to, pos + node.nodeSize)
      const text = node.text ?? ''
      for (let i = start; i < end; i++) {
        chars.push({
          pos: i,
          endPos: i + 1,
          ch: text[i - pos] ?? '',
          virtual: false,
        })
      }
      lastEnd = end
      separated = false
      return
    }
    if (node.isLeaf) {
      chars.push({
        pos,
        endPos: pos + node.nodeSize,
        ch: '\n',
        virtual: true,
      })
      lastEnd = pos + node.nodeSize
      separated = false
      return false
    }
    if (!separated && node.isBlock) {
      chars.push({
        pos: lastEnd,
        endPos: lastEnd,
        ch: '\n',
        virtual: true,
      })
      separated = true
    }
    return
  })
  return chars
}

function posAtOffset(chars: MappedChar[], from: number, to: number, offset: number): number {
  if (chars.length) {
    if (offset <= 0) return chars[0].pos
    if (offset >= chars.length) return chars[chars.length - 1].endPos
    return chars[offset].pos
  }
  return offset <= 0 ? from : to
}

/** Смещение в textBetween(from, to, '\\n', '\\n') → позиция в документе. */
export function mapTextBetweenOffset(doc: PMNode, from: number, to: number, offset: number): number {
  const chars = mapTextBetweenChars(doc, from, to)
  return posAtOffset(chars, from, to, offset)
}

function marksForInsert(doc: PMNode, pos: number): readonly Mark[] {
  const safe = Math.max(0, Math.min(pos, doc.content.size))
  const $pos = doc.resolve(safe)
  const here = $pos.marks()
  if (here.length) return here
  if ($pos.nodeBefore?.isText && $pos.nodeBefore.marks.length) return $pos.nodeBefore.marks
  if ($pos.nodeAfter?.isText && $pos.nodeAfter.marks.length) return $pos.nodeAfter.marks
  return here
}

function mappedOps(doc: PMNode, from: number, to: number, ops: PunctOp[]): MappedOp[] {
  const chars = mapTextBetweenChars(doc, from, to)
  const out: MappedOp[] = []
  for (const op of ops) {
    if (op.kind === 'insert') {
      const text = op.text.replace(/\n/g, '')
      if (!text) continue
      let pos = posAtOffset(chars, from, to, op.at)
      const $pos = doc.resolve(Math.max(0, Math.min(pos, doc.content.size)))
      if (!$pos.parent.inlineContent) {
        pos = chars[0]?.pos ?? pos
      }
      out.push({ kind: 'insert', pos, text, marks: marksForInsert(doc, pos) })
      continue
    }
    let start = -1
    let end = -1
    const flush = () => {
      if (start >= 0 && end > start) out.push({ kind: 'delete', from: start, to: end })
      start = -1
      end = -1
    }
    for (let k = 0; k < op.length; k++) {
      const ch = chars[op.at + k]
      if (!ch || ch.virtual || ch.ch === '\n') {
        flush()
        continue
      }
      if (start < 0) start = ch.pos
      end = ch.endPos
    }
    flush()
  }
  return out
}

function applyMappedOps(tr: Transaction, schema: Schema, ops: MappedOp[]): boolean {
  if (!ops.length) return false
  const ordered = ops.slice().sort((a, b) => {
    const pa = a.kind === 'delete' ? a.from : a.pos
    const pb = b.kind === 'delete' ? b.from : b.pos
    if (pb !== pa) return pb - pa
    if (a.kind === 'delete' && b.kind !== 'delete') return -1
    if (b.kind === 'delete' && a.kind !== 'delete') return 1
    return 0
  })
  for (const op of ordered) {
    if (op.kind === 'delete') {
      if (op.to > op.from) tr.delete(op.from, op.to)
      continue
    }
    if (!op.text) continue
    tr.insert(op.pos, schema.text(op.text, op.marks))
  }
  return true
}

export function applyTextKeepingMarksToTr(
  tr: Transaction,
  schema: Schema,
  from: number,
  to: number,
  nextText: string
): boolean {
  const doc = tr.doc
  if (from < 0 || to > doc.content.size || from >= to) return false
  const oldText = doc.textBetween(from, to, '\n', '\n')
  const locked = lockLineBreaks(oldText, nextText)
  if (oldText === locked) return false
  const ops = textEditOps(oldText, locked)
  const mapped = mappedOps(doc, from, to, ops)
  return applyMappedOps(tr, schema, mapped)
}

export function applyTextKeepingMarks(
  editor: Editor,
  from: number,
  to: number,
  nextText: string
): boolean {
  return editor
    .chain()
    .focus()
    .command(({ tr, state }) => applyTextKeepingMarksToTr(tr, state.schema, from, to, nextText))
    .run()
}

export function applyPunctuationKeepingMarks(
  editor: Editor,
  from: number,
  to: number,
  nextText: string
): boolean {
  return applyTextKeepingMarks(editor, from, to, nextText)
}
