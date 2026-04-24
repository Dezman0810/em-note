import { CaptureUpdateAction, newElementWith } from '@excalidraw/excalidraw'
import type { ExcalidrawImperativeAPI } from '@excalidraw/excalidraw/types'
import type { ExcalidrawElement } from '@excalidraw/excalidraw/element/types'
import { applyExcalidrawClipboardJson, excalidrawClipboardPayloadLooksLikeJson } from './excalidrawClipboardApply'
import { excalidrawGetLastPointerClientCoords } from './excalidrawPointerBridge'

function focusInner(pasteRoot: HTMLDivElement) {
  pasteRoot.querySelector<HTMLElement>('.excalidraw.excalidraw-container')?.focus({ preventScroll: true })
}

/** Выделенные элементы + привязанный текст у фигур (без отдельного импорта scene из пакета). */
function getSelectedElementsForBar(api: ExcalidrawImperativeAPI): ExcalidrawElement[] {
  const appState = api.getAppState()
  const sel = appState.selectedElementIds
  const selectedIds = new Set(Object.keys(sel).filter((k) => sel[k]))
  const elements = api.getSceneElements()
  const out: ExcalidrawElement[] = []
  for (const el of elements) {
    if (el.isDeleted) continue
    if (selectedIds.has(el.id)) out.push(el)
  }
  for (const el of elements) {
    if (el.isDeleted) continue
    if (el.type !== 'text') continue
    const cid = 'containerId' in el && typeof el.containerId === 'string' ? el.containerId : null
    if (cid && selectedIds.has(cid) && !selectedIds.has(el.id)) out.push(el)
  }
  return out
}

async function writeExcalidrawClipboard(api: ExcalidrawImperativeAPI, elements: ExcalidrawElement[]): Promise<void> {
  const files = api.getFiles()
  const fileIds = new Set<string>()
  for (const el of elements) {
    if (el.type === 'image' && 'fileId' in el && el.fileId) fileIds.add(String(el.fileId))
  }
  const filesOut: Record<string, unknown> = {}
  for (const id of fileIds) {
    const f = files[id]
    if (f) filesOut[id] = f
  }
  const clip = JSON.stringify({
    type: 'excalidraw/clipboard',
    elements: JSON.parse(JSON.stringify(elements)) as unknown[],
    files: filesOut,
  })
  if (!navigator.clipboard?.writeText) {
    throw new Error('Clipboard API недоступен')
  }
  await navigator.clipboard.writeText(clip)
}

export async function excalidrawBarCopy(api: ExcalidrawImperativeAPI, pasteRoot: HTMLDivElement): Promise<void> {
  focusInner(pasteRoot)
  const selected = getSelectedElementsForBar(api)
  if (selected.length === 0) return
  if (!window.isSecureContext) {
    api.setToast?.({ message: 'Копирование нужен HTTPS или localhost', duration: 4000 })
    return
  }
  await writeExcalidrawClipboard(api, selected)
}

export async function excalidrawBarCut(api: ExcalidrawImperativeAPI, pasteRoot: HTMLDivElement): Promise<void> {
  focusInner(pasteRoot)
  const selected = getSelectedElementsForBar(api)
  if (selected.length === 0) return
  if (!window.isSecureContext) {
    api.setToast?.({ message: 'Вырезание нужен HTTPS или localhost', duration: 4000 })
    return
  }
  await writeExcalidrawClipboard(api, selected)
  const toRemove = new Set(selected.map((e) => e.id))
  const cur = api.getSceneElements()
  const next = cur.map((el) => (toRemove.has(el.id) ? newElementWith(el, { isDeleted: true }) : el))
  api.updateScene({
    elements: next,
    appState: { selectedElementIds: {} },
    captureUpdate: CaptureUpdateAction.IMMEDIATELY,
  })
}

export async function excalidrawBarPaste(api: ExcalidrawImperativeAPI, pasteRoot: HTMLDivElement): Promise<void> {
  focusInner(pasteRoot)
  if (!window.isSecureContext || !navigator.clipboard?.readText) {
    api.setToast?.({ message: 'Вставка нужен HTTPS или localhost', duration: 4000 })
    return
  }
  let text: string
  try {
    text = await navigator.clipboard.readText()
  } catch {
    api.setToast?.({ message: 'Не удалось прочитать буфер обмена', duration: 4000 })
    return
  }
  if (!text || !excalidrawClipboardPayloadLooksLikeJson(text)) {
    api.setToast?.({
      message: 'В буфере нет данных схемы — сначала «Копировать» в этой же заметке',
      duration: 5000,
    })
    return
  }
  const client = excalidrawGetLastPointerClientCoords()
  applyExcalidrawClipboardJson(api, text, client)
}
