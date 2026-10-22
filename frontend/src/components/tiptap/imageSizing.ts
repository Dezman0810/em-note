import type { EditorView } from '@tiptap/pm/view'

/** Минимальная ширина картинки при ресайзе, px. */
export const IMAGE_MIN_WIDTH_PX = 40

/** Ширина области текста редактора без внутренних отступов, px. */
export function editorContentWidthPx(view: EditorView): number {
  const dom = view.dom as HTMLElement
  const cs = getComputedStyle(dom)
  const pad = (parseFloat(cs.paddingLeft) || 0) + (parseFloat(cs.paddingRight) || 0)
  return Math.max(1, dom.clientWidth - pad)
}
