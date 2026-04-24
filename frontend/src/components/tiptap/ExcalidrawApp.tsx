import {
  CaptureUpdateAction,
  Excalidraw,
  Footer,
  MainMenu,
  restore,
  serializeAsJSON,
} from '@excalidraw/excalidraw'
import '@excalidraw/excalidraw/index.css'
import type { ExcalidrawImperativeAPI } from '@excalidraw/excalidraw/types'
import { excalidrawRegisterApi } from './excalidrawApiRegistry'
import {
  applyExcalidrawClipboardJson,
  excalidrawClipboardPayloadLooksLikeJson,
} from './excalidrawClipboardApply'
import {
  excalidrawGetLastPasteHost,
  excalidrawInnerHasFocusedTextField,
  excalidrawPasteRootInActiveFullscreen,
  excalidrawPasteRootUnderLastPointer,
  excalidrawSetLastPasteHost,
  excalidrawSyntheticModKeys,
  excalidrawTrackPointerClient,
  resolveExcalidrawInnerForCutCopy,
  resolveExcalidrawInnerForUndoRedo,
} from './excalidrawPointerBridge'
import {
  createElement,
  Fragment,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  type MouseEvent,
  type PointerEvent,
  type RefObject,
} from 'react'
import { excalidrawBarCopy, excalidrawBarCut, excalidrawBarPaste } from './excalidrawBarClipboard'
import { excalidrawGetApiForPasteRoot } from './excalidrawApiRegistry'

/** Выделение по умолчанию. Множественное: Shift+клик, рамка, Ctrl/Cmd+клик — встроенная логика Excalidraw 0.18. */
const DEFAULT_ACTIVE_TOOL = {
  type: 'selection' as const,
  customType: null as null,
  lastActiveTool: null,
  locked: false,
}

export type ExcalidrawAppProps = {
  sceneJson: string
  readOnly: boolean
  sceneKey: number
  onSceneDebounced: (json: string) => void
}

function parseScene(sceneJson: string) {
  try {
    const raw = JSON.parse(sceneJson) as Record<string, unknown>
    const elements = raw.elements
    const appState = raw.appState
    const files = raw.files
    if (Array.isArray(elements)) {
      return restore(
        {
          elements: elements as never,
          appState: (appState && typeof appState === 'object' ? appState : {}) as never,
          files: (files && typeof files === 'object' ? files : {}) as never,
        },
        null,
        null
      )
    }
    return restore(JSON.parse(sceneJson), null, null)
  } catch {
    return restore({ elements: [], appState: {}, files: {} }, null, null)
  }
}

function focusExcalidrawContainer(host: HTMLDivElement | null) {
  const inner = host?.querySelector('.excalidraw.excalidraw-container') as HTMLElement | null
  inner?.focus({ preventScroll: true })
}

/** data-excalidraw-root должен быть на узле внутри excalidrawContainerRef — иначе paste/copy не срабатывают. */
function markExcalidrawRootEl(host: HTMLDivElement | null) {
  if (!host) return
  host.querySelectorAll('[data-excalidraw-root]').forEach((el) => {
    if (host.contains(el)) el.removeAttribute('data-excalidraw-root')
  })
  const inner = host.querySelector('.excalidraw.excalidraw-container') as HTMLElement | null
  if (inner) inner.setAttribute('data-excalidraw-root', '')
}

/** Последняя позиция указателя над корнем вставки (client coords) — куда ставить вставку в координатах сцены. */
const lastPastePointerClient = new WeakMap<HTMLDivElement, { clientX: number; clientY: number }>()

function isWritableFormElement(el: Element | null): boolean {
  if (!el || !(el instanceof HTMLElement)) return false
  if (el instanceof HTMLTextAreaElement || el instanceof HTMLInputElement) return true
  if (el.isContentEditable) return true
  return false
}

