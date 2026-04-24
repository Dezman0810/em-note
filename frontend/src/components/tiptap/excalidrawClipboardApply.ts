import {
  CaptureUpdateAction,
  convertToExcalidrawElements,
  getCommonBounds,
  newElementWith,
  restore,
  viewportCoordsToSceneCoords,
} from '@excalidraw/excalidraw'
import type { ExcalidrawImperativeAPI } from '@excalidraw/excalidraw/types'
import type { ExcalidrawElement } from '@excalidraw/excalidraw/element/types'

export function excalidrawClipboardPayloadLooksLikeJson(s: string): boolean {
  return s.includes('excalidraw/clipboard') || s.includes('excalidraw-api/clipboard')
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

/** Вставка JSON из буфера (тот же формат, что и при Ctrl+V). */
export function applyExcalidrawClipboardJson(
  api: ExcalidrawImperativeAPI,
  text: string,
  pasteClient: { clientX: number; clientY: number } | null
): void {
  const trimmed = text.trim()
  if (!excalidrawClipboardPayloadLooksLikeJson(trimmed)) return
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
    const targetScene = pasteClient
      ? scenePointAtClient(api, pasteClient.clientX, pasteClient.clientY)
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
    console.error('Excalidraw clipboard apply failed', err)
  }
}
