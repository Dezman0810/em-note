import { mergeAttributes, Node } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import CodeSnippetNodeView from './CodeSnippetNodeView.vue'

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    codeSnippetBlock: {
      insertCodeSnippet: () => ReturnType
    }
  }
}

export const CodeSnippetBlock = Node.create({
  name: 'codeSnippetBlock',
  group: 'block',
  atom: true,
  selectable: true,
  draggable: true,

  addAttributes() {
    return {
      code: { default: '' },
      language: { default: 'sql' },
      title: { default: 'SQL' },
      collapsed: { default: false },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-code-snippet-block]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-code-snippet-block': '' })]
  },

  addNodeView() {
    return VueNodeViewRenderer(CodeSnippetNodeView)
  },

  addCommands() {
    return {
      insertCodeSnippet:
        () =>
        ({ chain }) =>
          chain()
            .insertContent({
              type: this.name,
              attrs: { code: '', language: 'sql', title: 'SQL', collapsed: false },
            })
            .run(),
    }
  },
})