function clipboardLooksLikeFileOrImagePaste(cd: DataTransfer | null): boolean {
  if (!cd) return false
  if (cd.files && cd.files.length > 0) return true
  return Array.from(cd.types ?? []).some(
    (t) => t === 'Files' || t.startsWith('image/')
  )
}

function iconCut() {
  return createElement(
    'svg',
    {
      width: 24,
      height: 24,
      viewBox: '0 0 24 24',
      fill: 'none',
      stroke: 'currentColor',
      strokeWidth: 2,
      'aria-hidden': true,
    },
    createElement('circle', { cx: 6, cy: 6, r: 3 }),
    createElement('circle', { cx: 6, cy: 18, r: 3 }),
    createElement('path', {
      d: 'M20 4L8.12 15.88M14.47 14.48L20 20M8.12 8.12L12 12',
      strokeLinecap: 'round',
      strokeLinejoin: 'round',
    })
  )
}

function iconCopy() {
  return createElement(
    'svg',
    {
      width: 24,
      height: 24,
      viewBox: '0 0 24 24',
      fill: 'none',
      stroke: 'currentColor',
      strokeWidth: 2,
      'aria-hidden': true,
    },
    createElement('rect', { x: 9, y: 9, width: 13, height: 13, rx: 2, ry: 2 }),
    createElement('path', { d: 'M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1' })
  )
}

function iconPaste() {
  return createElement(
    'svg',
    {
      width: 24,
      height: 24,
      viewBox: '0 0 24 24',
      fill: 'none',
      stroke: 'currentColor',
      strokeWidth: 2,
      'aria-hidden': true,
    },
    createElement('path', { d: 'M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2' }),
    createElement('rect', { x: 8, y: 2, width: 8, height: 4, rx: 1, ry: 1 })
  )
}

function clipFooterTool(
  pos: 'first' | 'mid' | 'last',
  title: string,
  icon: ReturnType<typeof iconCut>,
  activate: () => void | Promise<void>
) {
  return createElement(
    'div',
    { className: `excal-clip-footer-btn excal-clip-footer-btn--${pos}` },
    createElement(
      'label',
      { className: 'ToolIcon ToolIcon_size_small' },
      createElement(
        'button',
        {
          type: 'button',
          className: 'ToolIcon_type_button',
          title,
          'aria-label': title,
          onClick: (e: MouseEvent<HTMLButtonElement>) => {
            e.stopPropagation()
            e.preventDefault()
            void Promise.resolve(activate()).catch(console.error)
          },
        },
        createElement('div', { className: 'ToolIcon__icon' }, icon)
      )
    )
  )
}

function createClipboardFooter(hostRef: RefObject<HTMLDivElement | null>) {
  const withApi = (fn: typeof excalidrawBarCut | typeof excalidrawBarCopy | typeof excalidrawBarPaste) => () => {
    const root = hostRef.current
    const api = root ? excalidrawGetApiForPasteRoot(root) : null
    if (!root || !api) return
    return fn(api, root)
  }
  return createElement(
    'div',
    { className: 'undo-redo-buttons excal-embed-clipboard' },
    clipFooterTool('first', 'Вырезать (в буфер схемы)', iconCut(), withApi(excalidrawBarCut)),
    clipFooterTool('mid', 'Копировать', iconCopy(), withApi(excalidrawBarCopy)),
    clipFooterTool('last', 'Вставить', iconPaste(), withApi(excalidrawBarPaste))
  )
}

function selectedIdsFromAppState(selectedElementIds: unknown): Set<string> {
  if (!selectedElementIds || typeof selectedElementIds !== 'object') return new Set()
  const out = new Set<string>()
  for (const [k, v] of Object.entries(selectedElementIds as Record<string, unknown>)) {
    if (v) out.add(k)
  }
  return out
}

