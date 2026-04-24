import type { ExcalidrawImperativeAPI } from '@excalidraw/excalidraw/types'

const byPasteRoot = new WeakMap<HTMLDivElement, ExcalidrawImperativeAPI>()

export function excalidrawRegisterApi(pasteRoot: HTMLDivElement | null, api: ExcalidrawImperativeAPI | null) {
  if (!pasteRoot) return
  if (api) byPasteRoot.set(pasteRoot, api)
  else byPasteRoot.delete(pasteRoot)
}

export function excalidrawGetApiForPasteRoot(pasteRoot: HTMLDivElement | null): ExcalidrawImperativeAPI | null {
  if (!pasteRoot) return null
  return byPasteRoot.get(pasteRoot) ?? null
}
