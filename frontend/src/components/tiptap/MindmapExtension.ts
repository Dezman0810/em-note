import { mergeAttributes, Node } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'

import MindmapNodeView from './MindmapNodeView.vue'
import { DEFAULT_MINDMAP_SCENE } from './mindmapDefaultScene'

function eventIsOverMindmapUi(event: Event, target: Element): boolean {
  if (target.closest('[data-mindmap-frame]')) return true
  if (target.closest('.mindmap-fullscreen-shell')) return true
  if (target.closest('.mindmap-host')) return true
  if (typeof event.composedPath === 'function') {
    return event.composedPath().some((node) => {
      if (!(node instanceof Element)) return false
      return (
        node.closest('[data-mindmap-frame]') ||
        node.closest('.mindmap-fullscreen-shell') ||
        node.closest('.mindmap-host') ||
        node.hasAttribute?.('data-mindmap-frame') ||
        node.classList?.contains?.('mindmap-fullscreen-shell') ||
        node.classList?.contains?.('mindmap-host')
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
    !!target.closest('.block-title-field') ||
    !!target.closest('.block-title-wrap') ||
    !!(target as HTMLElement).isContentEditable
  )
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    mindmapBlock: {
      insertMindmap: () => ReturnType
    }
  }
}

export const MindmapBlock = Node.create({
  name: 'mindmapBlock',
  group: 'block',
  atom: true,
  draggable: false,
  isolating: true,

  addAttributes() {
    return {
      scene: {
        default: DEFAULT_MINDMAP_SCENE,
        parseHTML: (el) => (el as HTMLElement).getAttribute('data-scene') ?? DEFAULT_MINDMAP_SCENE,
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
    return [{ tag: 'div[data-type="mindmap-block"]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-type': 'mindmap-block' })]
  },

  addNodeView() {
    return VueNodeViewRenderer(MindmapNodeView, {
      stopEvent: ({ event }) => {
        const t = event.target
        if (!(t instanceof Element)) return false
        if (eventIsOverMindmapUi(event, t)) return true
        if (interactiveInHead(t)) return true
        if (t.closest('.mindmap-node-head')) return false
        return true
      },
    })
  },

  addCommands() {
    return {
      insertMindmap:
        () =>
        ({ commands }) =>
          commands.insertContent({
            type: this.name,
            attrs: {
              scene: DEFAULT_MINDMAP_SCENE,
              collapsed: false,
              blockId: crypto.randomUUID(),
              title: 'Карта',
            },
          }),
    }
  },
})
