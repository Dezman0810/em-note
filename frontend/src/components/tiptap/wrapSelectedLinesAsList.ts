import type { Node as PMNode, NodeType } from '@tiptap/pm/model'
import { Fragment } from '@tiptap/pm/model'
import { TextSelection, type EditorState, type Transaction } from '@tiptap/pm/state'

export type LineListKind = 'taskList' | 'bulletList' | 'orderedList'

function lineChunks(node: PMNode, hardBreakType: NodeType | undefined): PMNode[][] {
  const chunks: PMNode[][] = []
  let cur: PMNode[] = []
  const flush = () => {
    chunks.push(cur)
    cur = []
  }
  node.forEach((child) => {
    if (hardBreakType && child.type === hardBreakType) {
      flush()
      return
    }
    if (child.isText && child.text?.includes('\n')) {
      const parts = child.text.split('\n')
      for (let i = 0; i < parts.length; i++) {
        if (parts[i]) cur.push(child.type.schema.text(parts[i], child.marks))
        if (i < parts.length - 1) flush()
      }
      return
    }
    cur.push(child)
  })
  chunks.push(cur)
  return chunks
}

const LINE_CONTAINERS = new Set(['paragraph', 'heading'])
const LIST_TYPES = new Set(['taskList', 'bulletList', 'orderedList'])
const ITEM_TYPES = new Set(['taskItem', 'listItem'])

function collectLines(node: PMNode, hardBreakType: NodeType | undefined, out: PMNode[][]): boolean {
  if (LINE_CONTAINERS.has(node.type.name)) {
    out.push(...lineChunks(node, hardBreakType))
    return true
  }
  if (LIST_TYPES.has(node.type.name) || ITEM_TYPES.has(node.type.name) || node.type.name === 'blockquote') {
    let any = false
    node.forEach((child) => {
      if (collectLines(child, hardBreakType, out)) any = true
    })
    return any
  }
  return false
}

function makeItems(schema: EditorState['schema'], lines: PMNode[][], kind: LineListKind): PMNode[] | null {
  const paragraph = schema.nodes.paragraph
  if (!paragraph) return null
  const itemType = kind === 'taskList' ? schema.nodes.taskItem : schema.nodes.listItem
  if (!itemType) return null
  const items: PMNode[] = []
  for (const inline of lines) {
    const para = paragraph.create(null, inline.length ? inline : undefined)
    if (!itemType.validContent(Fragment.from(para))) return null
    items.push(
      kind === 'taskList' ? itemType.create({ checked: false }, para) : itemType.create(null, para)
    )
  }
  return items
}

function unwrapList(list: PMNode, paragraph: NodeType): PMNode[] {
  const out: PMNode[] = []
  list.forEach((item) => {
    if (item.childCount === 0) {
      out.push(paragraph.create())
      return
    }
    item.forEach((child) => {
      if (child.type === paragraph) out.push(child)
      else {
        const inline: PMNode[] = []
        child.forEach((c) => {
          if (c.isInline) inline.push(c)
        })
        out.push(paragraph.create(null, inline.length ? inline : undefined))
      }
    })
  })
  return out.length ? out : [paragraph.create()]
}

function findListDepth($from: Transaction['selection']['$from'], type: NodeType): number {
  for (let d = $from.depth; d > 0; d--) {
    if ($from.node(d).type === type) return d
  }
  return -1
}

function findAnyListDepth($from: Transaction['selection']['$from']): number {
  for (let d = $from.depth; d > 0; d--) {
    if (LIST_TYPES.has($from.node(d).type.name)) return d
  }
  return -1
}

function replaceListAt(
  tr: Transaction,
  listPos: number,
  listSize: number,
  nodes: PMNode | PMNode[]
): void {
  const frag = Array.isArray(nodes) ? Fragment.fromArray(nodes) : Fragment.from(nodes)
  tr.replaceWith(listPos, listPos + listSize, frag)
  tr.setSelection(TextSelection.near(tr.doc.resolve(Math.min(listPos + 1, tr.doc.content.size))))
}

/**
 * Выделенные строки → список (маркеры, номера или чек-боксы). Повтор по тому же типу снимает список.
 * Другой тип на уже готовом списке — просто меняет вид, без разборки в абзацы.
 */
