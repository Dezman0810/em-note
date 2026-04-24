import {
  CaptureUpdateAction,
  convertToExcalidrawElements,
  Excalidraw,
  getCommonBounds,
  MainMenu,
  newElementWith,
  restore,
  serializeAsJSON,
  viewportCoordsToSceneCoords,
} from '@excalidraw/excalidraw'
import '@excalidraw/excalidraw/index.css'
import type { ExcalidrawImperativeAPI } from '@excalidraw/excalidraw/types'
import type { ExcalidrawElement } from '@excalidraw/excalidraw/element/types'
import {
  excalidrawGetLastPasteHost,
  excalidrawPasteRootInActiveFullscreen,
  excalidrawPasteRootUnderLastPointer,
  excalidrawSetLastPasteHost,
  excalidrawTrackPointerClient,
} from './excalidrawPointerBridge'
import {
  createElement,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  type PointerEvent,
} from 'react'

/**
 * Выделение по умолчанию. Множественное: Shift+клик, рамка, и Ctrl/Cmd+клик (добавление/снятие) — см. onPointerUp.
 */
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

function stringLooksLikeExcalidrawClipboardPayload(s: string): boolean {
  return (
    s.includes('excalidraw/clipboard') || s.includes('excalidraw-api/clipboard')
  )
}

function clipboardLooksLikeFileOrImagePaste(cd: DataTransfer | null): boolean {
  if (!cd) return false
  if (cd.files && cd.files.length > 0) return true
  return Array.from(cd.types ?? []).some(
    (t) => t === 'Files' || t.startsWith('image/')
  )
}

function scenePointAtClient(
  api: ExcalidrawImperativeAPI,
  clientX: number,
  clientY: number
): { x: number; y: number } {
  const { zoom, offsetLeft, offsetTop, scrollX, scrollY } = api.getAppState()
  return viewportCoordsToSceneCoords(
    { clientX, clientY },
    { zoom, offsetLeft, offsetTop, scrollX, scrollY }
  )
}

/** Смещает вставку: левый верхний угол общего bbox группы совпадает с точкой под курсором (или с центром видимой области). */
function applyExcalidrawClipboardText(
  api: ExcalidrawImperativeAPI,
  text: string,
  pasteRootHost: HTMLDivElement | null
): void {
  const trimmed = text.trim()
  if (!stringLooksLikeExcalidrawClipboardPayload(trimmed)) return
  let raw: { type?: unknown; elements?: unknown; files?: unknown }
  try {
    raw = JSON.parse(trimmed) as { type?: unknown; elements?: unknown; files?: unknown }
  } catch {
    return
  }
  const okType =
    raw.type === 'excalidraw/clipboard' || raw.type === 'excalidraw-api/clipboard'
  if (!okType || !Array.isArray(raw.elements)) return
  try {
    const restored = restore(
      {
        elements: raw.elements as never,
        appState: {} as never,
        files: (raw.files && typeof raw.files === 'object' ? raw.files : {}) as never,
      },
      null,
      null
    )
    const pastedRaw = convertToExcalidrawElements(restored.elements as never, { regenerateIds: true })
    const pasted = pastedRaw as readonly ExcalidrawElement[]
    if (pasted.length === 0) return

    const [minX, minY] = getCommonBounds(pasted)

    const app = api.getAppState()
    const client = pasteRootHost ? lastPastePointerClient.get(pasteRootHost) : undefined
    const targetScene = client
      ? scenePointAtClient(api, client.clientX, client.clientY)
      : scenePointAtClient(api, app.offsetLeft + app.width / 2, app.offsetTop + app.height / 2)

    const dx = targetScene.x - minX
    const dy = targetScene.y - minY
    const shifted = pasted.map((el) => newElementWith(el, { x: el.x + dx, y: el.y + dy }))

    const cur = api.getSceneElements()
    api.updateScene({
      elements: [...cur, ...shifted],
      captureUpdate: CaptureUpdateAction.IMMEDIATELY,
    })
    if (restored.files && Object.keys(restored.files).length > 0) {
      api.addFiles(Object.values(restored.files))
    }
  } catch (err) {
    console.error('Excalidraw paste bridge failed', err)
  }
}

