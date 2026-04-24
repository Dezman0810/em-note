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

function buildExcalidrawClipboardString(
  api: ExcalidrawImperativeAPI,
  elements: ExcalidrawElement[]
): string {
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
  return JSON.stringify({
    type: 'excalidraw/clipboard',
    elements: JSON.parse(JSON.stringify(elements)) as unknown[],
    files: filesOut,
  })
}

/**
 * Запасной путь без navigator.clipboard (http, старые WebView, часть планшетов).
 * Должен вызываться в том же «жесте пользователя», что и клик по кнопке.
 */
function copyTextViaExecCommand(text: string): boolean {
  if (typeof document === 'undefined') return false
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.cssText = 'position:fixed;left:-9999px;top:0;width:1px;height:1px;opacity:0;'
    document.body.appendChild(ta)
    ta.focus()
    ta.select()
    ta.setSelectionRange(0, text.length)
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}

/**
 * Запись в буфер: сначала Clipboard API, при ошибке — execCommand.
 * На iOS важно не ставить await до writeText, иначе теряется user activation.
 */
function writeClipboardPayload(
  api: ExcalidrawImperativeAPI,
  clip: string,
  onSuccess: () => void,
  what: 'copy' | 'cut'
): void {
  const fail = () => {
    const hint =
      location.protocol === 'http:' && location.hostname !== 'localhost'
        ? ' Откройте сайт по https:// (не http://).'
        : ''
    api.setToast?.({
      message:
        (what === 'cut' ? 'Не удалось вырезать в буфер' : 'Не удалось скопировать в буфер') +
        '.' +
        hint,
      duration: 5500,
    })
  }

  if (navigator.clipboard?.writeText) {
    void navigator.clipboard.writeText(clip).then(onSuccess, () => {
      if (copyTextViaExecCommand(clip)) onSuccess()
      else fail()
    })
    return
  }
  if (copyTextViaExecCommand(clip)) onSuccess()
  else fail()
}

export async function excalidrawBarCopy(api: ExcalidrawImperativeAPI, pasteRoot: HTMLDivElement): Promise<void> {
  focusInner(pasteRoot)
  const selected = getSelectedElementsForBar(api)
  if (selected.length === 0) return
  const clip = buildExcalidrawClipboardString(api, selected)
  writeClipboardPayload(api, clip, () => {}, 'copy')
}

export async function excalidrawBarCut(api: ExcalidrawImperativeAPI, pasteRoot: HTMLDivElement): Promise<void> {
  focusInner(pasteRoot)
  const selected = getSelectedElementsForBar(api)
  if (selected.length === 0) return
  const clip = buildExcalidrawClipboardString(api, selected)
  const toRemove = new Set(selected.map((e) => e.id))
  const applyCut = () => {
    const cur = api.getSceneElements()
    const next = cur.map((el) => (toRemove.has(el.id) ? newElementWith(el, { isDeleted: true }) : el))
    api.updateScene({
      elements: next,
      appState: { selectedElementIds: {} },
      captureUpdate: CaptureUpdateAction.IMMEDIATELY,
    })
  }
  writeClipboardPayload(api, clip, applyCut, 'cut')
}

export async function excalidrawBarPaste(api: ExcalidrawImperativeAPI, pasteRoot: HTMLDivElement): Promise<void> {
  focusInner(pasteRoot)
  const finish = (text: string) => {
    const t = text?.trim() ?? ''
    if (!t || !excalidrawClipboardPayloadLooksLikeJson(t)) {
      api.setToast?.({
        message: 'В буфере нет данных схемы — сначала «Копировать» в этой же заметке',
        duration: 5000,
      })
      return
    }
    const client = excalidrawGetLastPointerClientCoords()
    applyExcalidrawClipboardJson(api, t, client)
  }

  if (!navigator.clipboard?.readText) {
    api.setToast?.({
      message:
        'Вставка из кнопки недоступна в этом браузере. Нажмите на холст и используйте вставку с клавиатуры (или меню «Вставить»).',
      duration: 6000,
    })
    return
  }

  try {
    const text = await navigator.clipboard.readText()
    finish(text)
  } catch {
    api.setToast?.({
      message:
        'Не удалось прочитать буфер. Разрешите доступ к буферу обмена для сайта или вставьте через клавиатуру по холсту.',
      duration: 6000,
    })
  }
}