export function wrapSelectedLinesAsList(
  state: EditorState,
  tr: Transaction,
  kind: LineListKind
): boolean {
  const listType = state.schema.nodes[kind]
  const paragraph = state.schema.nodes.paragraph
  const hardBreak = state.schema.nodes.hardBreak
  if (!listType || !paragraph) return false

  const selection = tr.selection
  const sameDepth = findListDepth(selection.$from, listType)
  if (sameDepth > 0) {
    const list = selection.$from.node(sameDepth)
    const listPos = selection.$from.before(sameDepth)
    const paras = unwrapList(list, paragraph)
    if (
      !selection.$from
        .node(sameDepth - 1)
        .canReplace(
          selection.$from.index(sameDepth - 1),
          selection.$from.index(sameDepth - 1) + 1,
          Fragment.fromArray(paras)
        )
    ) {
      return false
    }
    replaceListAt(tr, listPos, list.nodeSize, paras)
    return true
  }

  const otherDepth = findAnyListDepth(selection.$from)
  if (otherDepth > 0) {
    const list = selection.$from.node(otherDepth)
    const listPos = selection.$from.before(otherDepth)
    const lines: PMNode[][] = []
    if (!collectLines(list, hardBreak, lines) || !lines.length) return false
    const items = makeItems(state.schema, lines, kind)
    if (!items?.length) return false
    const next = listType.create(null, Fragment.fromArray(items))
    if (
      !selection.$from
        .node(otherDepth - 1)
        .canReplace(
          selection.$from.index(otherDepth - 1),
          selection.$from.index(otherDepth - 1) + 1,
          Fragment.from(next)
        )
    ) {
      return false
    }
    replaceListAt(tr, listPos, list.nodeSize, next)
    return true
  }

  const range = selection.$from.blockRange(selection.$to)
  if (!range) return false

  const { parent, startIndex, endIndex } = range
  if (endIndex <= startIndex) return false

  if (endIndex - startIndex === 1 && LIST_TYPES.has(parent.child(startIndex).type.name)) {
    const list = parent.child(startIndex)
    if (list.type === listType) {
      const paras = unwrapList(list, paragraph)
      if (!parent.canReplace(startIndex, endIndex, Fragment.fromArray(paras))) return false
      replaceListAt(tr, range.start, list.nodeSize, paras)
      return true
    }
    const lines: PMNode[][] = []
    if (!collectLines(list, hardBreak, lines) || !lines.length) return false
    const items = makeItems(state.schema, lines, kind)
    if (!items?.length) return false
    const next = listType.create(null, Fragment.fromArray(items))
    if (!parent.canReplace(startIndex, endIndex, Fragment.from(next))) return false
    replaceListAt(tr, range.start, list.nodeSize, next)
    return true
  }

  if (LIST_TYPES.has(parent.type.name)) {
    const lines: PMNode[][] = []
    if (!collectLines(parent, hardBreak, lines) || !lines.length) return false
    const items = makeItems(state.schema, lines, kind)
    if (!items?.length) return false
    const next = listType.create(null, Fragment.fromArray(items))
    const listPos = selection.$from.before(range.depth)
    const grand = selection.$from.node(range.depth - 1)
    const idx = selection.$from.index(range.depth - 1)
    if (!grand.canReplace(idx, idx + 1, Fragment.from(next))) return false
    replaceListAt(tr, listPos, parent.nodeSize, next)
    return true
  }

  const childPos: number[] = []
  let pos = range.start
  for (let i = startIndex; i < endIndex; i++) {
    childPos.push(pos)
    pos += parent.child(i).nodeSize
  }

  type Run = { fromIndex: number; toIndex: number; lines: PMNode[][] }
  const runs: Run[] = []
  let i = startIndex
  while (i < endIndex) {
    const chunk: PMNode[][] = []
    if (!collectLines(parent.child(i), hardBreak, chunk) || !chunk.length) {
      i += 1
      continue
    }
    const run: Run = { fromIndex: i, toIndex: i + 1, lines: chunk }
    i += 1
    while (i < endIndex) {
      const more: PMNode[][] = []
      if (!collectLines(parent.child(i), hardBreak, more) || !more.length) break
      run.lines.push(...more)
      run.toIndex = i + 1
      i += 1
    }
    runs.push(run)
  }
  if (!runs.length) return false

  for (let r = runs.length - 1; r >= 0; r--) {
    const run = runs[r]
    const items = makeItems(state.schema, run.lines, kind)
    if (!items?.length) return false
    const list = listType.create(null, Fragment.fromArray(items))
    if (!parent.canReplace(run.fromIndex, run.toIndex, Fragment.from(list))) return false
    const from = childPos[run.fromIndex - startIndex]
    const last = run.toIndex - 1 - startIndex
    const to = childPos[last] + parent.child(run.toIndex - 1).nodeSize
    tr.replaceWith(from, to, list)
  }

  const firstFrom = childPos[runs[0].fromIndex - startIndex]
  tr.setSelection(TextSelection.near(tr.doc.resolve(Math.min(firstFrom + 2, tr.doc.content.size))))
  return true
}

export function wrapSelectedLinesAsTaskList(state: EditorState, tr: Transaction): boolean {
  return wrapSelectedLinesAsList(state, tr, 'taskList')
}
