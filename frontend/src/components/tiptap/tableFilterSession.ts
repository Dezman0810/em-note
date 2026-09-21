import type { Editor } from '@tiptap/core'

import { syncTableFilterDom } from './tableFilterDomSync'

export const tableFilterPluginKeyName = 'noteTableColumnFilter'

export function refreshTableFilterDecorations(editor: Editor | null | undefined): void {
  const view = editor?.view
  if (!view || view.isDestroyed) return
  syncTableFilterDom(view)
  view.dispatch(view.state.tr.setMeta(tableFilterPluginKeyName, true))
}
