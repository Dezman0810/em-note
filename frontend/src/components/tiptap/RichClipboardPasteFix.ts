import { Extension } from '@tiptap/core'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import type { Slice } from '@tiptap/pm/model'
import { DOMParser as PMDOMParser } from '@tiptap/pm/model'
import type { EditorView } from '@tiptap/pm/view'

import { isTableSlice, resolveStructuredPasteHtml } from '../../utils/clipboardStructuredPaste'

export function insertStructuredPasteHtml(view: EditorView, html: string, event: ClipboardEvent): boolean {
  let processed = html
  view.someProp('transformPastedHTML', (f) => {
    processed = f(processed, view)
  })

  const wrap = document.createElement('div')
  wrap.innerHTML = processed

  const parser =
    view.someProp('clipboardParser') ||
    view.someProp('domParser') ||
    PMDOMParser.fromSchema(view.state.schema)

  let slice = parser.parseSlice(wrap, {
    preserveWhitespace: false,
    context: view.state.selection.$from,
  })

  view.someProp('transformPasted', (f) => {
    slice = f(slice, view, false)
  })

  if (!slice.size) return false

  event.preventDefault()
  view.dispatch(
    view.state.tr
      .replaceSelection(slice)
      .scrollIntoView()
      .setMeta('paste', true)
      .setMeta('uiEvent', 'paste'),
  )
  return true
}

/**
 * MindManager / SSMS / Office / Excel: когда ProseMirror вставляет только text/plain
 * или PNG-превью вместо таблицы — форсируем HTML (unwrap CF_HTML, TSV → table).
 */
export const RichClipboardPasteFix = Extension.create({
  name: 'richClipboardPasteFix',
  priority: 2000,

  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: new PluginKey('emRichClipboardPaste'),
        props: {
          handlePaste(view: EditorView, event: ClipboardEvent, slice?: Slice): boolean {
            const cd = event.clipboardData
            if (!cd) return false
            const ev = event as ClipboardEvent & { shiftKey?: boolean }
            if (ev.shiftKey) return false

            const $from = view.state.selection.$anchor
            for (let d = $from.depth; d >= 0; d--) {
              if ($from.node(d).type.spec.code) return false
            }

            const pasteHtml = resolveStructuredPasteHtml(cd)
            if (!pasteHtml) return false

            // Уже распарсили в table — отдаём стандартной вставке.
            if (slice && slice.size > 0 && isTableSlice(slice)) return false

            return insertStructuredPasteHtml(view, pasteHtml, event)
          },
        },
      }),
    ]
  },
})
