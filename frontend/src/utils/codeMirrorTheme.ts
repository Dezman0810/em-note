import { EditorView } from '@codemirror/view'
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { tags as t } from '@lezer/highlight'

/** Светлая тема в духе GitHub / highlight.js для блока кода в заметке. */
export const noteCodeTheme = EditorView.theme(
  {
    '&': {
      backgroundColor: '#fff',
      color: '#24292e',
      fontSize: '13px',
    },
    '.cm-content': {
      fontFamily:
        "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
      lineHeight: '20px',
      padding: '0.55rem 0.65rem',
      caretColor: '#0f172a',
    },
    '.cm-gutters': {
      display: 'none',
    },
    '.cm-scroller': {
      overflow: 'auto',
      minHeight: '7rem',
    },
    '.cm-line': {
      padding: '0',
    },
    '&.cm-focused': {
      outline: '2px solid rgba(37, 99, 235, 0.35)',
      outlineOffset: '0px',
    },
    '.cm-placeholder': {
      color: '#94a3b8',
    },
    '.cm-selectionBackground, ::selection': {
      backgroundColor: 'rgba(37, 99, 235, 0.22) !important',
    },
  },
  { dark: false }
)

export const noteCodeHighlight = HighlightStyle.define([
  { tag: t.comment, color: '#6a737d', fontStyle: 'italic' },
  { tag: [t.string, t.special(t.string)], color: '#032f62' },
  { tag: t.number, color: '#005cc5' },
  { tag: t.bool, color: '#005cc5' },
  { tag: t.null, color: '#005cc5' },
  { tag: t.keyword, color: '#d73a49', fontWeight: '600' },
  { tag: [t.operator, t.punctuation], color: '#24292e' },
  { tag: [t.variableName, t.name], color: '#24292e' },
  { tag: [t.function(t.variableName), t.function(t.propertyName)], color: '#6f42c1' },
  { tag: t.typeName, color: '#005cc5' },
  { tag: t.propertyName, color: '#005cc5' },
])

export const noteCodeHighlighting = syntaxHighlighting(noteCodeHighlight)
