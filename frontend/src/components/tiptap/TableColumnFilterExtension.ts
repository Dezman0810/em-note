import { Extension } from '@tiptap/core'
import { Plugin, PluginKey } from '@tiptap/pm/state'

import { cleanupLegacyTableFilterStyles, syncTableFilterDom } from './tableFilterDomSync'
import { tableFilterPluginKeyName } from './tableFilterSession'

export const tableFilterPluginKey = new PluginKey(tableFilterPluginKeyName)

export const TableColumnFilter = Extension.create({
  name: 'tableColumnFilter',

  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: tableFilterPluginKey,
        view(editorView) {
          let raf = 0
          let syncing = false

          const run = () => {
            if (syncing || editorView.isDestroyed) return
            syncing = true
            try {
              syncTableFilterDom(editorView)
            } finally {
              syncing = false
            }
          }

          const schedule = () => {
            if (raf) return
            raf = requestAnimationFrame(() => {
              raf = 0
              run()
            })
          }

          cleanupLegacyTableFilterStyles(editorView.dom)
          schedule()

          return {
            update(view, prevState) {
              if (
                view.state.doc.eq(prevState.doc) &&
                !view.state.tr.getMeta(tableFilterPluginKeyName)
              ) {
                return
              }
              schedule()
            },
            destroy() {
              if (raf) cancelAnimationFrame(raf)
              cleanupLegacyTableFilterStyles(editorView.dom)
            },
          }
        },
      }),
    ]
  },
})
