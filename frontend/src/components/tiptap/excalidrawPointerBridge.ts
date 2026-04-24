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

/**
 * Оболочка полноэкранного режима из ExcalidrawNodeView (нативный :fullscreen или CSS-fallback).
 * Пока схема на весь экран, Ctrl+Z должен идти только в Excalidraw — иначе TipTap откатывает весь блок.
 */
export function excalidrawPasteRootInActiveFullscreen(): HTMLDivElement | null {
  const shell =
    document.querySelector('.excal-fullscreen-shell:fullscreen') ??
    document.querySelector('.excal-fullscreen-shell--fallback')
  if (!(shell instanceof Element)) return null
  const root = shell.querySelector('[data-excalidraw-paste-root]')
  return root instanceof HTMLDivElement ? root : null
}
