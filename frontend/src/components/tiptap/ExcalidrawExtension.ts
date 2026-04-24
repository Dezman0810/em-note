import { mergeAttributes, Node } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'

import ExcalidrawNodeView from './ExcalidrawNodeView.vue'
import { DEFAULT_EXCALIDRAW_SCENE } from './excalidrawDefaultScene'

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
  draggable: true,
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
       * По умолчанию TipTap для selectable atom даёт ProseMirror обработать mousedown — выделяется
       * весь блок схемы, а не фигуры внутри Excalidraw (ломается Ctrl/Cmd+клик и обычный клик по холсту).
       * Внутри paste-root события полностью остаются у Excalidraw.
       */
      stopEvent: ({ event }) => {
        const t = event.target
        if (!(t instanceof Element)) return false
        if (t.closest('[data-excalidraw-paste-root]')) return true

        const el = t as HTMLElement
        const tag = el.tagName
        if (tag === 'LABEL' || tag === 'BUTTON' || tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') {
          return true
        }
        if (el.isContentEditable) return true

        return false
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
            attrs: { scene: DEFAULT_EXCALIDRAW_SCENE },
          }),
    }
  },
})
