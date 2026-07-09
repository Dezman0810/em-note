import { EditorState, Compartment, type Extension } from '@codemirror/state'
import { EditorView, placeholder, keymap } from '@codemirror/view'
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
import { sql } from '@codemirror/lang-sql'
import { python } from '@codemirror/lang-python'
import { noteCodeHighlighting, noteCodeTheme } from './codeMirrorTheme'
import type { CodeSnippetLanguage } from './highlightCode'

export type CodeMirrorHostOptions = {
  doc: string
  language: CodeSnippetLanguage
  editable: boolean
  placeholder?: string
  onDocChange?: (value: string) => void
}

export type CodeMirrorHost = {
  view: EditorView
  setDoc: (value: string) => void
  setLanguage: (language: CodeSnippetLanguage) => void
  setEditable: (editable: boolean) => void
  focus: () => void
  destroy: () => void
}

function languageExtension(language: CodeSnippetLanguage): Extension {
  return language === 'python' ? python() : sql({ upperCaseKeywords: true })
}

export function createCodeMirrorHost(parent: HTMLElement, options: CodeMirrorHostOptions): CodeMirrorHost {
  const languageCompartment = new Compartment()
  const editableCompartment = new Compartment()

  const extensions: Extension[] = [
    history(),
    keymap.of([...defaultKeymap, ...historyKeymap]),
    noteCodeTheme,
    noteCodeHighlighting,
    languageCompartment.of(languageExtension(options.language)),
    editableCompartment.of(EditorView.editable.of(options.editable)),
    EditorView.lineWrapping,
    EditorView.domEventHandlers({
      mousedown: (event) => {
        event.stopPropagation()
        return false
      },
      click: (event) => {
        event.stopPropagation()
        return false
      },
      keydown: (event) => {
        event.stopPropagation()
        return false
      },
      keyup: (event) => {
        event.stopPropagation()
        return false
      },
    }),
    EditorView.updateListener.of((update) => {
      if (update.docChanged) {
        options.onDocChange?.(update.state.doc.toString())
      }
    }),
  ]

  if (options.placeholder?.trim()) {
    extensions.push(placeholder(options.placeholder))
  }

  const view = new EditorView({
    state: EditorState.create({
      doc: options.doc,
      extensions,
    }),
    parent,
  })

  return {
    view,
    setDoc(value: string) {
      const current = view.state.doc.toString()
      if (current === value) return
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: value },
      })
    },
    setLanguage(language: CodeSnippetLanguage) {
      view.dispatch({
        effects: languageCompartment.reconfigure(languageExtension(language)),
      })
    },
    setEditable(editable: boolean) {
      view.dispatch({
        effects: editableCompartment.reconfigure(EditorView.editable.of(editable)),
      })
    },
    focus() {
      view.focus()
    },
    destroy() {
      view.destroy()
    },
  }
}
