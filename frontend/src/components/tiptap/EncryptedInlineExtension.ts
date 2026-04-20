import { mergeAttributes, Node } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'

import EncryptedInlineView from './EncryptedInlineView.vue'

export const EncryptedInline = Node.create({
  name: 'encryptedInline',
  group: 'inline',
  inline: true,
  atom: true,
  selectable: true,
  draggable: true,

  addAttributes() {
    return {
      version: {
        default: 1,
        parseHTML: (el) => parseInt((el as HTMLElement).getAttribute('data-version') || '1', 10),
        renderHTML: (attrs) => ({ 'data-version': String(attrs.version ?? 1) }),
      },
      salt: {
        default: '',
        parseHTML: (el) => (el as HTMLElement).getAttribute('data-salt') ?? '',
        renderHTML: (attrs) => {
          const s = attrs.salt as string
          return s ? { 'data-salt': s } : {}
        },
      },
      iv: {
        default: '',
        parseHTML: (el) => (el as HTMLElement).getAttribute('data-iv') ?? '',
        renderHTML: (attrs) => {
          const s = attrs.iv as string
          return s ? { 'data-iv': s } : {}
        },
      },
      ciphertext: {
        default: '',
        parseHTML: (el) => (el as HTMLElement).getAttribute('data-ciphertext') ?? '',
        renderHTML: (attrs) => {
          const s = attrs.ciphertext as string
          return s ? { 'data-ciphertext': s } : {}
        },
      },
    }
  },

  parseHTML() {
    return [{ tag: 'span[data-type="encrypted-inline"]' }]
  },

  renderHTML({ HTMLAttributes, node }) {
    return [
      'span',
      mergeAttributes(HTMLAttributes, {
        'data-type': 'encrypted-inline',
        'data-version': String(node.attrs.version ?? 1),
        'data-salt': node.attrs.salt as string,
        'data-iv': node.attrs.iv as string,
        'data-ciphertext': node.attrs.ciphertext as string,
      }),
    ]
  },

  addNodeView() {
    return VueNodeViewRenderer(EncryptedInlineView)
  },
})