export function ExcalidrawApp({ sceneJson, readOnly, sceneKey, onSceneDebounced }: ExcalidrawAppProps) {
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const apiRef = useRef<ExcalidrawImperativeAPI | null>(null)
  const hostRef = useRef<HTMLDivElement | null>(null)
  /** Встраивание: иногда Cmd/Ctrl+клик сбрасывает прежнее выделение до одного id — восстанавливаем объединение. */
  const mergeModifierClickRef = useRef<{
    beforeIds: Set<string>
    startX: number
    startY: number
    pointerId: number
  } | null>(null)

  const initialData = useMemo(() => {
    const r = parseScene(sceneJson)
    const base = (r.appState && typeof r.appState === 'object' ? r.appState : {}) as Record<string, unknown>
    return {
      elements: r.elements,
      appState: {
        ...base,
        activeTool: DEFAULT_ACTIVE_TOOL,
        scrolledOutside: false,
      },
      files: r.files,
    }
  }, [sceneJson, sceneKey])

  const onChange = useCallback(
    (elements: readonly unknown[], appState: unknown, files: unknown) => {
      const st = appState as { scrolledOutside?: boolean }
      if (st.scrolledOutside && apiRef.current) {
        queueMicrotask(() => apiRef.current?.updateScene({ appState: { scrolledOutside: false } as const }))
      }
      if (readOnly) return
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        debounceRef.current = null
        const json = serializeAsJSON(
          elements as never,
          appState as never,
          files as never,
          'local'
        )
        onSceneDebounced(json)
      }, 450)
    },
    [readOnly, onSceneDebounced]
  )

  const excalidrawAPI = useCallback((api: ExcalidrawImperativeAPI) => {
    apiRef.current = api
    const hr = hostRef.current
    if (hr) excalidrawRegisterApi(hr, api)
    queueMicrotask(() => markExcalidrawRootEl(hostRef.current))
  }, [])

  useEffect(() => {
    return () => {
      const hr = hostRef.current
      if (hr) excalidrawRegisterApi(hr, null)
    }
  }, [sceneKey])

  useLayoutEffect(() => {
    markExcalidrawRootEl(hostRef.current)
    const id = requestAnimationFrame(() => markExcalidrawRootEl(hostRef.current))
    return () => cancelAnimationFrame(id)
  }, [sceneKey])

  /** Paste в capture: иначе ProseMirror раньше обрабатывает вставку, пока activeElement не в схеме (типично в полноэкране). */
  useEffect(() => {
    if (readOnly) return

    const onPointerOverDoc = (e: Event) => {
      const t = e.target
      if (!(t instanceof Element)) return
      const h = t.closest('[data-excalidraw-paste-root]')
      if (h instanceof HTMLDivElement) excalidrawSetLastPasteHost(h)
    }

    const onPointerDownDoc = (e: Event) => {
      if (e instanceof PointerEvent) excalidrawTrackPointerClient(e)
      const t = e.target
      if (!(t instanceof Element)) {
        excalidrawSetLastPasteHost(null)
        return
      }
      const h = t.closest('[data-excalidraw-paste-root]')
      excalidrawSetLastPasteHost(h instanceof HTMLDivElement ? h : null)
    }

    const onPointerMoveDoc = (e: Event) => {
      if (!(e instanceof PointerEvent)) return
      const pe = e
      excalidrawTrackPointerClient(pe)
      const t = pe.target
      if (!(t instanceof Element)) return
      const h = t.closest('[data-excalidraw-paste-root]')
      if (h instanceof HTMLDivElement) {
        lastPastePointerClient.set(h, { clientX: pe.clientX, clientY: pe.clientY })
      }
    }

    const readExcalidrawClipboardText = (ev: ClipboardEvent): string | null => {
      const cd = ev.clipboardData
      if (!cd) return null
      const plain = cd.getData('text/plain')
      if (plain && excalidrawClipboardPayloadLooksLikeJson(plain)) return plain
      for (const type of cd.types ?? []) {
        if (type === 'text/plain') continue
        try {
          const s = cd.getData(type)
          if (s && excalidrawClipboardPayloadLooksLikeJson(s)) return s
        } catch {
          /* */
        }
      }
      return plain || null
    }

    const onPasteCapture = (e: Event) => {
      const ev = e as ClipboardEvent
      const api = apiRef.current
      const hr = hostRef.current
      if (!api || !hr) return
      const inner = hr.querySelector('.excalidraw.excalidraw-container') as HTMLElement | null
      if (!inner) return

      const fullscreenRoot = excalidrawPasteRootInActiveFullscreen()
      const underPointer = excalidrawPasteRootUnderLastPointer()
      const forThisInstance =
        resolveExcalidrawInnerForCutCopy() === inner ||
        fullscreenRoot === hr ||
        underPointer === hr ||
        excalidrawGetLastPasteHost() === hr ||
        inner.contains(document.activeElement)
      if (!forThisInstance) return

      const ae = document.activeElement
      if (ae && inner.contains(ae) && isWritableFormElement(ae)) return

      const syncRaw = readExcalidrawClipboardText(ev)
      const syncText = syncRaw?.trim() ?? ''

      if (excalidrawClipboardPayloadLooksLikeJson(syncText)) {
        ev.preventDefault()
        ev.stopImmediatePropagation()
        inner.focus({ preventScroll: true })
        applyExcalidrawClipboardJson(api, syncText, lastPastePointerClient.get(hr) ?? null)
        return
      }

      if (syncText.length > 0) {
        return
      }

      if (clipboardLooksLikeFileOrImagePaste(ev.clipboardData)) return

      /*
       * readText() требует secure context (HTTPS или localhost). На http://<LAN-IP> без TLS
       * Clipboard API часто падает — если вызвать preventDefault, вставка «молчит».
       */
      if (!window.isSecureContext || !navigator.clipboard?.readText) return

      /* Ctrl+V: иногда getData в paste пустой, а readText() всё ещё видит JSON. */
      ev.preventDefault()
      ev.stopImmediatePropagation()
      inner.focus({ preventScroll: true })
      void navigator.clipboard.readText().then((t) => {
        if (t && excalidrawClipboardPayloadLooksLikeJson(t)) {
          applyExcalidrawClipboardJson(api, t, lastPastePointerClient.get(hr) ?? null)
        }
      })
    }

    /**
     * Копирование/вставка/undo: фокус часто остаётся в ProseMirror — событие не доходит до Excalidraw.
     * Для undo/redo отменяем исходное keydown и шлём синтетическое на контейнер (только доверенные события).
     */
    const onKeyDownCapture = (e: Event) => {
      const ke = e as KeyboardEvent
      if (!ke.isTrusted) return
      const hr = hostRef.current
      const inner = hr?.querySelector('.excalidraw.excalidraw-container') as HTMLElement | null
      if (!hr || !inner) return

      const undoInner = resolveExcalidrawInnerForUndoRedo()
      const cutInner = resolveExcalidrawInnerForCutCopy()
      const iAmUndo = undoInner === inner
      const iAmCut = cutInner === inner
      if (!iAmUndo && !iAmCut) return

      const ae = document.activeElement
      const focusInInner = !!(ae && inner.contains(ae))
      const inWritable = focusInInner && isWritableFormElement(ae)

      const mod = ke.ctrlKey || ke.metaKey
      if (!mod) return
      const k = ke.key.toLowerCase()
      const isUndo = k === 'z' && !ke.shiftKey
      const isRedo = k === 'y' || (k === 'z' && ke.shiftKey)

      if (isUndo || isRedo) {
        if (!iAmUndo) return
        if (inWritable) return
        if (!focusInInner) {
          ke.preventDefault()
          ke.stopImmediatePropagation()
          inner.focus({ preventScroll: true })
          queueMicrotask(() => {
            inner.dispatchEvent(
              new KeyboardEvent('keydown', {
                key: ke.key,
                code: ke.code,
                ctrlKey: ke.ctrlKey,
                metaKey: ke.metaKey,
                shiftKey: ke.shiftKey,
                bubbles: true,
                cancelable: true,
              })
            )
          })
        }
        return
      }

      if (k === 'c' || k === 'v' || k === 'x' || (k === 'a' && !ke.shiftKey)) {
        if (!iAmCut) return
        if (inWritable) return
        if (!focusInInner) {
          ke.preventDefault()
          ke.stopImmediatePropagation()
          inner.focus({ preventScroll: true })
          queueMicrotask(() => {
            inner.dispatchEvent(
              new KeyboardEvent('keydown', {
                key: ke.key,
                code: ke.code,
                ctrlKey: ke.ctrlKey,
                metaKey: ke.metaKey,
                shiftKey: ke.shiftKey,
                bubbles: true,
                cancelable: true,
              })
            )
          })
          return
        }
        inner.focus({ preventScroll: true })
      }
    }

    const onCutCapture = (e: Event) => {
      const ev = e as ClipboardEvent
      if (!ev.isTrusted) return
      const hr = hostRef.current
      const inner = hr?.querySelector('.excalidraw.excalidraw-container') as HTMLElement | null
      if (!inner || resolveExcalidrawInnerForCutCopy() !== inner) return
      if (inner.contains(document.activeElement)) return
      if (excalidrawInnerHasFocusedTextField(inner)) return
      ev.preventDefault()
      ev.stopImmediatePropagation()
      inner.focus({ preventScroll: true })
      const m = excalidrawSyntheticModKeys()
      queueMicrotask(() => {
        inner.dispatchEvent(
          new KeyboardEvent('keydown', {
            key: 'x',
            code: 'KeyX',
            ctrlKey: m.ctrlKey,
            metaKey: m.metaKey,
            shiftKey: false,
            bubbles: true,
            cancelable: true,
          })
        )
      })
    }

    const onCopyCapture = (e: Event) => {
      const ev = e as ClipboardEvent
      if (!ev.isTrusted) return
      const hr = hostRef.current
      const inner = hr?.querySelector('.excalidraw.excalidraw-container') as HTMLElement | null
      if (!inner || resolveExcalidrawInnerForCutCopy() !== inner) return
      if (inner.contains(document.activeElement)) return
      if (excalidrawInnerHasFocusedTextField(inner)) return
      ev.preventDefault()
      ev.stopImmediatePropagation()
      inner.focus({ preventScroll: true })
      const m = excalidrawSyntheticModKeys()
      queueMicrotask(() => {
        inner.dispatchEvent(
          new KeyboardEvent('keydown', {
            key: 'c',
            code: 'KeyC',
            ctrlKey: m.ctrlKey,
            metaKey: m.metaKey,
            shiftKey: false,
            bubbles: true,
            cancelable: true,
          })
        )
      })
    }

    document.addEventListener('pointerover', onPointerOverDoc, true)
    document.addEventListener('pointerdown', onPointerDownDoc, true)
    document.addEventListener('pointermove', onPointerMoveDoc, true)
    document.addEventListener('keydown', onKeyDownCapture, true)
    document.addEventListener('paste', onPasteCapture, true)
    document.addEventListener('cut', onCutCapture, true)
    document.addEventListener('copy', onCopyCapture, true)
    return () => {
      document.removeEventListener('pointerover', onPointerOverDoc, true)
      document.removeEventListener('pointerdown', onPointerDownDoc, true)
      document.removeEventListener('pointermove', onPointerMoveDoc, true)
      document.removeEventListener('keydown', onKeyDownCapture, true)
      document.removeEventListener('paste', onPasteCapture, true)
      document.removeEventListener('cut', onCutCapture, true)
      document.removeEventListener('copy', onCopyCapture, true)
    }
  }, [readOnly, sceneKey])

  useEffect(() => {
    if (readOnly) return
    const finishMergeIfNeeded = (e: globalThis.PointerEvent) => {
      const pending = mergeModifierClickRef.current
      if (!pending || e.pointerId !== pending.pointerId) return
      mergeModifierClickRef.current = null
      const dx = e.clientX - pending.startX
      const dy = e.clientY - pending.startY
      if (dx * dx + dy * dy > 36) return
      const beforeIds = pending.beforeIds
      if (beforeIds.size === 0) return
      queueMicrotask(() => {
        const api = apiRef.current
        if (!api) return
        const afterIds = selectedIdsFromAppState(api.getAppState().selectedElementIds)
        if (afterIds.size !== 1) return
        const only = [...afterIds][0]!
        if (beforeIds.has(only)) return
        const merged: Record<string, true> = {}
        for (const id of beforeIds) merged[id] = true
        merged[only] = true
        api.updateScene({
          appState: { selectedElementIds: merged },
          captureUpdate: CaptureUpdateAction.IMMEDIATELY,
        })
      })
    }
    const onDocUp = (e: Event) => {
      if (e instanceof window.PointerEvent) finishMergeIfNeeded(e)
    }
    const onDocCancel = (e: Event) => {
      if (!(e instanceof window.PointerEvent)) return
      if (mergeModifierClickRef.current?.pointerId === e.pointerId) mergeModifierClickRef.current = null
    }
    document.addEventListener('pointerup', onDocUp)
    document.addEventListener('pointercancel', onDocCancel)
    return () => {
      document.removeEventListener('pointerup', onDocUp)
      document.removeEventListener('pointercancel', onDocCancel)
    }
  }, [readOnly, sceneKey])

  const onHostPointerDownCapture = useCallback((e: PointerEvent<HTMLDivElement>) => {
    if (readOnly) return
    excalidrawSetLastPasteHost(hostRef.current)
    /* Фокус только с canvas: фокус на каждый клик по UI Excalidraw ломал множественное выделение и рамку. */
    if (e.target instanceof HTMLCanvasElement) {
      focusExcalidrawContainer(hostRef.current)
      const api = apiRef.current
      if (api && (e.ctrlKey || e.metaKey) && e.button === 0) {
        const beforeIds = selectedIdsFromAppState(api.getAppState().selectedElementIds)
        mergeModifierClickRef.current = {
          beforeIds,
          startX: e.clientX,
          startY: e.clientY,
          pointerId: e.pointerId,
        }
      } else {
        mergeModifierClickRef.current = null
      }
    } else {
      mergeModifierClickRef.current = null
    }
  }, [readOnly])

  /** Свой MainMenu скрывает дефолтный fallback и пункты Open/Save/Export/Поиск/Help/Reset/Socials. */
  const customMainMenu = createElement(
    MainMenu,
    null,
    createElement(MainMenu.DefaultItems.ToggleTheme),
    createElement(MainMenu.DefaultItems.ChangeCanvasBackground)
  )

  const excalChildren = readOnly
    ? customMainMenu
    : createElement(
        Fragment,
        null,
        customMainMenu,
        createElement(Footer, null, createClipboardFooter(hostRef))
      )

  const uiOptions = useMemo(
    () => ({
      canvasActions: {
        loadScene: false,
        saveToActiveFile: false,
        saveAsImage: false,
        export: false as const,
        clearCanvas: false,
        changeViewBackgroundColor: true,
        toggleTheme: true,
      },
    }),
    []
  )

  return createElement(
    'div',
    {
      ref: hostRef,
      'data-excalidraw-paste-root': '',
      style: { height: '100%', width: '100%' },
      onPointerDownCapture: onHostPointerDownCapture,
    },
    createElement(Excalidraw, {
      key: sceneKey,
      initialData,
      onChange,
      excalidrawAPI,
      detectScroll: false,
      viewModeEnabled: readOnly,
      UIOptions: uiOptions,
      children: excalChildren,
    })
  )
}
