import { mergeAttributes, Node } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'

import UploadedFileNodeView from './UploadedFileNodeView.vue'

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    uploadedFile: {
      insertUploadedFile: (attrs: {
        attachmentId: string
        filename: string
        mimeType: string
        isImage: boolean
        transcript?: string
      }) => ReturnType
    }
  }
}

export const UploadedFileBlock = Node.create({
  name: 'uploadedFile',
  group: 'block',
  atom: true,
  draggable: true,

  addAttributes() {
    return {
      attachmentId: { default: '' },
      filename: { default: '' },
      mimeType: { default: 'application/octet-stream' },
      isImage: { default: false },
      transcript: { default: '' },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-type="uploaded-file"]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-type': 'uploaded-file' })]
  },

  addNodeView() {
    return VueNodeViewRenderer(UploadedFileNodeView)
  },

  addCommands() {
    return {
      insertUploadedFile:
        (attrs: {
          attachmentId: string
          filename: string
          mimeType: string
          isImage: boolean
          transcript?: string
        }) =>
        ({ commands, editor }) => {
          const pos = editor.state.selection.from
          return commands.insertContentAt(pos, {
            type: this.name,
            attrs: {
              attachmentId: attrs.attachmentId,
              filename: attrs.filename,
              mimeType: attrs.mimeType,
              isImage: attrs.isImage,
              transcript: attrs.transcript ?? '',
            },
          })
        },
    }
  },
})
