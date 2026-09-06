import Image from '@tiptap/extension-image'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import type { EditorView } from '@tiptap/pm/view'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import ResizableImageNodeView from './ResizableImageNodeView.vue'

function parseNum(v: string | null, fallback: number | null): number | null {
  if (v == null || v === '') return fallback
  const n = Number(v)
  return Number.isFinite(n) ? n : fallback
}

function parseWrap(v: string | null): 'none' | 'left' | 'right' {
  if (v === 'left' || v === 'right') return v
  return 'none'
}

function insertImageFromFile(view: EditorView, file: File, wrap: 'left' | 'right' | 'none') {
  const reader = new FileReader()
  reader.onload = () => {
    const src = String(reader.result || '')
    if (!src) return
    const type = view.state.schema.nodes.image
    if (!type) return
    const node = type.create({
      src,
      wrap,
      widthPercent: wrap === 'none' ? 100 : 48,
    })
    view.dispatch(view.state.tr.replaceSelectionWith(node).scrollIntoView())
  }
  reader.readAsDataURL(file)
}

function firstClipboardImage(cd: DataTransfer | null): File | null {
  if (!cd) return null
  for (const f of Array.from(cd.files || [])) {
    if (f.type.startsWith('image/')) return f
  }
  for (const item of Array.from(cd.items || [])) {
    if (item.kind !== 'file' || !item.type.startsWith('image/')) continue
    const f = item.getAsFile()
    if (f) return f
  }
  return null
}

/** Скриншот Ctrl+V: размер, перетаскивание и обтекание текстом слева/справа. */
export const ResizableImage = Image.extend({
  name: 'image',
  draggable: true,

  addAttributes() {
    return {
      ...this.parent?.(),
      widthPercent: {
        default: 100,
        parseHTML: (el) => parseNum(el.getAttribute('data-width-percent'), 100) ?? 100,
        renderHTML: (attrs) => {
          const n = Number(attrs.widthPercent)
          if (!Number.isFinite(n) || n === 100) return {}
          return { 'data-width-percent': String(n) }
        },
      },
      heightPx: {
        default: null,
        parseHTML: (el) => parseNum(el.getAttribute('data-height-px'), null),
        renderHTML: (attrs) => {
          const n = Number(attrs.heightPx)
          if (!Number.isFinite(n) || n <= 0) return {}
          return { 'data-height-px': String(n) }
        },
      },
      wrap: {
        default: 'none',
        parseHTML: (el) => parseWrap(el.getAttribute('data-wrap')),
        renderHTML: (attrs) => {
          const w = parseWrap(String(attrs.wrap ?? ''))
          if (w === 'none') return {}
          return { 'data-wrap': w }
        },
      },
    }
  },

  addNodeView() {
    return VueNodeViewRenderer(ResizableImageNodeView)
  },

  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: new PluginKey('resizableImageClipboard'),
        props: {
          handlePaste: (view, event) => {
            const file = firstClipboardImage(event.clipboardData)
            if (!file) return false
            event.preventDefault()
            insertImageFromFile(view, file, 'left')
            return true
          },
          handleDrop: (view, event) => {
            const dt = event.dataTransfer
            const file = firstClipboardImage(dt)
            if (!file) return false
            event.preventDefault()
            insertImageFromFile(view, file, 'left')
            return true
          },
        },
      }),
      ...(this.parent?.() ?? []),
    ]
  },
})
