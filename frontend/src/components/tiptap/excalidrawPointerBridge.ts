/** Глобальные координаты указателя для маршрутизации Ctrl+Z: фокус часто в TipTap, а курсор над схемой. */

let lastPointerClient: { clientX: number; clientY: number } | null = null

export function excalidrawTrackPointerClient(e: Pick<PointerEvent, 'clientX' | 'clientY'>) {
  lastPointerClient = { clientX: e.clientX, clientY: e.clientY }
}

export function excalidrawPasteRootUnderLastPointer(): HTMLDivElement | null {
  if (!lastPointerClient) return null
  const el = document.elementFromPoint(lastPointerClient.clientX, lastPointerClient.clientY)
  if (!(el instanceof Element)) return null
  const root = el.closest('[data-excalidraw-paste-root]')
  return root instanceof HTMLDivElement ? root : null
}
