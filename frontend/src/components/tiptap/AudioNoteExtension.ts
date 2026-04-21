import { mergeAttributes, Node } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'

import AudioNoteNodeView from './AudioNoteNodeView.vue'

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    audioNote: {
      insertAudioNote: (attrs: { src: string; mime?: string; label?: string }) => ReturnType
    }
  }
}

export const AudioNoteBlock = Node.create({
  name: 'audioNote',
  group: 'block',
  atom: true,
  draggable: true,

  addAttributes() {
    return {
      src: {
        default: '',
      },
      mime: {
        default: 'audio/webm',
      },
      label: {
        default: '',
      },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-type="audio-note"]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-type': 'audio-note' })]
  },

  addNodeView() {
    return VueNodeViewRenderer(AudioNoteNodeView)
  },

  addCommands() {
    return {
      insertAudioNote:
        (attrs: { src: string; mime?: string; label?: string }) =>
        ({ commands, editor }) => {
          const pos = editor.state.doc.content.size
          return commands.insertContentAt(pos, {
            type: this.name,
            attrs: {
              src: attrs.src,
              mime: attrs.mime || 'audio/webm',
              label: attrs.label ?? '',
            },
          })
        },
    }
  },
})
