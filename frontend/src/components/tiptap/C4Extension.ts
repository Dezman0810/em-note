import { mergeAttributes, Node } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'

import DrawioNodeView from './DrawioNodeView.vue'
import { DEFAULT_DRAWIO_XML } from './drawioDefaultScene'

function eventIsOverDrawioUi(event: Event, target: Element): boolean {
  if (target.closest('[data-drawio-frame]')) return true
  if (target.closest('.drawio-fullscreen-shell')) return true
  if (target.closest('.drawio-host')) return true
  if (typeof event.composedPath === 'function') {
    return event.composedPath().some((node) => {
      if (!(node instanceof Element)) return false
      return (
        node.closest('[data-drawio-frame]') ||
        node.closest('.drawio-fullscreen-shell') ||
        node.closest('.drawio-host') ||
        node.hasAttribute?.('data-drawio-frame') ||
        node.classList?.contains?.('drawio-fullscreen-shell') ||
        node.classList?.contains?.('drawio-host')
      )
    })
  }
  return false
}

function interactiveInHead(target: Element): boolean {
  const tag = target.tagName
  return (
    tag === 'BUTTON' ||
    tag === 'INPUT' ||
    tag === 'SELECT' ||
    tag === 'TEXTAREA' ||
    !!target.closest('button') ||
    !!target.closest('.drawio-import') ||
    !!target.closest('label.drawio-import') ||
    !!target.closest('.block-title-field') ||
    !!target.closest('.block-title-wrap') ||
    !!(target as HTMLElement).isContentEditable
  )
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    c4Block: {
      insertC4: () => ReturnType
    }
  }
}

export const C4Block = Node.create({
  name: 'c4Block',
  group: 'block',
  atom: true,
  draggable: false,
  isolating: true,

  addAttributes() {
    return {
      scene: {
        default: DEFAULT_DRAWIO_XML,
        parseHTML: (el) => (el as HTMLElement).getAttribute('data-scene') ?? DEFAULT_DRAWIO_XML,
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
      blockId: {
        default: null,
        parseHTML: (el) => (el as HTMLElement).getAttribute('data-block-id'),
        renderHTML: (attrs) => {
          if (!attrs.blockId) return {}
          return { 'data-block-id': attrs.blockId as string }
        },
      },
      title: {
        default: null,
        parseHTML: (el) => (el as HTMLElement).getAttribute('data-title'),
        renderHTML: (attrs) => {
          const title = typeof attrs.title === 'string' ? attrs.title.trim() : ''
          if (!title) return {}
          return { 'data-title': title }
        },
      },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-type="c4-block"]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-type': 'c4-block' })]
  },

  addNodeView() {
    return VueNodeViewRenderer(DrawioNodeView, {
      stopEvent: ({ event }) => {
        const t = event.target
        if (!(t instanceof Element)) return false
        if (eventIsOverDrawioUi(event, t)) return true
        if (interactiveInHead(t)) return true
        if (t.closest('.drawio-node-head')) return false
        return true
      },
    })
  },

  addCommands() {
    return {
      insertC4:
        () =>
        ({ commands }) =>
          commands.insertContent({
            type: this.name,
            attrs: {
              scene: DEFAULT_DRAWIO_XML,
              collapsed: false,
              blockId: crypto.randomUUID(),
              title: 'Диаграмма',
            },
          }),
    }
  },
})
