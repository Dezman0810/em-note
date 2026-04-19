import type { Node as PMNode } from '@tiptap/pm/model'
import { Fragment, Slice } from '@tiptap/pm/model'
import type { EditorState, Transaction } from '@tiptap/pm/state'

function paragraphHasHardBreak(node: PMNode, hardBreakType: PMNode['type']): boolean {
  let found = false
  node.forEach((c) => {
    if (c.type === hardBreakType) found = true
  })
  return found
}

/**
 * Перед включением чек-листа: каждая «строка» внутри абзаца (Shift+Enter / вставка с \n)
 * становится отдельным абзацем, чтобы у каждой был свой чекбокс.
 */
export function splitSelectedBlocksAtHardBreaks(state: EditorState, tr: Transaction): void {
  const paragraph = state.schema.nodes.paragraph
  const hardBreakType = state.schema.nodes.hardBreak
  if (!paragraph || !hardBreakType) return

  const range = tr.selection.$from.blockRange(tr.selection.$to)
  if (!range) return

  const { parent, startIndex, endIndex } = range

  const jobs: { pos: number; node: PMNode }[] = []
  let p = range.start
  for (let i = 0; i < startIndex; i++) p += parent.child(i).nodeSize
  for (let i = startIndex; i < endIndex; i++) {
    const node = parent.child(i)
    if (node.type === paragraph && paragraphHasHardBreak(node, hardBreakType)) {
      jobs.push({ pos: p, node })
    }
    p += node.nodeSize
  }

  for (let j = jobs.length - 1; j >= 0; j--) {
    const { pos, node } = jobs[j]
    const chunks: PMNode[][] = []
    let cur: PMNode[] = []
    node.forEach((child) => {
      if (child.type === hardBreakType) {
        chunks.push(cur)
        cur = []
      } else {
        cur.push(child)
      }
    })
    chunks.push(cur)

    const newParas = chunks.map((inline) => paragraph.create(null, inline))
    if (newParas.length <= 1) continue
    tr.replace(pos, pos + node.nodeSize, new Slice(Fragment.fromArray(newParas), 0, 0))
  }
}
