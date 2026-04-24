import { Extension } from '@tiptap/core'
import {
  excalidrawInnerHasFocusedTextField,
  resolveExcalidrawInnerForUndoRedo,
} from './excalidrawPointerBridge'

function modKeysForSynthetic(): { ctrlKey: boolean; metaKey: boolean } {
  if (typeof navigator === 'undefined') return { ctrlKey: true, metaKey: false }
  const mac = /Mac|iPhone|iPod|iPad/i.test(navigator.userAgent)
  return mac ? { ctrlKey: false, metaKey: true } : { ctrlKey: true, metaKey: false }
}

function dispatchUndo(inner: HTMLElement) {
  const m = modKeysForSynthetic()
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

function dispatchRedo(inner: HTMLElement) {
  const m = modKeysForSynthetic()
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
}

/**
 * Высокий приоритет: пока есть «активная» схема, Mod+Z/Y не должны попадать в историю TipTap
 * (иначе откатывается весь node / документ).
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
        dispatchUndo(inner)
        return true
      },
      'Shift-Mod-z': () => {
        const inner = resolveExcalidrawInnerForUndoRedo()
        if (!inner) return false
        if (excalidrawInnerHasFocusedTextField(inner)) return false
        dispatchRedo(inner)
        return true
      },
      'Mod-y': () => {
        const inner = resolveExcalidrawInnerForUndoRedo()
        if (!inner) return false
        if (excalidrawInnerHasFocusedTextField(inner)) return false
        dispatchRedo(inner)
        return true
      },
    }
  },
})
