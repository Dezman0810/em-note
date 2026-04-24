/** Глобальные координаты указателя для маршрутизации Ctrl+Z: фокус часто в TipTap, а курсор над схемой. */

let lastPointerClient: { clientX: number; clientY: number } | null = null

/** Последний блок схемы под курсором / кликом — чтобы Ctrl+Z не уходил в TipTap, если elementFromPoint промахнулся. */
let lastExcalidrawPasteHost: HTMLDivElement | null = null

export function excalidrawTrackPointerClient(e: Pick<PointerEvent, 'clientX' | 'clientY'>) {
  lastPointerClient = { clientX: e.clientX, clientY: e.clientY }
}

export function excalidrawGetLastPointerClientCoords(): { clientX: number; clientY: number } | null {
  return lastPointerClient
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

type ResolveMode = 'strict' | 'loose'

/** strict: последний host только если курсор ещё внутри (чтобы Ctrl+Z в тексте не уезжал в схему). loose: для Cut/Copy после рамки курсор может быть вне блока. */
function resolveExcalidrawInner(mode: ResolveMode): HTMLElement | null {
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
  if (!inner || !document.contains(inner) || !last) return null
  if (mode === 'loose') return inner
  if (pointerClientInsideElement(last)) return inner
  return null
}

export function resolveExcalidrawInnerForUndoRedo(): HTMLElement | null {
  return resolveExcalidrawInner('strict')
}

/** Cut / Copy / Ctrl+X / Ctrl+C: не требовать курсор внутри rect (после drag-select курсор часто снаружи). */
export function resolveExcalidrawInnerForCutCopy(): HTMLElement | null {
  return resolveExcalidrawInner('loose')
}

export function excalidrawInnerHasFocusedTextField(inner: HTMLElement): boolean {
  const ae = document.activeElement
  if (!ae || !inner.contains(ae)) return false
  if (ae instanceof HTMLTextAreaElement || ae instanceof HTMLInputElement) return true
  if (ae instanceof HTMLElement && ae.isContentEditable) return true
  return false
}

/** Синтетические keydown для Excalidraw (фокус часто в ProseMirror). */
export function excalidrawSyntheticModKeys(): { ctrlKey: boolean; metaKey: boolean } {
  if (typeof navigator === 'undefined') return { ctrlKey: true, metaKey: false }
  const mac = /Mac|iPhone|iPod|iPad/i.test(navigator.userAgent)
  return mac ? { ctrlKey: false, metaKey: true } : { ctrlKey: true, metaKey: false }
}

/** Клик по холсту (canvas/svg), не по тулбару/полям — для Ctrl+добавления в выделение. */
export function excalidrawIsLikelyCanvasPointerTarget(
  target: EventTarget | null,
  host: HTMLDivElement | null
): boolean {
  if (!(target instanceof Element) || !host?.contains(target)) return false
  if (
    target.closest(
      'button, input, textarea, select, a[href], [role="button"], .App-toolbar, .App-bottom-bar, .mobile-misc-buttons, .main-menu, .dropdown-menu, .context-menu, .popover, .Modal, .Dialog'
    )
  ) {
    return false
  }
  /* Интерактивный слой: canvas; подписи/фигуры могут быть в SVG вне кнопок. */
  if (target instanceof HTMLCanvasElement) return true
  if (target instanceof SVGElement) return !target.closest('button')
  return false
}
