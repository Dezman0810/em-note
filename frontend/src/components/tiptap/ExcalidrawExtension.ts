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
    return VueNodeViewRenderer(ExcalidrawNodeView)
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
