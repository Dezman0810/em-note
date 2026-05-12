import { mergeAttributes, Node } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'

import ExcalidrawNodeView from './ExcalidrawNodeView.vue'
import { DEFAULT_EXCALIDRAW_SCENE } from './excalidrawDefaultScene'

/**
 * Область рисования Excalidraw зум/рамка/канва — события не отдаём ProseMirror иначе
 * блок целиком уезжает вместо выделения и ломаются ЛКМ/ПКМ как в полноэкране.
 *
 * `.excal-host` держится отдельно: часть узлов деревa (слои поверх канвы) может
 * не давать успешный `closest(...)` без composedPath().
 */
function eventIsOverExcalidrawEmbeddedUi(event: Event, target: Element): boolean {
  if (target.closest('[data-excalidraw-paste-root]')) return true
  /* paste-root — потомок .excal-host; в :fullscreen target часто retarget на shell/host */
  if (target.closest('.excal-fullscreen-shell')) return true
  if (target.closest('.excal-host')) return true
  if (typeof event.composedPath === 'function') {
    return event.composedPath().some((node) => {
      if (!(node instanceof Element)) return false
      if (node.closest('[data-excalidraw-paste-root]')) return true
      if (node.closest('.excal-fullscreen-shell')) return true
      if (node.closest('.excal-host')) return true
      return (
        node.hasAttribute?.('data-excalidraw-paste-root') ||
        node.classList?.contains?.('excal-fullscreen-shell') ||
        node.classList?.contains?.('excal-host')
      )
    })
  }
  return false
}

function interactiveInHeadOrEditor(target: Element): boolean {
  const tag = target.tagName
  if (
    tag === 'BUTTON' ||
    tag === 'INPUT' ||
    tag === 'SELECT' ||
    tag === 'TEXTAREA' ||
    target.closest('button') ||
    target.closest('.excal-import') ||
    target.closest('label.excal-import')
  ) {
    return true
  }
  if ((target as HTMLElement).isContentEditable) return true
  return false
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    excalidrawBlock: {
      insertExcalidraw: () => ReturnType
    }
  }
}

export const ExcalidrawBlock = Node.create({
  name: 'excalidrawBlock',
  group: 'block',
  atom: true,
  /** Перетаскивание блока отключено: ломало ЛКМ/ПКМ на холсте. Перемещение — Вырезать / Вставить. */
  draggable: false,
  isolating: true,

  addAttributes() {
    return {
      scene: {
        default: DEFAULT_EXCALIDRAW_SCENE,
        parseHTML: (el) => (el as HTMLElement).getAttribute('data-scene') ?? DEFAULT_EXCALIDRAW_SCENE,
        renderHTML: (attrs) => {
          if (!attrs.scene) return {}
          return { 'data-scene': attrs.scene as string }
        },
      },
      collapsed: {
        default: false,
        parseHTML: (el) => (el as HTMLElement).getAttribute('data-collapsed') === 'true',
        renderHTML: (attrs) => (attrs.collapsed ? { 'data-collapsed': 'true' } : {}),
      },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-type="excalidraw-block"]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-type': 'excalidraw-block' })]
  },

  addNodeView() {
    return VueNodeViewRenderer(ExcalidrawNodeView, {
      /**
       * Холст / UI Excalidraw — события не отдаём ProseMirror (рисование, рамка, ПКМ).
       * Шапка: клик по фону (не по кнопкам/импорту) — отдаём PM, чтобы можно было выделить узел для Вырезать.
       * Перетаскивание узла выключено (draggable: false).
       */
      stopEvent: ({ event }) => {
        const t = event.target
        if (!(t instanceof Element)) return false

        if (eventIsOverExcalidrawEmbeddedUi(event, t)) return true

        if (interactiveInHeadOrEditor(t)) return true

        if (t.closest('.excalidraw-node-head')) return false

        return true
      },
    })
  },

  addCommands() {
    return {
      insertExcalidraw:
        () =>
        ({ commands }) =>
          commands.insertContent({
            type: this.name,
            attrs: { scene: DEFAULT_EXCALIDRAW_SCENE, collapsed: false },
          }),
    }
  },
})
