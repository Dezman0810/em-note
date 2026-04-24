/** Глобальные координаты указателя для маршрутизации Ctrl+Z: фокус часто в TipTap, а курсор над схемой. */

let lastPointerClient: { clientX: number; clientY: number } | null = null

/** Последний блок схемы под курсором / кликом — чтобы Ctrl+Z не уходил в TipTap, если elementFromPoint промахнулся. */
let lastExcalidrawPasteHost: HTMLDivElement | null = null

export function excalidrawTrackPointerClient(e: Pick<PointerEvent, 'clientX' | 'clientY'>) {
  lastPointerClient = { clientX: e.clientX, clientY: e.clientY }
}

export function excalidrawSetLastPasteHost(host: HTMLDivElement | null) {
  lastExcalidrawPasteHost = host
}

export function excalidrawGetLastPasteHost(): HTMLDivElement | null {
  return lastExcalidrawPasteHost
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

function queryInner(pasteRoot: HTMLDivElement | null): HTMLElement | null {
  if (!pasteRoot) return null
  const inner = pasteRoot.querySelector('.excalidraw.excalidraw-container')
  return inner instanceof HTMLElement ? inner : null
}

function pointerClientInsideElement(el: HTMLElement): boolean {
  if (!lastPointerClient) return false
  const r = el.getBoundingClientRect()
  const { clientX: x, clientY: y } = lastPointerClient
  return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom
}

/** Куда слать undo/redo, если фокус остался в ProseMirror. Порядок: полноэкран → точка → :hover → последний host. */
export function resolveExcalidrawInnerForUndoRedo(): HTMLElement | null {
  let inner = queryInner(excalidrawPasteRootInActiveFullscreen())
  if (inner) return inner

  inner = queryInner(excalidrawPasteRootUnderLastPointer())
  if (inner) return inner

  const hover = document.querySelector('[data-excalidraw-paste-root]:hover')
  if (hover instanceof HTMLDivElement) {
    inner = queryInner(hover)
    if (inner) return inner
  }

  const last = excalidrawGetLastPasteHost()
  inner = queryInner(last)
  if (inner && document.contains(inner) && last && pointerClientInsideElement(last)) return inner

  return null
}

export function excalidrawInnerHasFocusedTextField(inner: HTMLElement): boolean {
  const ae = document.activeElement
  if (!ae || !inner.contains(ae)) return false
  if (ae instanceof HTMLTextAreaElement || ae instanceof HTMLInputElement) return true
  if (ae instanceof HTMLElement && ae.isContentEditable) return true
  return false
}
