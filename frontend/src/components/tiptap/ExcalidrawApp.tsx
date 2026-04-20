import { Excalidraw, MainMenu, restore, serializeAsJSON } from '@excalidraw/excalidraw'
import '@excalidraw/excalidraw/index.css'
import type { ExcalidrawImperativeAPI } from '@excalidraw/excalidraw/types'
import { createElement, useCallback, useMemo, useRef } from 'react'

/** ЛКМ = панорама (как «рука» на excalidraw.com), а не рамка выделения. */
const DEFAULT_ACTIVE_TOOL = {
  type: 'hand' as const,
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

export function ExcalidrawApp({ sceneJson, readOnly, sceneKey, onSceneDebounced }: ExcalidrawAppProps) {
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const apiRef = useRef<ExcalidrawImperativeAPI | null>(null)

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
  }, [])

  const stopUndoBubbleToEditor = useCallback((e: React.KeyboardEvent) => {
    const mod = e.ctrlKey || e.metaKey
    if (!mod) return
    const k = e.key.toLowerCase()
    if (k === 'z' || k === 'y') {
      e.stopPropagation()
    }
  }, [])

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
      'data-excalidraw-root': '',
      style: { height: '100%', width: '100%' },
      onKeyDown: stopUndoBubbleToEditor,
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
