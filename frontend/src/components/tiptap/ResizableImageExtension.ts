import Image from '@tiptap/extension-image'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import type { EditorView } from '@tiptap/pm/view'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import ResizableImageNodeView from './ResizableImageNodeView.vue'
import { shouldPreferStructuredPasteOverImage } from '../../utils/clipboardStructuredPaste'
import { editorContentWidthPx, IMAGE_MIN_WIDTH_PX } from './imageSizing'

function parseNum(v: string | null, fallback: number | null): number | null {
  if (v == null || v === '') return fallback
  const n = Number(v)
  return Number.isFinite(n) ? n : fallback
}

/** none — у левого края без обтекания; center — по центру без обтекания; left/right — обтекание. */
function parseWrap(v: string | null): 'none' | 'center' | 'left' | 'right' {
  if (v === 'left' || v === 'right' || v === 'center') return v
  return 'none'
}

/** Натуральная ширина картинки в CSS-пикселях; null, если браузер не смог её прочитать. */
function naturalCssWidth(src: string): Promise<number | null> {
  return new Promise((resolve) => {
    // window.Image: имя Image в этом модуле занято расширением TipTap.
    const img = new window.Image()
    img.onload = () => {
      // Скриншот на экране с масштабом 150–200% хранит физические пиксели — делим,
      // чтобы картинка в заметке была того же размера, что и на экране при копировании.
      const dpr = window.devicePixelRatio > 0 ? window.devicePixelRatio : 1
      resolve(img.naturalWidth > 0 ? img.naturalWidth / dpr : null)
    }
    img.onerror = () => resolve(null)
    img.src = src
  })
}

/**
 * Постоянная ширина в px по исходному размеру: маленькую не растягиваем, а слишком
 * широкую при вставке ужимаем до ширины текста. Дальше размер от окна не зависит.
 */
function initialWidthPx(view: EditorView, cssWidth: number | null): number {
  const editorW = editorContentWidthPx(view)
  const w = cssWidth ?? editorW
  return Math.round(Math.min(editorW, Math.max(IMAGE_MIN_WIDTH_PX, w)))
}

function insertImageFromFile(view: EditorView, file: File, wrap: 'left' | 'right' | 'none') {
  const reader = new FileReader()
  reader.onload = async () => {
    const src = String(reader.result || '')
    if (!src) return
    const type = view.state.schema.nodes.image
    if (!type) return
    const natural = await naturalCssWidth(src)
    if (view.isDestroyed) return
    const widthPx =
      wrap === 'none'
        ? initialWidthPx(view, natural)
        : Math.round(editorContentWidthPx(view) * 0.48)
    const node = type.create({ src, wrap, widthPx })
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
      /** Постоянная ширина в px. Если задана — главнее widthPercent (тот остался у старых картинок). */
      widthPx: {
        default: null,
        parseHTML: (el) => parseNum(el.getAttribute('data-width-px'), null),
        renderHTML: (attrs) => {
          const n = Number(attrs.widthPx)
          if (!Number.isFinite(n) || n <= 0) return {}
          return { 'data-width-px': String(n) }
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
            if (shouldPreferStructuredPasteOverImage(event.clipboardData)) return false
            const file = firstClipboardImage(event.clipboardData)
            if (!file) return false
            event.preventDefault()
            // По умолчанию без обтекания: текст пишется под картинкой, а не справа.
            insertImageFromFile(view, file, 'none')
            return true
          },
          handleDrop: (view, event) => {
            const dt = event.dataTransfer
            const file = firstClipboardImage(dt)
            if (!file) return false
            event.preventDefault()
            insertImageFromFile(view, file, 'none')
            return true
          },
        },
      }),
      ...(this.parent?.() ?? []),
    ]
  },
})
