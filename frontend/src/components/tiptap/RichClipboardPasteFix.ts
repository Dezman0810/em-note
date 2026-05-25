import { Extension } from '@tiptap/core'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import type { EditorView } from '@tiptap/pm/view'

import { normalizePastedRichCodeHtml } from '../../utils/normalizePastedRichCodeHtml'

/**
 * MindManager / SSMS / Office: когда ProseMirror вставляет только text/plain без цветов,
 * форсируем вставку разобранного HTML (unwrap CF_HTML + нормализация).
 */
export const RichClipboardPasteFix = Extension.create({
  name: 'richClipboardPasteFix',
  priority: 1060,

  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: new PluginKey('emRichClipboardPaste'),
        props: {
          handlePaste(view: EditorView, event: ClipboardEvent): boolean {
            const cd = event.clipboardData
            if (!cd) return false
            // DOM: ClipboardEvent в lib DOM не содержит shiftKey; в браузере для paste он бывает наследием UIEvent — проверка опционально
            const ev = event as ClipboardEvent & { shiftKey?: boolean }
            if (ev.shiftKey) return false
            if (cd.files?.length) return false

            const $from = view.state.selection.$anchor
            for (let d = $from.depth; d >= 0; d--) {
              if ($from.node(d).type.spec.code) return false
            }

            const rawHtml = cd.getData('text/html')
            if (!rawHtml?.trim()) return false

            const normalized = normalizePastedRichCodeHtml(rawHtml).trim()
            if (!normalized) return false

            const cfHtml = /^Version:\s*\d/m.test(rawHtml)
            const hasBlocks =
              /<(?:p|div|table|tr|td|th|ul|ol|li|thead|tbody|caption|colgroup|svg|picture|figure|h[1-6])\b/i.test(
                normalized,
              )
            const hasInlineRich =
              /<span\b[^>]*style\s*=/i.test(normalized) ||
              /<font\b/i.test(normalized)

            if (!cfHtml && !hasBlocks && !hasInlineRich) return false

            return view.pasteHTML(normalized, event)
          },
        },
      }),
    ]
  },
})
