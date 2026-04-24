import { Extension } from '@tiptap/core'
import {
  excalidrawInnerHasFocusedTextField,
  excalidrawSyntheticModKeys,
  resolveExcalidrawInnerForCutCopy,
  resolveExcalidrawInnerForUndoRedo,
} from './excalidrawPointerBridge'

function dispatchToExcalidraw(inner: HTMLElement, key: string, code: string, shiftKey: boolean) {
  const m = excalidrawSyntheticModKeys()
  inner.focus({ preventScroll: true })
  queueMicrotask(() => {
    inner.dispatchEvent(
      new KeyboardEvent('keydown', {
        key,
        code,
        ctrlKey: m.ctrlKey,
        metaKey: m.metaKey,
        shiftKey,
        bubbles: true,
        cancelable: true,
      })
    )
  })
}

/**
 * Высокий приоритет: Mod+Z/Y/X/C не должны обрабатываться историей TipTap, пока целевая схема «активна»
 * (в т.ч. после рамки выделения, когда курсор уже вне блока — см. resolveExcalidrawInnerForCutCopy).
 */
export const ExcalidrawUndoGuard = Extension.create({
  name: 'excalidrawUndoGuard',
  priority: 10000,

  addKeyboardShortcuts() {
    return {
      'Mod-z': () => {
        const inner = resolveExcalidrawInnerForUndoRedo()
        if (!inner) return false
        if (excalidrawInnerHasFocusedTextField(inner)) return false
        dispatchToExcalidraw(inner, 'z', 'KeyZ', false)
        return true
      },
      'Shift-Mod-z': () => {
        const inner = resolveExcalidrawInnerForUndoRedo()
        if (!inner) return false
        if (excalidrawInnerHasFocusedTextField(inner)) return false
        dispatchToExcalidraw(inner, 'z', 'KeyZ', true)
        return true
      },
      'Mod-y': () => {
        const inner = resolveExcalidrawInnerForUndoRedo()
        if (!inner) return false
        if (excalidrawInnerHasFocusedTextField(inner)) return false
        const m = excalidrawSyntheticModKeys()
        inner.focus({ preventScroll: true })
        queueMicrotask(() => {
          if (m.metaKey) {
            inner.dispatchEvent(
              new KeyboardEvent('keydown', {
                key: 'z',
                code: 'KeyZ',
                ctrlKey: false,
                metaKey: true,
                shiftKey: true,
                bubbles: true,
                cancelable: true,
              })
            )
          } else {
            inner.dispatchEvent(
              new KeyboardEvent('keydown', {
                key: 'y',
                code: 'KeyY',
                ctrlKey: true,
                metaKey: false,
                shiftKey: false,
                bubbles: true,
                cancelable: true,
              })
            )
          }
        })
        return true
      },
      'Mod-x': () => {
        const inner = resolveExcalidrawInnerForCutCopy()
        if (!inner) return false
        if (excalidrawInnerHasFocusedTextField(inner)) return false
        if (inner.contains(document.activeElement)) return false
        dispatchToExcalidraw(inner, 'x', 'KeyX', false)
        return true
      },
      'Mod-c': () => {
        const inner = resolveExcalidrawInnerForCutCopy()
        if (!inner) return false
        if (excalidrawInnerHasFocusedTextField(inner)) return false
        if (inner.contains(document.activeElement)) return false
        dispatchToExcalidraw(inner, 'c', 'KeyC', false)
        return true
      },
    }
  },
})