export function ExcalidrawApp({ sceneJson, readOnly, sceneKey, onSceneDebounced }: ExcalidrawAppProps) {
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const apiRef = useRef<ExcalidrawImperativeAPI | null>(null)
  const hostRef = useRef<HTMLDivElement | null>(null)
  /** Снимок выделения до Ctrl/Cmd+клика — Excalidraw сам по Cmd не добавляет в выделение. */
  const prevSelOnCtrlPointerRef = useRef<Record<string, boolean> | null>(null)

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
    queueMicrotask(() => markExcalidrawRootEl(hostRef.current))
  }, [])

  useLayoutEffect(() => {
    markExcalidrawRootEl(hostRef.current)
    const id = requestAnimationFrame(() => markExcalidrawRootEl(hostRef.current))
    return () => cancelAnimationFrame(id)
  }, [sceneKey])

  useEffect(() => {
    const api = apiRef.current
    if (!api || readOnly) return
    const unsubDown = api.onPointerDown((activeTool, _pds, event) => {
      if (event.target instanceof HTMLCanvasElement) {
        focusExcalidrawContainer(hostRef.current)
      }
      if (activeTool.type !== 'selection') {
        prevSelOnCtrlPointerRef.current = null
        return
      }
      if (!(event.ctrlKey || event.metaKey)) {
        prevSelOnCtrlPointerRef.current = null
        return
      }
      const t = event.target
      if (!(t instanceof HTMLElement) || !hostRef.current?.contains(t)) {
        prevSelOnCtrlPointerRef.current = null
        return
      }
      if (!(t instanceof HTMLCanvasElement)) {
        prevSelOnCtrlPointerRef.current = null
        return
      }
      prevSelOnCtrlPointerRef.current = { ...api.getAppState().selectedElementIds }
    })
    const unsubUp = api.onPointerUp((activeTool, pds, _ev) => {
      const snap = prevSelOnCtrlPointerRef.current
      prevSelOnCtrlPointerRef.current = null
      if (!snap) return
      if (activeTool.type !== 'selection') return
      if (!pds.withCmdOrCtrl) return
      if (pds.boxSelection.hasOccurred) return
      if (pds.drag.hasOccurred) return
      if (pds.resize.isResizing) return
      if (!pds.hit.element) return

      const st = api.getAppState()
      const next = st.selectedElementIds
      const prevKeys = Object.keys(snap).filter((k) => snap[k])
      const nextKeys = Object.keys(next).filter((k) => next[k])
      if (nextKeys.length === 0) return

      if (nextKeys.length === 1) {
        const id = nextKeys[0]
        if (prevKeys.includes(id) && prevKeys.length > 1) {
          const merged: Record<string, true> = {}
          for (const k of prevKeys) {
            if (k !== id) merged[k] = true
          }
          api.updateScene({
            appState: { selectedElementIds: merged },
            captureUpdate: CaptureUpdateAction.IMMEDIATELY,
          })
          return
        }
      }
      const merged = { ...snap, ...next } as Record<string, true>
      api.updateScene({
        appState: { selectedElementIds: merged },
        captureUpdate: CaptureUpdateAction.IMMEDIATELY,
      })
    })
    return () => {
      unsubDown()
      unsubUp()
    }
  }, [readOnly, sceneKey])

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
      if (plain && stringLooksLikeExcalidrawClipboardPayload(plain)) return plain
      for (const type of cd.types ?? []) {
        if (type === 'text/plain') continue
        try {
          const s = cd.getData(type)
          if (s && stringLooksLikeExcalidrawClipboardPayload(s)) return s
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
        fullscreenRoot === hr ||
        underPointer === hr ||
        excalidrawGetLastPasteHost() === hr ||
        inner.contains(document.activeElement)
      if (!forThisInstance) return

      const ae = document.activeElement
      if (ae && inner.contains(ae) && isWritableFormElement(ae)) return

      const syncRaw = readExcalidrawClipboardText(ev)
      const syncText = syncRaw?.trim() ?? ''

      if (stringLooksLikeExcalidrawClipboardPayload(syncText)) {
        ev.preventDefault()
        ev.stopImmediatePropagation()
        inner.focus({ preventScroll: true })
        applyExcalidrawClipboardText(api, syncText, hr)
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
        if (t && stringLooksLikeExcalidrawClipboardPayload(t)) {
          applyExcalidrawClipboardText(api, t, hr)
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

      const fullscreenRoot = excalidrawPasteRootInActiveFullscreen()
      const underPointer = excalidrawPasteRootUnderLastPointer()
      const forThisInstance =
        fullscreenRoot === hr ||
        underPointer === hr ||
        excalidrawGetLastPasteHost() === hr ||
        inner.contains(document.activeElement)
      if (!forThisInstance) return

      const ae = document.activeElement
      const focusInInner = !!(ae && inner.contains(ae))
      const inWritable = focusInInner && isWritableFormElement(ae)

      const mod = ke.ctrlKey || ke.metaKey
      if (!mod) return
      const k = ke.key.toLowerCase()
      const isUndo = k === 'z' && !ke.shiftKey
      const isRedo = k === 'y' || (k === 'z' && ke.shiftKey)

      if (isUndo || isRedo) {
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

      if (focusInInner) return
      if (
        fullscreenRoot !== hr &&
        underPointer !== hr &&
        excalidrawGetLastPasteHost() !== hr
      )
        return
      if (k === 'c' || k === 'v' || k === 'x' || (k === 'a' && !ke.shiftKey)) {
        inner.focus({ preventScroll: true })
      }
    }

    document.addEventListener('pointerover', onPointerOverDoc, true)
    document.addEventListener('pointerdown', onPointerDownDoc, true)
    document.addEventListener('pointermove', onPointerMoveDoc, true)
    document.addEventListener('keydown', onKeyDownCapture, true)
    document.addEventListener('paste', onPasteCapture, true)
    return () => {
      document.removeEventListener('pointerover', onPointerOverDoc, true)
      document.removeEventListener('pointerdown', onPointerDownDoc, true)
      document.removeEventListener('pointermove', onPointerMoveDoc, true)
      document.removeEventListener('keydown', onKeyDownCapture, true)
      document.removeEventListener('paste', onPasteCapture, true)
    }
  }, [readOnly, sceneKey])

  const onHostPointerDownCapture = useCallback((e: PointerEvent<HTMLDivElement>) => {
    if (readOnly) return
    excalidrawSetLastPasteHost(hostRef.current)
    /* Фокус только с canvas: фокус на каждый клик по UI Excalidraw ломал множественное выделение и рамку. */
    if (e.target instanceof HTMLCanvasElement) {
      focusExcalidrawContainer(hostRef.current)
    }
  }, [readOnly])

  /** Свой MainMenu скрывает дефолтный fallback и пункты Open/Save/Export/Поиск/Help/Reset/Socials. */
  const customMainMenu = createElement(
    MainMenu,
    null,
    createElement(MainMenu.DefaultItems.ToggleTheme),
    createElement(MainMenu.DefaultItems.ChangeCanvasBackground)
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
      children: customMainMenu,
    })
  )
}
