import {
  CaptureUpdateAction,
  bumpVersion,
  getCommonBounds,
  mutateElement,
  newElementWith,
  restoreElements,
  viewportCoordsToSceneCoords,
} from '@excalidraw/excalidraw'
import type { ExcalidrawElement } from '@excalidraw/excalidraw/element/types'
import type { BinaryFiles, ExcalidrawImperativeAPI } from '@excalidraw/excalidraw/types'
import { generateNKeysBetween } from 'fractional-indexing'

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

function effectiveGridSize(api: ExcalidrawImperativeAPI): number | null {
  const app = api.getAppState()
  return app.gridModeEnabled ? app.gridSize : null
}

function getGridPoint(x: number, y: number, gridSize: number | null): [number, number] {
  if (gridSize) {
    return [Math.round(x / gridSize) * gridSize, Math.round(y / gridSize) * gridSize]
  }
  return [x, y]
}

function regenerateId(): string {
  return crypto.randomUUID().replace(/-/g, '')
}

function randomInteger(): number {
  return Math.floor(Math.random() * 2 ** 31)
}

/** Как duplicateElements в Excalidraw — новые id, containerId и bindings внутри набора. */
function duplicateClipboardElements(
  elements: readonly ExcalidrawElement[],
  opts?: { randomizeSeed?: boolean }
): ExcalidrawElement[] {
  const clonedElements: ExcalidrawElement[] = []
  const origElementsMap = new Map(elements.map((el) => [el.id, el]))
  const elementNewIdsMap = new Map<string, string>()
  const groupNewIdsMap = new Map<string, string>()

  const maybeGetNewId = (id: string): string | null => {
    if (elementNewIdsMap.has(id)) return elementNewIdsMap.get(id)!
    if (origElementsMap.has(id)) {
      const newId = regenerateId()
      elementNewIdsMap.set(id, newId)
      return newId
    }
    return null
  }

  for (const element of elements) {
    type MutableClone = ExcalidrawElement & {
      id: string
      seed: number
      groupIds: string[]
      containerId?: string | null
      boundElements?: { id: string; type: string }[] | null
      endBinding?: { elementId: string } | null
      startBinding?: { elementId: string } | null
      frameId?: string | null
    }
    const clonedElement = JSON.parse(JSON.stringify(element)) as MutableClone
    clonedElement.id = maybeGetNewId(element.id)!
    if (opts?.randomizeSeed) {
      clonedElement.seed = randomInteger()
      bumpVersion(clonedElement)
    }

    if (clonedElement.groupIds?.length) {
      clonedElement.groupIds = clonedElement.groupIds.map((groupId) => {
        if (!groupNewIdsMap.has(groupId)) groupNewIdsMap.set(groupId, regenerateId())
        return groupNewIdsMap.get(groupId)!
      })
    }

    if ('containerId' in clonedElement && clonedElement.containerId) {
      clonedElement.containerId = maybeGetNewId(clonedElement.containerId)
    }

    if ('boundElements' in clonedElement && clonedElement.boundElements) {
      const nextBindings: { id: string; type: string }[] = []
      for (const binding of clonedElement.boundElements) {
        const newBindingId = maybeGetNewId(binding.id)
        if (newBindingId) nextBindings.push({ ...binding, id: newBindingId })
      }
      clonedElement.boundElements = nextBindings
    }

    if ('endBinding' in clonedElement && clonedElement.endBinding) {
      const newEndBindingId = maybeGetNewId(clonedElement.endBinding.elementId)
      clonedElement.endBinding = newEndBindingId
        ? { ...clonedElement.endBinding, elementId: newEndBindingId }
        : null
    }

    if ('startBinding' in clonedElement && clonedElement.startBinding) {
      const newStartBindingId = maybeGetNewId(clonedElement.startBinding.elementId)
      clonedElement.startBinding = newStartBindingId
        ? { ...clonedElement.startBinding, elementId: newStartBindingId }
        : null
    }

    if (clonedElement.frameId) {
      clonedElement.frameId = maybeGetNewId(clonedElement.frameId)
    }

    clonedElements.push(clonedElement)
  }

  return clonedElements
}

function assignFractionalIndicesForAppended(
  prevElements: readonly ExcalidrawElement[],
  newElements: ExcalidrawElement[]
): void {
  const lastIndex = prevElements.length > 0 ? prevElements[prevElements.length - 1].index : null
  const indices = generateNKeysBetween(lastIndex ?? null, null, newElements.length)
  for (let i = 0; i < newElements.length; i++) {
    mutateElement(newElements[i], { index: indices[i] as ExcalidrawElement['index'] }, false)
  }
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
    const elements = restoreElements(raw.elements as never, null)
    if (elements.length === 0) return

    const [minX, minY, maxX, maxY] = getCommonBounds(elements)
    const halfWidth = (maxX - minX) / 2
    const halfHeight = (maxY - minY) / 2

    const app = api.getAppState()
    const targetClient = pasteClient
      ? pasteClient
      : {
          clientX: app.offsetLeft + app.width / 2,
          clientY: app.offsetTop + app.height / 2,
        }
    const targetScene = scenePointAtClient(api, targetClient.clientX, targetClient.clientY)
    const dx = targetScene.x - halfWidth
    const dy = targetScene.y - halfHeight
    const [gridX, gridY] = getGridPoint(dx, dy, effectiveGridSize(api))

    const newElements = duplicateClipboardElements(
      elements.map((element) =>
        newElementWith(element, {
          x: element.x + gridX - minX,
          y: element.y + gridY - minY,
        })
      ),
      { randomizeSeed: true }
    )
    if (newElements.length === 0) return

    const prevElements = api.getSceneElementsIncludingDeleted()
    assignFractionalIndicesForAppended(prevElements, newElements)
    const nextElements = [...prevElements, ...newElements]

    const selectedElementIds: Record<string, true> = {}
    for (const el of newElements) {
      if (el.isDeleted) continue
      const bound =
        el.type === 'text' &&
        'containerId' in el &&
        typeof el.containerId === 'string' &&
        el.containerId
      if (!bound) selectedElementIds[el.id] = true
    }

    api.updateScene({
      elements: nextElements,
      appState: { selectedElementIds },
      captureUpdate: CaptureUpdateAction.IMMEDIATELY,
    })

    const files =
      raw.files && typeof raw.files === 'object' ? (raw.files as BinaryFiles) : null
    if (files && Object.keys(files).length > 0) {
      api.addFiles(Object.values(files))
    }
  } catch (err) {
    console.error('Excalidraw clipboard apply failed', err)
  }
}
