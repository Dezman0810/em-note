import { excalidrawInnerHasFocusedTextField, excalidrawSyntheticModKeys } from './excalidrawPointerBridge'

function queryInner(pasteRoot: HTMLDivElement): HTMLElement | null {
  const inner = pasteRoot.querySelector('.excalidraw.excalidraw-container')
  return inner instanceof HTMLElement ? inner : null
}

/** Кнопка панели: то же, что синтетический Ctrl/Cmd+Z на контейнере схемы. */
export function excalidrawBarUndo(pasteRoot: HTMLDivElement): void {
  const inner = queryInner(pasteRoot)
  if (!inner || excalidrawInnerHasFocusedTextField(inner)) return
  const m = excalidrawSyntheticModKeys()
  inner.focus({ preventScroll: true })
  queueMicrotask(() => {
    inner.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'z',
        code: 'KeyZ',
        ctrlKey: m.ctrlKey,
        metaKey: m.metaKey,
        shiftKey: false,
        bubbles: true,
        cancelable: true,
      })
    )
  })
}

/** Кнопка панели: Ctrl/Cmd+Shift+Z (как в обработчике ExcalidrawApp для redo). */
export function excalidrawBarRedo(pasteRoot: HTMLDivElement): void {
  const inner = queryInner(pasteRoot)
  if (!inner || excalidrawInnerHasFocusedTextField(inner)) return
  const m = excalidrawSyntheticModKeys()
  inner.focus({ preventScroll: true })
  queueMicrotask(() => {
    inner.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'z',
        code: 'KeyZ',
        ctrlKey: m.ctrlKey,
        metaKey: m.metaKey,
        shiftKey: true,
        bubbles: true,
        cancelable: true,
      })
    )
  })
}
