<script setup lang="ts">
import Color from '@tiptap/extension-color'
import Highlight from '@tiptap/extension-highlight'
import { ResizableImage } from './tiptap/ResizableImageExtension'
import { TableKit } from '@tiptap/extension-table'
import { NoteTableCell, NoteTableHeader } from './tiptap/noteTableSizingCells'
import {
  TABLE_COL_WIDTH_MAX,
  TABLE_COL_WIDTH_MIN,
  getNoteTableCellMetrics,
  getNoteTableCellMetricsAt,
} from './tiptap/noteTableMenuMetrics'
import TaskList from '@tiptap/extension-task-list'
import { wrapSelectedLinesAsList } from './tiptap/wrapSelectedLinesAsList'
import { EncryptedInline } from './tiptap/EncryptedInlineExtension'
import { AudioNoteBlock } from './tiptap/AudioNoteExtension'
import { CodeSnippetBlock } from './tiptap/CodeSnippetExtension'
import { ExcalidrawBlock } from './tiptap/ExcalidrawExtension'
import { MindmapBlock } from './tiptap/MindmapExtension'
import { C4Block } from './tiptap/C4Extension'
import { ExcalidrawUndoGuard } from './tiptap/ExcalidrawUndoGuard'
import { RichClipboardPasteFix } from './tiptap/RichClipboardPasteFix'
import { TableColumnFilter } from './tiptap/TableColumnFilterExtension'
import TableColumnFilterOverlay from './tiptap/TableColumnFilterOverlay.vue'
import { NoteTable } from './tiptap/noteTableFilterTable'
import {
  findTableAtState,
  isTableFilterEnabled,
  setTableFilterEnabled,
} from './tiptap/noteTableFilterCommands'
import { refreshTableFilterDecorations } from './tiptap/tableFilterSession'
import { cleanupLegacyTableFilterStyles } from './tiptap/tableFilterDomSync'
import { TaskItemNote } from './tiptap/taskItemNote'
import { TaskListEnterKeymap } from './tiptap/taskListEnterKeymap'
import { FontFamily, TextStyle } from '@tiptap/extension-text-style'
import StarterKit from '@tiptap/starter-kit'
import type { Editor } from '@tiptap/core'
import type { EditorState, Transaction } from '@tiptap/pm/state'
import { TableMap } from '@tiptap/pm/tables'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import { computed, nextTick, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import { attachmentsApi, errMessage, grammarApi, publicNoteApi } from '../api/client'
import type { GrammarAdvice, GrammarCheckResult } from '../api/types'
import { useNoteLayout } from '../composables/useNoteLayout'
import { useAuthStore } from '../stores/auth'
import { encryptText, HTTPS_REQUIRED_MSG, isSecureBrowserContext } from '../utils/cryptoSecret'
import { normalizePastedRichCodeHtml } from '../utils/normalizePastedRichCodeHtml'
import { registerAttachmentBlobResolver } from '../utils/attachmentBlob'
import { applyTextKeepingMarks } from '../utils/grammarMarks'
import { rewriteAttachmentImagesInTipTapDoc } from '../utils/tiptapContent'
import { UploadedFileBlock } from './tiptap/UploadedFileExtension'
import {
  excalidrawInnerHasFocusedTextField,
  resolveExcalidrawInnerForCutCopy,
  resolveExcalidrawInnerForUndoRedo,
} from './tiptap/excalidrawPointerBridge'

/** Цвет букв (круги + первая палитра). */
const TEXT_COLOR_PRESETS = [
  '#b91c1c',
  '#ea580c',
  '#ca8a04',
  '#16a34a',
  '#2563eb',
  '#9333ea',
] as const

/** Заливка вокруг текста (марк highlight), не цвет букв. */
const HIGHLIGHT_FILL_PRESETS = [
  '#fef08a',
  '#fde68a',
  '#bbf7d0',
  '#a5f3fc',
  '#fecdd3',
  '#e9d5ff',
  '#fed7aa',
  '#f5f5f4',
  '#d9f99d',
  '#fce7f3',
] as const

const props = withDefaults(
  defineProps<{
    contentJson: string
    editable?: boolean
    /** Нужен для загрузки вложений (после первого сохранения заметки). */
    noteId?: string | null
    /** Публичная ссылка: загрузка/скачивание через /api/public/... */
    publicToken?: string | null
  }>(),
  { editable: true, noteId: null, publicToken: null }
)
const emit = defineEmits<{ (e: 'update:contentJson', value: string): void }>()

/** Контекст для NodeView вложений (публичная ссылка vs своя заметка). */
const noteAttachmentContext = computed(() => ({
  publicToken: props.publicToken?.trim() || null,
}))
provide('noteAttachmentContext', noteAttachmentContext)

const toolbarTick = ref(0)
const editorContentHostRef = ref<HTMLElement | null>(null)

const MAX_AUDIO_BYTES = 12 * 1024 * 1024
/** Битрейт Opus/WebM: баланс качества и размера (~1 МБ на 1–1.5 мин речи). */
const AUDIO_RECORD_BITS_PER_SECOND = 96_000

const fileInputRef = ref<HTMLInputElement | null>(null)
const fileUploadErr = ref('')

watch(
  () => [props.noteId, props.publicToken] as const,
  () => {
    const tok = props.publicToken?.trim()
    if (tok) {
      registerAttachmentBlobResolver((id) => publicNoteApi.downloadAttachmentBlob(tok, id))
    } else if (props.noteId) {
      registerAttachmentBlobResolver((id) => attachmentsApi.downloadBlob(id))
    } else {
      registerAttachmentBlobResolver(null)
    }
  },
  { immediate: true }
)

const recording = ref(false)
const recordErr = ref('')
let mediaRecorder: MediaRecorder | null = null
let recordStream: MediaStream | null = null
const recordChunks: BlobPart[] = []

const encryptDlg = ref(false)
const encryptPass = ref('')
const encryptErr = ref('')
const encryptHint = ref('')
let encryptRangeFrom = 0
let encryptRangeTo = 0
let encryptPlain = ''

const auth = useAuthStore()
const { innerScroll } = useNoteLayout()
const GRAMMAR_MAX_CHARS = 8000
const grammarDlg = ref(false)
const grammarBusy = ref(false)
const grammarErr = ref('')
const grammarHint = ref('')
const grammarOriginal = ref('')
const grammarDraft = ref('')
const grammarDraftDirty = ref(false)
const grammarResult = ref<GrammarCheckResult | null>(null)
const grammarChosen = ref('')
let grammarFrom = 0
let grammarTo = 0

/**
 * Что мы сами только что отдали наружу. Родитель кладёт это значение обратно в проп,
 * и без сравнения по строке каждое нажатие клавиши приводило к лишнему разбору
 * документа и двум `JSON.stringify` в watch ниже.
 */
let lastEmittedContentJson = ''
let applyingExternal = false

/**
 * Панель инструментов перерисовывается по счётчику транзакций. За одно нажатие
 * их бывает несколько, поэтому склеиваем их в один кадр.
 */
let toolbarTickScheduled = false
function bumpToolbar() {
  if (toolbarTickScheduled) return
  toolbarTickScheduled = true
  requestAnimationFrame(() => {
    toolbarTickScheduled = false
    toolbarTick.value++
  })
}

function parseDoc(raw: string) {
  try {
    const j = JSON.parse(raw || '{}')
    const base = j && typeof j === 'object' ? j : {}
    return rewriteAttachmentImagesInTipTapDoc(base) as Record<string, unknown>
  } catch {
    return {}
  }
}

const editor = useEditor({
  editable: props.editable,
  editorProps: {
    /** SSMS и др. дают `<font>` / смесь тегов; TipTap понимает `span[style]`. */
    transformPastedHTML(html) {
      return normalizePastedRichCodeHtml(html)
    },
    handleDOMEvents: {
      /** Пока фокус внутри Excalidraw — не отдаём клавиши TipTap (в т.ч. после capture-фокуса перед Ctrl+C/V). */
      keydown(_view, event) {
        if (document.activeElement?.closest('[data-excalidraw-root]')) return true
        const t = event.target
        if (t instanceof Element && t.closest('[data-excalidraw-root]')) return true
        /* Ctrl+Z/Y над схемой, но фокус ещё в тексте заметки — отдаём undo/redo в Excalidraw. */
        if (event.isTrusted && (event.ctrlKey || event.metaKey)) {
          const k = event.key.toLowerCase()
          const undo = k === 'z' && !event.shiftKey
          const redo = k === 'y' || (k === 'z' && event.shiftKey)
          const cutOrCopy = k === 'x' || k === 'c'
          if (undo || redo) {
            const inner = resolveExcalidrawInnerForUndoRedo()
            if (inner) {
              if (excalidrawInnerHasFocusedTextField(inner)) return false
              if (inner.contains(document.activeElement)) return true
              event.preventDefault()
              inner.focus({ preventScroll: true })
              queueMicrotask(() => {
                inner.dispatchEvent(
                  new KeyboardEvent('keydown', {
                    key: event.key,
                    code: event.code,
                    ctrlKey: event.ctrlKey,
                    metaKey: event.metaKey,
                    shiftKey: event.shiftKey,
                    bubbles: true,
                    cancelable: true,
                  })
                )
              })
              return true
            }
          }
          if (cutOrCopy) {
            const inner = resolveExcalidrawInnerForCutCopy()
            if (inner) {
              if (excalidrawInnerHasFocusedTextField(inner)) return false
              if (inner.contains(document.activeElement)) return true
              event.preventDefault()
              inner.focus({ preventScroll: true })
              queueMicrotask(() => {
                inner.dispatchEvent(
                  new KeyboardEvent('keydown', {
                    key: event.key,
                    code: event.code,
                    ctrlKey: event.ctrlKey,
                    metaKey: event.metaKey,
                    shiftKey: event.shiftKey,
                    bubbles: true,
                    cancelable: true,
                  })
                )
              })
              return true
            }
          }
        }
        return false
      },
    },
  },
  extensions: [
    ExcalidrawUndoGuard,
    RichClipboardPasteFix,
    TableColumnFilter,
    StarterKit.configure({
      heading: { levels: [2, 3] },
    }),
    TableKit.configure({
      table: false,
      tableCell: false,
      tableHeader: false,
    }),
    NoteTable.configure({
      resizable: true,
      /** Совпадает с TABLE_COL_WIDTH_MIN — иначе узкие colwidth поджимаются при отрисовке. */
      cellMinWidth: 20,
      handleWidth: 6,
      lastColumnResizable: true,
    }),
    NoteTableCell,
    NoteTableHeader,
    TaskList,
    TaskItemNote.configure({ nested: false }),
    TaskListEnterKeymap,
    TextStyle,
    FontFamily.configure({ types: ['textStyle'] }),
    Color,
    Highlight.configure({ multicolor: true }),
    ResizableImage.configure({ inline: false, allowBase64: true }),
    EncryptedInline,
    ExcalidrawBlock,
    MindmapBlock,
    C4Block,
    CodeSnippetBlock,
    AudioNoteBlock,
    UploadedFileBlock,
  ],
  content: parseDoc(props.contentJson),
  onUpdate: ({ editor: ed }) => {
    if (applyingExternal) return
    lastEmittedContentJson = JSON.stringify(ed.getJSON())
    emit('update:contentJson', lastEmittedContentJson)
  },
  onSelectionUpdate: () => {
    bumpToolbar()
  },
  onTransaction: () => {
    bumpToolbar()
  },
})

watch(
  () => props.editable,
  (v) => {
    editor.value?.setEditable(!!v)
    if (!v && recording.value) {
      try {
        mediaRecorder?.stop()
      } catch {
        /* */
      }
      recording.value = false
      cleanupRecordStream()
    }
  }
)

/**
 * Какой заметке сейчас принадлежит документ в TipTap.
 * Нужен отдельно от lastEmitted: после смены заметки строка JSON может
 * совпасть с тем, что мы когда-то эмитили (вернулиcь к A), а на экране ещё B.
 */
let appliedNoteId: string | null | undefined = props.noteId

function applyExternalContent(raw: string, force: boolean) {
  const ed = editor.value
  if (!ed || ed.isDestroyed || applyingExternal) return
  if (!force && raw === lastEmittedContentJson) return
  const next = parseDoc(raw)
  if (!force && JSON.stringify(ed.getJSON()) === JSON.stringify(next)) {
    lastEmittedContentJson = raw
    return
  }
  applyingExternal = true
  try {
    ed.commands.setContent(next, { emitUpdate: false })
    lastEmittedContentJson = raw
  } finally {
    applyingExternal = false
  }
}

watch(
  () => [props.contentJson, props.noteId] as const,
  ([v, noteId]) => {
    const noteChanged = noteId !== appliedNoteId
    appliedNoteId = noteId
    applyExternalContent(v, noteChanged)
  }
)

/** Цвета на кнопках панели: только из палитры / быстрого выбора, не от выделения в тексте. */
const DEFAULT_TOOLBAR_TEXT_COLOR = '#1e293b'
const DEFAULT_TOOLBAR_HIGHLIGHT_COLOR = '#fef08a'
const toolbarTextColor = ref(DEFAULT_TOOLBAR_TEXT_COLOR)
const toolbarHighlightColor = ref(DEFAULT_TOOLBAR_HIGHLIGHT_COLOR)

function normalizeToolbarHex(hex: string, fallback: string): string {
  const s = hex.trim()
  return /^#[0-9A-Fa-f]{6}$/i.test(s) ? s.toLowerCase() : fallback
}

const taskListOn = computed(() => {
  void toolbarTick.value
  return editor.value?.isActive('taskList') ?? false
})
const bulletListOn = computed(() => {
  void toolbarTick.value
  return editor.value?.isActive('bulletList') ?? false
})
const orderedListOn = computed(() => {
  void toolbarTick.value
  return editor.value?.isActive('orderedList') ?? false
})

const tableDd = ref<HTMLDetailsElement | null>(null)

const TABLE_INSERT_COLS_MIN = 1
const TABLE_INSERT_COLS_MAX = 30
const TABLE_INSERT_ROWS_MIN = 1
const TABLE_INSERT_ROWS_MAX = 100
const tableCustomCols = ref(4)
const tableCustomRows = ref(4)
const tableCustomErr = ref('')

/** Якорь ячейки: сохраняем на pointerdown по summary (до ухода фокуса с редактора). */
const tableMenuSavedAnchor = ref<number | null>(null)

function onTableSummaryPointerDown() {
  const dd = tableDd.value
  const ed = editor.value
  if (!dd || !ed) return
  /* Сохраняем якорь при любом открытии меню, пока details ещё закрыт (фокус часто ещё в редакторе). */
  if (!dd.open) {
    tableMenuSavedAnchor.value = ed.state.selection.anchor
  }
}

watch(
  () => tableDd.value?.open,
  (open) => {
    if (!open) {
      tableMenuSavedAnchor.value = null
      return
    }
    const ed = editor.value
    if (tableMenuSavedAnchor.value == null && ed?.isActive('table')) {
      tableMenuSavedAnchor.value = ed.state.selection.anchor
    }
  }
)

const tableMenuInTable = computed(() => {
  void toolbarTick.value
  return editor.value?.isActive('table') ?? false
})

/** Панель строк/столбцов даже если после открытия меню isActive('table') на мгновение false. */
const showTableRowColPanel = computed(() => {
  void toolbarTick.value
  void tableMenuSavedAnchor.value
  if (editor.value?.isActive('table')) return true
  if (tableDd.value?.open && tableMenuSavedAnchor.value != null) return true
  return false
})

const canTableAddRowBefore = computed(() => {
  void toolbarTick.value
  return editor.value?.can().addRowBefore() ?? false
})
const canTableAddRowAfter = computed(() => {
  void toolbarTick.value
  return editor.value?.can().addRowAfter() ?? false
})
const canTableDeleteRow = computed(() => {
  void toolbarTick.value
  return editor.value?.can().deleteRow() ?? false
})
const canTableAddColBefore = computed(() => {
  void toolbarTick.value
  return editor.value?.can().addColumnBefore() ?? false
})
const canTableAddColAfter = computed(() => {
  void toolbarTick.value
  return editor.value?.can().addColumnAfter() ?? false
})
const canTableDeleteCol = computed(() => {
  void toolbarTick.value
  return editor.value?.can().deleteColumn() ?? false
})
const canTableDeleteTable = computed(() => {
  void toolbarTick.value
  return editor.value?.can().deleteTable() ?? false
})
const canTableToggleHeaderRow = computed(() => {
  void toolbarTick.value
  return editor.value?.can().toggleHeaderRow() ?? false
})

const tableColumnFilterEnabled = computed(() => {
  void toolbarTick.value
  void tableMenuSavedAnchor.value
  const ed = editor.value
  if (!ed) return false
  const anchor = tableMenuSavedAnchor.value ?? ed.state.selection.anchor
  const found = findTableAtState(ed.state, anchor)
  return found ? isTableFilterEnabled(found.tableNode) : false
})

function toggleTableColumnFiltering(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  const ed = editor.value
  if (!ed) return
  setTableFilterEnabled(ed, checked)
  refreshTableFilterDecorations(ed)
  bumpToolbar()
}

const tableCellMetrics = computed(() => {
  void toolbarTick.value
  void tableMenuSavedAnchor.value
  const ed = editor.value
  if (!ed?.isActive('table')) return null
  const open = tableDd.value?.open
  const anchor = tableMenuSavedAnchor.value
  if (open && anchor != null) {
    return getNoteTableCellMetricsAt(ed.state, anchor) ?? getNoteTableCellMetrics(ed.state)
  }
  return getNoteTableCellMetrics(ed.state)
})

const canTableApplySizing = computed(() => {
  void toolbarTick.value
  return showTableRowColPanel.value
})

const draftColW = ref('')

/** Фактическая ширина ячейки на экране (getBoundingClientRect), px. */
const measuredCellW = ref<number | null>(null)

function getSelectedTableCellElement(ed: Editor): HTMLElement | null {
  const { from } = ed.state.selection
  const root = ed.view.dom
  let n: Node | null = ed.view.domAtPos(from).node
  if (n.nodeType === Node.TEXT_NODE) n = n.parentElement
  let cur: Element | null = n as Element | null
  while (cur && root.contains(cur)) {
    if (cur instanceof HTMLElement && (cur.tagName === 'TD' || cur.tagName === 'TH')) return cur
    cur = cur.parentElement
  }
  return null
}

function refreshMeasuredCellSize() {
  measuredCellW.value = null
  const ed = editor.value
  if (!ed?.isActive('table')) return
  const cell = getSelectedTableCellElement(ed)
  if (!cell) return
  const r = cell.getBoundingClientRect()
  measuredCellW.value = Math.max(0, Math.round(r.width))
}

/** Первая допустимая позиция внутри ячейки для метрик / якоря. */
function posInsideTableCellForCommand(ed: Editor, pos: number): number {
  const max = ed.state.doc.content.size
  const p = Math.max(1, Math.min(pos, max))
  try {
    const $ = ed.state.doc.resolve(p)
    for (let d = $.depth; d >= 1; d--) {
      const n = $.node(d)
      if (n.type.name === 'tableCell' || n.type.name === 'tableHeader') {
        const inner = $.start(d) + 1
        return Math.min(Math.max(1, inner), max)
      }
    }
  } catch {
    /* */
  }
  return p
}

/** Позиция перед ячейкой для setNodeMarkup (без selectionCell из pm-tables). */
function findTableCellMarkupPosition(state: EditorState, hintPos: number): number | null {
  try {
    const max = state.doc.content.size
    const p = Math.max(1, Math.min(hintPos, max))
    const $ = state.doc.resolve(p)
    for (let d = $.depth; d >= 1; d--) {
      const node = $.node(d)
      const role = node.type.spec.tableRole
      if (role === 'cell' || role === 'header_cell') return $.before(d)
      if (node.type.name === 'tableCell' || node.type.name === 'tableHeader') return $.before(d)
    }
  } catch {
    /* */
  }
  return null
}

function colwidthZeroes(span: number) {
  return Array.from({ length: span }, () => 0)
}

/** Ширина столбца для всей колонки (как drag columnResizing / colgroup), иначе после первого раза раскладка ломается. */
function setColWidthOnTableColumnAtHint(
  tr: Transaction,
  state: EditorState,
  hintCellInsidePos: number,
  widthPx: number | null
): boolean {
  const cellBefore = findTableCellMarkupPosition(state, hintCellInsidePos)
  if (cellBefore == null) return false
  const $cell = state.doc.resolve(cellBefore)
  const nodeAfter = $cell.nodeAfter
  if (!nodeAfter || (nodeAfter.type.name !== 'tableCell' && nodeAfter.type.name !== 'tableHeader')) return false
  const table = $cell.node(-1)
  if (!table || table.type.spec.tableRole !== 'table') return false
  const start = $cell.start(-1)
  const map = TableMap.get(table)
  let col: number
  try {
    col = map.colCount($cell.pos - start) + nodeAfter.attrs.colspan - 1
  } catch {
    return false
  }
  let changed = false
  for (let row = 0; row < map.height; row++) {
    const mapIndex = row * map.width + col
    if (row > 0 && map.map[mapIndex] === map.map[mapIndex - map.width]) continue
    const rel = map.map[mapIndex]
    const cellNode = table.nodeAt(rel)
    if (!cellNode) continue
    const attrs = cellNode.attrs
    const span = Math.max(1, Number(attrs.colspan) || 1)
    const slot = attrs.colspan === 1 ? 0 : col - map.colCount(rel)
    let nextColwidth: number[] | null
    if (widthPx == null) {
      const cw = (attrs.colwidth as number[] | null) ?? null
      if (!cw) continue
      const colwidth = cw.slice()
      colwidth[slot] = 0
      nextColwidth = colwidth.every((x) => !x) ? null : colwidth
    } else {
      const w = widthPx
      const cw = (attrs.colwidth as number[] | null) ?? null
      if (cw && cw[slot] === w) continue
      const colwidth = cw ? cw.slice() : colwidthZeroes(span)
      colwidth[slot] = w
      nextColwidth = colwidth
    }
    tr.setNodeMarkup(start + rel, null, { ...attrs, colwidth: nextColwidth })
    changed = true
  }
  return changed
}

watch(
  () => [toolbarTick.value, tableMenuInTable.value, tableDd.value?.open] as const,
  async () => {
    if (!tableMenuInTable.value && !tableDd.value?.open) return
    const m = tableCellMetrics.value
    if (m) {
      draftColW.value = m.widthPx != null ? String(m.widthPx) : ''
    }
    await nextTick()
    refreshMeasuredCellSize()
  }
)

function clampDraftColW() {
  const raw = String(draftColW.value ?? '').trim()
  if (raw === '') return
  const n = parseInt(raw, 10)
  if (Number.isNaN(n)) return
  const c = Math.min(TABLE_COL_WIDTH_MAX, Math.max(TABLE_COL_WIDTH_MIN, Math.round(n)))
  draftColW.value = String(c)
}

function applyColWidthOnly() {
  const ed = editor.value
  if (!ed?.isEditable) return
  if (String(draftColW.value ?? '').trim() !== '') clampDraftColW()
  const wStr = String(draftColW.value ?? '').trim()
  const hintRaw = tableMenuSavedAnchor.value ?? ed.state.selection.anchor
  const hint = posInsideTableCellForCommand(ed, hintRaw)
  let widthPx: number | null = null
  if (wStr !== '') {
    const parsed = parseInt(wStr, 10)
    if (Number.isNaN(parsed)) return
    widthPx = Math.min(TABLE_COL_WIDTH_MAX, Math.max(TABLE_COL_WIDTH_MIN, Math.round(parsed)))
  }
  ed.view.focus()
  ed.chain()
    .command(({ tr, state }) => setColWidthOnTableColumnAtHint(tr, state, hint, widthPx))
    .run()
  closeTableDd()
  void nextTick(() => refreshMeasuredCellSize())
}

const boldOn = computed(() => {
  void toolbarTick.value
  return editor.value?.isActive('bold') ?? false
})

const textColorDd = ref<HTMLDetailsElement | null>(null)
const highlightDd = ref<HTMLDetailsElement | null>(null)

function pickTextColor(hex: string) {
  const n = normalizeToolbarHex(hex, toolbarTextColor.value)
  toolbarTextColor.value = n
  setTextColor(n)
  if (textColorDd.value) textColorDd.value.open = false
}

function clearTextColorFromMenu() {
  toolbarTextColor.value = DEFAULT_TOOLBAR_TEXT_COLOR
  unsetTextColor()
  if (textColorDd.value) textColorDd.value.open = false
}

function pickHighlightFill(hex: string) {
  const n = normalizeToolbarHex(hex, toolbarHighlightColor.value)
  toolbarHighlightColor.value = n
  setHighlightFill(n)
  if (highlightDd.value) highlightDd.value.open = false
}

function clearHighlightFromMenu() {
  toolbarHighlightColor.value = DEFAULT_TOOLBAR_HIGHLIGHT_COLOR
  unsetHighlightFill()
  if (highlightDd.value) highlightDd.value.open = false
}

function onToolbarTextColorPickInput(ev: Event) {
  const v = (ev.target as HTMLInputElement).value
  const n = normalizeToolbarHex(v, toolbarTextColor.value)
  toolbarTextColor.value = n
  setTextColor(n)
}

function onToolbarHighlightPickInput(ev: Event) {
  const v = (ev.target as HTMLInputElement).value
  const n = normalizeToolbarHex(v, toolbarHighlightColor.value)
  toolbarHighlightColor.value = n
  setHighlightFill(n)
}

function closeTextColorDd() {
  if (textColorDd.value) textColorDd.value.open = false
}

function closeHighlightDd() {
  if (highlightDd.value) highlightDd.value.open = false
}

/** Стрелка — открыть палитру; слева (иконка + полоска) — сразу применить цвет к выделению. */
function onTextColorSummaryClick(ev: MouseEvent) {
  const chev = (ev.currentTarget as HTMLElement).querySelector('.word-dd-chev-wrap')
  if (chev?.contains(ev.target as Node)) return
  ev.preventDefault()
  setTextColor(toolbarTextColor.value)
  closeTextColorDd()
}

function onHighlightSummaryClick(ev: MouseEvent) {
  const chev = (ev.currentTarget as HTMLElement).querySelector('.word-dd-chev-wrap')
  if (chev?.contains(ev.target as Node)) return
  ev.preventDefault()
  setHighlightFill(toolbarHighlightColor.value)
  closeHighlightDd()
}

/** Не давать клику по Ж/К/списку сбрасывать выделение в тексте (закреплённая панель лежит поверх). */
function onToolbarMouseDown(ev: MouseEvent) {
  const t = ev.target
  if (t instanceof HTMLElement && t.closest('input, textarea, select')) return
  ev.preventDefault()
}

function toggleLineList(kind: 'taskList' | 'bulletList' | 'orderedList') {
  const ed = editor.value
  if (!ed) return
  ed.chain()
    .focus()
    .command(({ state, tr }) => wrapSelectedLinesAsList(state, tr, kind))
    .run()
}

function isTextPresetActive(hex: string) {
  void toolbarTick.value
  const c = editor.value?.getAttributes('textStyle')?.color
  return typeof c === 'string' && c.toLowerCase() === hex.toLowerCase()
}

function isHighlightFillActive(hex: string) {
  void toolbarTick.value
  const c = editor.value?.getAttributes('highlight')?.color
  return typeof c === 'string' && c.toLowerCase() === hex.toLowerCase()
}

function setTextColor(hex: string) {
  editor.value?.chain().focus().setColor(hex).run()
}

function unsetTextColor() {
  editor.value?.chain().focus().unsetColor().run()
}

function setHighlightFill(hex: string) {
  editor.value?.chain().focus().setHighlight({ color: hex }).run()
}

function unsetHighlightFill() {
  editor.value?.chain().focus().unsetHighlight().run()
}

function insertExcalidraw() {
  editor.value?.chain().focus().insertExcalidraw().run()
}

function insertMindmap() {
  editor.value?.chain().focus().insertMindmap().run()
}

function insertC4() {
  editor.value?.chain().focus().insertC4().run()
}

function insertCodeSnippet() {
  editor.value?.chain().focus().insertCodeSnippet().run()
}

function closeTableDd() {
  if (tableDd.value) tableDd.value.open = false
}

function insertNoteTable(rows: number, cols: number, withHeaderRow: boolean) {
  editor.value
    ?.chain()
    .focus()
    .insertTable({ rows, cols, withHeaderRow })
    .run()
  closeTableDd()
}

function insertCustomNoteTable() {
  const cols = Math.round(Number(tableCustomCols.value))
  const rows = Math.round(Number(tableCustomRows.value))
  if (!Number.isFinite(cols) || cols < TABLE_INSERT_COLS_MIN || cols > TABLE_INSERT_COLS_MAX) {
    tableCustomErr.value = `Столбцов: от ${TABLE_INSERT_COLS_MIN} до ${TABLE_INSERT_COLS_MAX}`
    return
  }
  if (!Number.isFinite(rows) || rows < TABLE_INSERT_ROWS_MIN || rows > TABLE_INSERT_ROWS_MAX) {
    tableCustomErr.value = `Строк: от ${TABLE_INSERT_ROWS_MIN} до ${TABLE_INSERT_ROWS_MAX}`
    return
  }
  tableCustomErr.value = ''
  insertNoteTable(rows, cols, true)
}

function triggerFilePick() {
  fileUploadErr.value = ''
  fileInputRef.value?.click()
}

async function onFilePicked(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const ed = editor.value
  if (!ed || !props.editable) return
  if (!props.noteId) {
    fileUploadErr.value = 'Сначала сохраните заметку — без id файлы не прикрепить.'
    return
  }
  fileUploadErr.value = ''
  try {
    const tok = props.publicToken?.trim()
    const meta = tok
      ? await publicNoteApi.uploadAttachment(tok, file)
      : await attachmentsApi.upload(props.noteId, file)
    ed.chain()
      .focus()
      .insertUploadedFile({
        attachmentId: meta.id,
        filename: meta.original_filename,
        mimeType: meta.content_type,
        isImage: meta.is_image,
      })
      .run()
  } catch (e) {
    fileUploadErr.value = errMessage(e)
  }
}

function pickAudioMime(): string {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/ogg',
    'audio/mp4',
  ]
  for (const c of candidates) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(c)) return c
  }
  return ''
}

function recorderOptionsForMime(mime: string): MediaRecorderOptions {
  const o: MediaRecorderOptions = {}
  if (mime) o.mimeType = mime
  if (
    mime &&
    (mime.includes('opus') || mime.includes('webm') || mime.includes('ogg') || mime.includes('mp4'))
  ) {
    o.audioBitsPerSecond = AUDIO_RECORD_BITS_PER_SECOND
  }
  return o
}

function blobTypeFromChunks(chunks: BlobPart[]): string {
  for (const c of chunks) {
    if (c instanceof Blob && c.type) return c.type
  }
  return 'audio/webm'
}

function fileExtensionForRecordedAudio(mime: string): string {
  const m = mime.toLowerCase()
  if (m.includes('webm')) return 'webm'
  if (m.includes('ogg')) return 'ogg'
  if (m.includes('mp4') || m.includes('aac') || m.includes('m4a')) return 'm4a'
  return 'webm'
}

/** Имя файла: дата и время по Москве, сутки 0–23, время через точки (напр. 15.25.03). */
function moscowRecordingFileStamp(): string {
  const d = new Date()
  const fmt = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Moscow',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
  const parts = fmt.formatToParts(d)
  const pick = (type: Intl.DateTimeFormatPartTypes) =>
    (parts.find((p) => p.type === type)?.value ?? '').padStart(2, '0')
  const y = pick('year')
  const mo = pick('month')
  const day = pick('day')
  const h = pick('hour')
  const mi = pick('minute')
  const s = pick('second')
  return `${y}-${mo}-${day}.${h}.${mi}.${s}`
}

async function uploadRecordedAudioBlob(blob: Blob, mimeType: string) {
  const tok = props.publicToken?.trim()
  if (!tok && !props.noteId) {
    throw new Error('Сначала сохраните заметку — запись сохраняется как файл на сервере.')
  }
  const ext = fileExtensionForRecordedAudio(mimeType)
  const stamp = moscowRecordingFileStamp()
  const filename = `Запись-${stamp}.${ext}`
  const file = new File([blob], filename, { type: mimeType || 'audio/webm' })
  return tok ? publicNoteApi.uploadAttachment(tok, file) : attachmentsApi.upload(props.noteId!, file)
}

function cleanupRecordStream() {
  if (recordStream) {
    recordStream.getTracks().forEach((t) => t.stop())
    recordStream = null
  }
  mediaRecorder = null
  recordChunks.length = 0
}

async function startRecording() {
  const ed = editor.value
  if (!ed || !props.editable || recording.value) return
  recordErr.value = ''
  if (typeof window !== 'undefined' && !isSecureBrowserContext()) {
    recordErr.value =
      'Запись с микрофона доступна только по HTTPS или на localhost. В Chrome по http://IP микрофон отключён политикой безопасности.'
    return
  }
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
    recordErr.value = 'Запись недоступна в этом браузере.'
    return
  }
  try {
    try {
      recordStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          channelCount: 1,
        },
      })
    } catch {
      recordStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    }
    const mime = pickAudioMime()
    let opts = recorderOptionsForMime(mime)
    try {
      mediaRecorder = new MediaRecorder(recordStream, Object.keys(opts).length ? opts : undefined)
    } catch {
      opts = mime ? { mimeType: mime } : {}
      mediaRecorder = new MediaRecorder(recordStream, Object.keys(opts).length ? opts : undefined)
    }
    recordChunks.length = 0
    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) recordChunks.push(e.data)
    }
    mediaRecorder.onerror = () => {
      recordErr.value = 'Ошибка записи.'
      recording.value = false
      cleanupRecordStream()
    }
    mediaRecorder.onstop = () => {
      recording.value = false
      const mr = mediaRecorder
      const chunks = [...recordChunks]
      const mimeType = mr?.mimeType || blobTypeFromChunks(chunks)
      cleanupRecordStream()
      if (!mr || !ed) return
      const blob = new Blob(chunks, { type: mimeType })
      if (blob.size > MAX_AUDIO_BYTES) {
        recordErr.value = 'Файл слишком большой (макс. ~12 МБ). Запишите короче.'
        return
      }
      if (blob.size < 256) {
        recordErr.value = 'Запись слишком короткая.'
        return
      }
      void (async () => {
        try {
          const meta = await uploadRecordedAudioBlob(blob, blob.type || mimeType)
          const edNow = editor.value
          if (!edNow) return
          edNow
            .chain()
            .focus()
            .insertUploadedFile({
              attachmentId: meta.id,
              filename: meta.original_filename,
              mimeType: meta.content_type,
              isImage: false,
            })
            .run()
        } catch (e) {
          recordErr.value = errMessage(e)
        }
      })()
    }
    /* Без интервала — один фрагмент при stop, обычно лучше качество, чем мелкие чанки */
    mediaRecorder.start()
    recording.value = true
  } catch {
    recordErr.value = 'Нет доступа к микрофону. Разрешите запись в настройках браузера.'
    cleanupRecordStream()
    recording.value = false
  }
}

function stopRecording() {
  if (!recording.value || !mediaRecorder) return
  try {
    mediaRecorder.requestData()
    mediaRecorder.stop()
  } catch {
    recording.value = false
    cleanupRecordStream()
  }
}

function selectionInSingleTextblock(): boolean {
  const ed = editor.value
  if (!ed) return false
  const { empty, from, to } = ed.state.selection
  if (empty || from === to) return false
  const $from = ed.state.doc.resolve(from)
  const $to = ed.state.doc.resolve(to)
  return $from.parent === $to.parent && $from.parent.isTextblock
}

const canEncryptSelection = computed(() => {
  void toolbarTick.value
  const ed = editor.value
  if (!ed || !ed.isEditable) return false
  if (!selectionInSingleTextblock()) return false
  const { from, to, empty } = ed.state.selection
  if (empty) return false
  const t = ed.state.doc.textBetween(from, to, '\n').trim()
  return t.length > 0
})

function openEncryptDialog() {
  const ed = editor.value
  if (!ed) return
  const { from, to, empty } = ed.state.selection
  if (empty || !selectionInSingleTextblock()) {
    encryptHint.value =
      'Выделите текст в одном абзаце или заголовке (несколько абзацев за раз зашифровать нельзя).'
    window.setTimeout(() => {
      encryptHint.value = ''
    }, 4500)
    return
  }
  const text = ed.state.doc.textBetween(from, to, '\n')
  if (!text.trim()) return
  encryptRangeFrom = from
  encryptRangeTo = to
  encryptPlain = text
  encryptPass.value = ''
  encryptErr.value = ''
  encryptDlg.value = true
}

function closeEncryptDialog() {
  encryptDlg.value = false
  encryptPlain = ''
}

const canUseGrammar = computed(() => !!auth.user?.can_use_grammar && !!props.editable)

const grammarChosenSuggestion = computed(
  () => grammarResult.value?.suggestions.find((s) => s.id === grammarChosen.value) ?? null
)

const grammarLeftParts = computed(() => {
  const parts = grammarChosenSuggestion.value?.original_parts
  if (parts?.length) return parts
  return [{ text: grammarOriginal.value, kind: 'ok', message: '', before: '', after: '' }]
})

const grammarChanges = computed(() => grammarChosenSuggestion.value?.changes ?? [])
const grammarAdvice = computed(() => grammarResult.value?.advice ?? [])

const grammarCanApply = computed(() => {
  return grammarDraft.value !== grammarOriginal.value
})

function flashGrammarHint(msg: string) {
  grammarHint.value = msg
  window.setTimeout(() => {
    grammarHint.value = ''
  }, 4000)
}

function captureGrammarSelection(): boolean {
  const ed = editor.value
  if (!ed) {
    grammarFrom = 0
    grammarTo = 0
    grammarOriginal.value = ''
    return false
  }
  const { empty, from, to } = ed.state.selection
  if (empty || from === to) {
    grammarFrom = 0
    grammarTo = 0
    grammarOriginal.value = ''
    return false
  }
  const text = ed.state.doc.textBetween(from, to, '\n', '\n')
  if (!text.trim()) {
    grammarFrom = 0
    grammarTo = 0
    grammarOriginal.value = ''
    return false
  }
  if (text.length > GRAMMAR_MAX_CHARS) {
    flashGrammarHint(`Слишком длинный фрагмент. Выделите не больше ${GRAMMAR_MAX_CHARS} знаков.`)
    grammarFrom = 0
    grammarTo = 0
    grammarOriginal.value = ''
    return false
  }
  grammarFrom = from
  grammarTo = to
  grammarOriginal.value = text
  return true
}

function onGrammarMouseDown() {
  captureGrammarSelection()
}

function openGrammarDialog() {
  grammarErr.value = ''
  grammarResult.value = null
  grammarChosen.value = ''
  const captured = grammarFrom < grammarTo && grammarOriginal.value.trim().length > 0
  if (!captured && !captureGrammarSelection()) {
    if (!grammarHint.value) flashGrammarHint('Выделите текст, который нужно проверить.')
    return
  }
  grammarDraft.value = grammarOriginal.value
  grammarDraftDirty.value = false
  grammarDlg.value = true
  void runGrammarCheck()
}

function closeGrammarDialog() {
  grammarDlg.value = false
  grammarBusy.value = false
  grammarErr.value = ''
  grammarResult.value = null
  grammarFrom = 0
  grammarTo = 0
  grammarOriginal.value = ''
  grammarDraft.value = ''
  grammarDraftDirty.value = false
}

async function runGrammarCheck() {
  grammarBusy.value = true
  grammarErr.value = ''
  try {
    const result = await grammarApi.check(grammarOriginal.value)
    grammarResult.value = result
    const first = result.suggestions.find((s) => s.text !== result.original) ?? result.suggestions[0]
    grammarChosen.value = first?.id ?? ''
    if (!grammarDraftDirty.value) {
      grammarDraft.value = first?.text ?? grammarOriginal.value
    }
  } catch (e) {
    grammarErr.value = errMessage(e)
  } finally {
    grammarBusy.value = false
  }
}

function applyAdviceToDraft(item: GrammarAdvice) {
  const src = grammarDraft.value
  const needle = item.before
  if (!needle) {
    grammarDraft.value = `${src}${item.after}`
    grammarDraftDirty.value = true
    return
  }
  let idx = src.indexOf(needle)
  if (idx < 0) idx = src.toLocaleLowerCase().indexOf(needle.toLocaleLowerCase())
  if (idx < 0) return
  grammarDraft.value = src.slice(0, idx) + item.after + src.slice(idx + needle.length)
  grammarDraftDirty.value = true
}

function applyGrammarSuggestion() {
  const ed = editor.value
  const next = grammarDraft.value
  if (!ed || !grammarCanApply.value) return
  const size = ed.state.doc.content.size
  if (grammarFrom < 0 || grammarTo > size || grammarFrom >= grammarTo) {
    flashGrammarHint('Фрагмент в заметке уже изменился. Выделите текст снова.')
    return
  }
  const current = ed.state.doc.textBetween(grammarFrom, grammarTo, '\n', '\n')
  if (current !== grammarOriginal.value) {
    flashGrammarHint('Фрагмент в заметке уже изменился. Выделите текст снова.')
    return
  }
  const ok = applyTextKeepingMarks(ed, grammarFrom, grammarTo, next)
  if (!ok) {
    flashGrammarHint('Не удалось вставить, сохранив оформление.')
    return
  }
  closeGrammarDialog()
}

async function confirmEncrypt() {
  const ed = editor.value
  if (!ed) return
  const pw = encryptPass.value
  if (!pw || pw.length < 4) {
    encryptErr.value = 'Введите ключ не короче 4 символов'
    return
  }
  if (typeof window !== 'undefined' && !isSecureBrowserContext()) {
    encryptErr.value = HTTPS_REQUIRED_MSG
    return
  }
  encryptErr.value = ''
  try {
    const payload = await encryptText(encryptPlain, pw)
    ed.chain()
      .focus()
      .deleteRange({ from: encryptRangeFrom, to: encryptRangeTo })
      .insertContentAt(encryptRangeFrom, {
        type: 'encryptedInline',
        attrs: {
          version: payload.version,
          salt: payload.salt,
          iv: payload.iv,
          ciphertext: payload.ciphertext,
        },
      })
      .run()
    closeEncryptDialog()
  } catch {
    encryptErr.value =
      typeof window !== 'undefined' && !isSecureBrowserContext()
        ? HTTPS_REQUIRED_MSG
        : 'Не удалось зашифровать. Попробуйте другой ключ.'
  }
}

onMounted(() => {
  window.addEventListener('scroll', bumpToolbar, true)
  nextTick(() => {
    const root = editorContentHostRef.value?.querySelector('.ProseMirror')
    if (root) cleanupLegacyTableFilterStyles(root)
  })
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', bumpToolbar, true)
  registerAttachmentBlobResolver(null)
  if (recording.value && mediaRecorder) {
    try {
      mediaRecorder.stop()
    } catch {
      /* */
    }
  }
  cleanupRecordStream()
  editor.value?.destroy()
})
</script>

<template>
  <div class="editor-wrap" :class="{ 'editor-wrap--fit': innerScroll }" v-if="editor">
    <div class="toolbar" v-if="editable" @mousedown="onToolbarMouseDown">
      <button
        type="button"
        class="tb tb-letter"
        title="Жирный"
        aria-label="Жирный"
        :class="{ tbOn: boldOn }"
        :aria-pressed="boldOn"
        @click="editor.chain().focus().toggleBold().run()"
      >
        Ж
      </button>
      <button
        type="button"
        class="tb"
        :class="{ tbOn: bulletListOn }"
        title="Список: у каждой выделенной строки свой маркер"
        aria-label="Список"
        :aria-pressed="bulletListOn"
        @click="toggleLineList('bulletList')"
      >
        Список
      </button>
      <button
        type="button"
        class="tb"
        :class="{ tbOn: orderedListOn }"
        title="Нумерация: у каждой выделенной строки свой номер"
        aria-label="Нумерация"
        :aria-pressed="orderedListOn"
        @click="toggleLineList('orderedList')"
      >
        Нумерация
      </button>
      <button
        type="button"
        class="tb"
        :class="{ tbOn: taskListOn }"
        title="Чек-бокс: у каждой выделенной строки свой флажок"
        aria-label="Чек-бокс"
        :aria-pressed="taskListOn"
        @click="toggleLineList('taskList')"
      >
        Чек-бокс
      </button>
      <details ref="tableDd" class="table-dd">
        <summary
          class="table-dd-summary"
          title="Таблица: вставить или изменить строки и столбцы"
          @pointerdown="onTableSummaryPointerDown"
        >
          <span class="table-dd-label">Таблица</span>
          <span class="table-dd-chev" aria-hidden="true">▼</span>
        </summary>
        <div class="table-dd-panel" @click.stop>
          <template v-if="!showTableRowColPanel">
            <p class="table-dd-hint">Вставить таблицу (первая строка — заголовок):</p>
            <div class="table-dd-grid">
              <button
                type="button"
                class="table-dd-preset"
                aria-label="Таблица 2 столбца на 2 строки"
                @click="insertNoteTable(2, 2, true)"
              >
                2×2
              </button>
              <button
                type="button"
                class="table-dd-preset"
                aria-label="Таблица 3 столбца на 3 строки"
                @click="insertNoteTable(3, 3, true)"
              >
                3×3
              </button>
              <button
                type="button"
                class="table-dd-preset"
                aria-label="Таблица 4 столбца на 4 строки"
                @click="insertNoteTable(4, 4, true)"
              >
                4×4
              </button>
              <button
                type="button"
                class="table-dd-preset"
                aria-label="Таблица 3 столбца на 5 строк"
                @click="insertNoteTable(5, 3, true)"
              >
                3×5
              </button>
            </div>
            <p class="table-dd-hint table-dd-hint--tight">Свой размер (первая строка — заголовок):</p>
            <div class="table-dd-custom">
              <label class="table-dd-custom-field">
                <span class="table-dd-custom-lab">Столбцов</span>
                <input
                  v-model.number="tableCustomCols"
                  type="number"
                  class="table-dd-inp table-dd-inp--inline"
                  :min="TABLE_INSERT_COLS_MIN"
                  :max="TABLE_INSERT_COLS_MAX"
                  step="1"
                  inputmode="numeric"
                  aria-label="Число столбцов"
                  @keydown.enter.prevent="insertCustomNoteTable"
                />
              </label>
              <span class="table-dd-custom-x" aria-hidden="true">×</span>
              <label class="table-dd-custom-field">
                <span class="table-dd-custom-lab">Строк</span>
                <input
                  v-model.number="tableCustomRows"
                  type="number"
                  class="table-dd-inp table-dd-inp--inline"
                  :min="TABLE_INSERT_ROWS_MIN"
                  :max="TABLE_INSERT_ROWS_MAX"
                  step="1"
                  inputmode="numeric"
                  aria-label="Число строк"
                  @keydown.enter.prevent="insertCustomNoteTable"
                />
              </label>
              <button type="button" class="table-dd-act table-dd-act--insert" @click="insertCustomNoteTable">
                Вставить
              </button>
            </div>
            <p v-if="tableCustomErr" class="table-dd-custom-err">{{ tableCustomErr }}</p>
            <p class="table-dd-note">
              Ширина таблицы по колонкам (не на всю строку): граница между ячейками — потянуть мышью. Tab —
              следующая ячейка.
            </p>
          </template>
          <template v-else>
            <p class="table-dd-hint">Строки и столбцы (курсор в ячейке):</p>
            <div class="table-dd-actions">
              <span class="table-dd-grp-lab">Строка</span>
              <div class="table-dd-row table-dd-row--sizes">
                <button
                  type="button"
                  class="table-dd-act"
                  :disabled="!canTableAddRowBefore"
                  title="Вставить строку выше"
                  @click="editor.chain().focus().addRowBefore().run(); closeTableDd()"
                >
                  + сверху
                </button>
                <button
                  type="button"
                  class="table-dd-act"
                  :disabled="!canTableAddRowAfter"
                  title="Вставить строку ниже"
                  @click="editor.chain().focus().addRowAfter().run(); closeTableDd()"
                >
                  + снизу
                </button>
                <button
                  type="button"
                  class="table-dd-act danger"
                  :disabled="!canTableDeleteRow"
                  title="Удалить текущую строку"
                  @click="editor.chain().focus().deleteRow().run(); closeTableDd()"
                >
                  Удалить
                </button>
              </div>
              <span class="table-dd-grp-lab">Столбец</span>
              <div class="table-dd-row table-dd-row--sizes">
                <button
                  type="button"
                  class="table-dd-act"
                  :disabled="!canTableAddColBefore"
                  title="Вставить столбец слева"
                  @click="editor.chain().focus().addColumnBefore().run(); closeTableDd()"
                >
                  + слева
                </button>
                <button
                  type="button"
                  class="table-dd-act"
                  :disabled="!canTableAddColAfter"
                  title="Вставить столбец справа"
                  @click="editor.chain().focus().addColumnAfter().run(); closeTableDd()"
                >
                  + справа
                </button>
                <form
                  v-if="canTableApplySizing"
                  class="table-dd-inline-size"
                  novalidate
                  title="Сейчас на экране — ширина ячейки; в поле — ширина столбца (px), пусто = авто"
                  @submit.prevent="applyColWidthOnly"
                >
                  <span class="table-dd-live-pill" v-if="measuredCellW != null">{{ measuredCellW }} px</span>
                  <input
                    v-model="draftColW"
                    type="number"
                    :min="TABLE_COL_WIDTH_MIN"
                    :max="TABLE_COL_WIDTH_MAX"
                    class="table-dd-inp table-dd-inp--inline"
                    placeholder="w"
                    aria-label="Ширина столбца в пикселях"
                    @blur="clampDraftColW"
                    @change="clampDraftColW"
                  />
                  <button
                    type="submit"
                    class="table-dd-act table-dd-act--narrow"
                    aria-label="Применить ширину столбца"
                    title="Применить ширину"
                  >
                    OK
                  </button>
                </form>
                <button
                  type="button"
                  class="table-dd-act danger"
                  :disabled="!canTableDeleteCol"
                  title="Удалить текущий столбец"
                  @click="editor.chain().focus().deleteColumn().run(); closeTableDd()"
                >
                  Удалить
                </button>
              </div>
              <label class="table-dd-filter-toggle">
                <input
                  type="checkbox"
                  :checked="tableColumnFilterEnabled"
                  @change="toggleTableColumnFiltering"
                />
                <span>Фильтрация по столбцам</span>
              </label>
              <p class="table-dd-hint table-dd-hint--tight">
                Фильтры сохраняются в заметке. Кнопки ▾ появятся в заголовках столбцов.
              </p>
              <div class="table-dd-row table-dd-row--footer">
                <button
                  type="button"
                  class="table-dd-act"
                  :disabled="!canTableToggleHeaderRow"
                  title="Сделать первую строку строкой заголовков или обычной"
                  @click="editor.chain().focus().toggleHeaderRow().run()"
                >
                  Строка заголовков
                </button>
                <button
                  type="button"
                  class="table-dd-act danger"
                  :disabled="!canTableDeleteTable"
                  title="Удалить всю таблицу"
                  @click="editor.chain().focus().deleteTable().run(); closeTableDd()"
                >
                  Удалить таблицу
                </button>
              </div>
            </div>
          </template>
        </div>
      </details>
      <details ref="textColorDd" class="word-dd">
        <summary class="word-dd-summary" @click="onTextColorSummaryClick($event)">
          <span
            class="word-dd-left"
            title="Применить цвет полоски к выделению"
            aria-label="Применить цвет полоски к выделению"
          >
            <span class="word-dd-icon word-dd-icon--letter" aria-hidden="true">A</span>
            <span class="word-dd-bar" :style="{ background: toolbarTextColor }" aria-hidden="true" />
          </span>
          <span
            class="word-dd-chev-wrap"
            title="Палитра: выбрать другой цвет"
            aria-label="Открыть палитру цвета текста"
          >
            <span class="word-dd-chev" aria-hidden="true">▼</span>
          </span>
        </summary>
        <div class="word-dd-panel" @click.stop>
          <div class="word-dd-presets" role="group" aria-label="Цвет букв">
            <button
              v-for="hex in TEXT_COLOR_PRESETS"
              :key="'t-' + hex"
              type="button"
              class="word-dd-dot"
              :title="hex"
              :style="{ background: hex }"
              :class="{ on: isTextPresetActive(hex) }"
              @click="pickTextColor(hex)"
            />
          </div>
          <label class="word-dd-custom">
            <span class="word-dd-custom-lab">Другой цвет…</span>
            <input
              class="word-dd-color-input"
              type="color"
              :value="toolbarTextColor"
              @input="onToolbarTextColorPickInput($event)"
              @change="closeTextColorDd"
            />
          </label>
          <button type="button" class="word-dd-clear" @click="clearTextColorFromMenu">Авто (как в теме)</button>
        </div>
      </details>
      <details ref="highlightDd" class="word-dd">
        <summary class="word-dd-summary" @click="onHighlightSummaryClick($event)">
          <span
            class="word-dd-left"
            title="Применить заливку по полоске к выделению"
            aria-label="Применить заливку по полоске к выделению"
          >
            <span class="word-dd-icon word-dd-icon--hi" aria-hidden="true">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path
                  d="M4 20h4l9.5-9.5a2.5 2.5 0 0 0 0-3.5L17 3.5a2.5 2.5 0 0 0-3.5 0L4 13v7z"
                  stroke="currentColor"
                  stroke-width="1.75"
                  stroke-linejoin="round"
                />
                <path d="M13 6l5 5" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" />
              </svg>
            </span>
            <span class="word-dd-bar" :style="{ background: toolbarHighlightColor }" aria-hidden="true" />
          </span>
          <span
            class="word-dd-chev-wrap"
            title="Палитра: выбрать другой цвет заливки"
            aria-label="Открыть палитру заливки текста"
          >
            <span class="word-dd-chev" aria-hidden="true">▼</span>
          </span>
        </summary>
        <div class="word-dd-panel" @click.stop>
          <div class="word-dd-presets word-dd-presets--sq" role="group" aria-label="Заливка текста">
            <button
              v-for="hex in HIGHLIGHT_FILL_PRESETS"
              :key="'h-' + hex"
              type="button"
              class="word-dd-sq"
              :title="hex"
              :style="{ backgroundColor: hex }"
              :class="{ on: isHighlightFillActive(hex) }"
              @click="pickHighlightFill(hex)"
            />
          </div>
          <label class="word-dd-custom">
            <span class="word-dd-custom-lab">Другой цвет…</span>
            <input
              class="word-dd-color-input"
              type="color"
              :value="toolbarHighlightColor"
              @input="onToolbarHighlightPickInput($event)"
              @change="closeHighlightDd"
            />
          </label>
          <button type="button" class="word-dd-clear" @click="clearHighlightFromMenu">Без заливки</button>
        </div>
      </details>
      <button
        type="button"
        class="tb"
        :disabled="!canEncryptSelection"
        :title="
          !canEncryptSelection
            ? 'Выделите текст в одном абзаце или заголовке'
            : 'Зашифровать выделенный текст (AES-GCM на вашем устройстве)'
        "
        @click="openEncryptDialog"
      >
        Зашифровать
      </button>
      <button
        v-if="canUseGrammar"
        type="button"
        class="tb"
        title="Проверить выделенный текст: орфография, пунктуация, грамматика"
        aria-label="Грамматика и орфография"
        @mousedown="onGrammarMouseDown"
        @click="openGrammarDialog"
      >
        ГР
      </button>
      <button type="button" class="tb" @click="insertExcalidraw">Схема</button>
      <button type="button" class="tb" title="Интеллект-карта, как в редакторе на localhost:8200" @click="insertMindmap">
        Карта
      </button>
      <button type="button" class="tb" title="Диаграмма draw.io (diagrams.net, русский интерфейс)" @click="insertC4">Диаграмма</button>
      <button
        type="button"
        class="tb"
        title="Вставить блок кода (SQL или Python) с подсветкой синтаксиса"
        @click="insertCodeSnippet"
      >
        Код
      </button>
      <input
        ref="fileInputRef"
        type="file"
        class="visually-hidden"
        aria-hidden="true"
        @change="onFilePicked"
      />
      <button
        v-if="editable"
        type="button"
        class="tb"
        title="Загрузить файл или изображение на сервер (до ~25 МБ)"
        @click="triggerFilePick"
      >
        Файл
      </button>
      <button
        v-if="editable"
        type="button"
        class="tb tb-mic"
        :class="{ tbOn: recording }"
        :title="
          recording
            ? 'Остановить запись'
            : 'Записать звук в файл на сервере (WebM/Opus, нужна сохранённая заметка). Качество ~96 kbps'
        "
        @click="recording ? stopRecording() : startRecording()"
      >
        {{ recording ? '■ Стоп' : '🎤 Аудио' }}
      </button>
    </div>
    <p v-if="fileUploadErr" class="record-err">{{ fileUploadErr }}</p>
    <p v-if="recordErr" class="record-err">{{ recordErr }}</p>
    <p v-if="encryptHint" class="encrypt-hint">{{ encryptHint }}</p>
    <p v-if="grammarHint" class="encrypt-hint">{{ grammarHint }}</p>
    <div ref="editorContentHostRef" class="editor-content-host">
      <EditorContent :editor="editor" class="editor-content" />
      <TableColumnFilterOverlay
        v-if="editor"
        :editor="editor"
        :editable="editable"
        :host-el="editorContentHostRef"
      />
    </div>
    <Teleport to="body">
      <div v-if="encryptDlg" class="enc-dlg-root" @click.self="closeEncryptDialog">
        <div class="enc-dlg" role="dialog" aria-labelledby="enc-dlg-title">
          <h3 id="enc-dlg-title" class="enc-dlg-title">Ключ шифрования</h3>
          <p class="enc-dlg-lead muted small">
            Без этого ключа расшифровать нельзя. Ключ не отправляется на сервер — только зашифрованные данные
            попадают в заметку.
          </p>
          <input
            v-model="encryptPass"
            type="password"
            class="enc-dlg-input"
            autocomplete="off"
            placeholder="Придумайте ключ или парольную фразу"
            @keydown.enter.prevent="confirmEncrypt"
          />
          <p v-if="encryptErr" class="enc-dlg-err">{{ encryptErr }}</p>
          <div class="enc-dlg-actions">
            <button type="button" class="enc-dlg-btn" @click="closeEncryptDialog">Отмена</button>
            <button type="button" class="enc-dlg-btn enc-dlg-primary" @click="confirmEncrypt">Зашифровать</button>
          </div>
        </div>
      </div>
    </Teleport>
    <Teleport to="body">
      <div v-if="grammarDlg" class="enc-dlg-root" @click.self="closeGrammarDialog">
        <div class="enc-dlg grammar-dlg" role="dialog" aria-labelledby="grammar-dlg-title">
          <h3 id="grammar-dlg-title" class="enc-dlg-title">Грамматика и орфография</h3>
          <p class="enc-dlg-lead muted small">
            Справа — текст вставки: его можно поправить, в том числе поставить запятую. Цвет,
            заливка и выделение в заметке сохраняются.
          </p>
          <p v-if="grammarBusy" class="muted small">Проверяю текст…</p>
          <p v-if="grammarErr" class="enc-dlg-err">{{ grammarErr }}</p>
          <div v-if="!grammarBusy" class="grammar-compare">
            <div class="grammar-col">
              <div class="grammar-col-lab">Сейчас</div>
              <p class="grammar-text">
                <span
                  v-for="(part, idx) in grammarLeftParts"
                  :key="'l' + idx"
                  :class="['gseg', part.kind !== 'ok' ? 'gseg--' + part.kind : '']"
                  :title="part.message || undefined"
                  >{{ part.text }}</span
                >
              </p>
            </div>
            <div class="grammar-col">
              <div class="grammar-col-lab">Вставка</div>
              <textarea
                v-model="grammarDraft"
                class="grammar-text grammar-text--new grammar-draft"
                rows="6"
                spellcheck="false"
                @input="grammarDraftDirty = true"
              />
              <div v-if="grammarAdvice.length" class="grammar-advice">
                <div class="grammar-col-lab">Совет — нажмите, чтобы подставить</div>
                <ul class="grammar-changes grammar-advice-list">
                  <li v-for="(item, idx) in grammarAdvice.slice(0, 16)" :key="'a' + idx">
                    <button
                      type="button"
                      class="grammar-advice-btn"
                      :title="'Подставить в вставку: ' + item.after"
                      @click="applyAdviceToDraft(item)"
                    >
                      <span class="grammar-advice-old">{{ item.before }}</span>
                      <span class="grammar-chg-arrow" aria-hidden="true">→</span>
                      <span class="grammar-advice-new">{{ item.after }}</span>
                    </button>
                    <span v-if="item.message" class="muted"> — {{ item.message }}</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>
          <ul v-if="grammarChanges.length && !grammarBusy" class="grammar-changes">
            <li v-for="(change, idx) in grammarChanges.slice(0, 12)" :key="idx">
              <span class="grammar-chg-old">{{ change.before || '∅' }}</span>
              <span class="grammar-chg-arrow" aria-hidden="true">→</span>
              <span class="grammar-chg-new">{{ change.after || '∅' }}</span>
              <span v-if="change.message" class="muted"> — {{ change.message }}</span>
            </li>
          </ul>
          <p
            v-if="
              grammarResult &&
              !grammarBusy &&
              !grammarCanApply &&
              !grammarAdvice.length &&
              !grammarChanges.length
            "
            class="muted small"
          >
            Автоматических правок нет. Можно поправить текст справа и вставить.
          </p>
          <div class="enc-dlg-actions">
            <button type="button" class="enc-dlg-btn" @click="closeGrammarDialog">Отмена</button>
            <button
              type="button"
              class="enc-dlg-btn enc-dlg-primary"
              :disabled="!grammarCanApply || grammarBusy"
              @click="applyGrammarSuggestion"
            >
              Вставить
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.editor-wrap {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
}
.editor-wrap--fit {
  flex: 1;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.editor-wrap--fit .toolbar {
  position: sticky;
  top: 0;
  flex-shrink: 0;
}
.editor-wrap--fit .editor-content-host {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.editor-wrap--fit .editor-content {
  min-height: 100%;
}
.editor-content-host {
  position: relative;
}
.editor-wrap:not(.editor-wrap--fit) .editor-content-host {
  overflow-x: auto;
  overflow-y: visible;
  max-width: 100%;
}
/* Без «Скролл в заметке»: страница вниз, горизонтальный скролл у блока текста (широкие таблицы). */
.editor-wrap:not(.editor-wrap--fit) .editor-content {
  overflow: visible;
  max-width: 100%;
}
.editor-wrap:not(.editor-wrap--fit) .editor-content :deep(.tableWrapper),
.editor-wrap:not(.editor-wrap--fit) .editor-content :deep(.ProseMirror > table) {
  width: max-content;
  max-width: none;
}
.editor-wrap:not(.editor-wrap--fit) .editor-content :deep(.ProseMirror table) {
  width: max-content;
  max-width: none;
  table-layout: auto;
}
.editor-wrap--fit :deep(.ProseMirror) {
  min-height: 100%;
}
.toolbar {
  position: sticky;
  top: 0;
  z-index: 25;
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem 0.55rem;
  align-items: center;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--border);
  border-radius: 8px 8px 0 0;
  background: var(--panel);
  box-shadow: 0 1px 0 var(--border);
  user-select: none;
}
.record-err {
  margin: 0;
  padding: 0.25rem 0.75rem 0.45rem;
  font-size: var(--fs-2xs);
  color: var(--danger-text);
  background: var(--danger-subtle);
}
.tb-mic.tbOn {
  border-color: var(--danger);
  color: var(--danger-text);
  background: var(--danger-subtle-hover);
}
.encrypt-hint {
  margin: 0;
  padding: 0.25rem 0.75rem 0.45rem;
  font-size: var(--fs-2xs);
  color: var(--danger-text);
  background: var(--danger-subtle);
}
.enc-dlg-root {
  position: fixed;
  inset: 0;
  z-index: 1200;
  background: var(--scrim);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  box-sizing: border-box;
}
.enc-dlg {
  width: min(400px, 100%);
  padding: 1rem 1.05rem;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  background: var(--surface-overlay);
  box-shadow: var(--shadow-xl);
  color: var(--text-1);
  animation: ui-pop-in var(--dur-slow) var(--ease);
}
.enc-dlg-title {
  margin: 0 0 0.35rem;
  font-size: var(--fs-md);
  font-weight: 650;
}
.enc-dlg-lead {
  margin: 0 0 0.65rem;
  line-height: var(--lh-normal);
}
.enc-dlg-input {
  width: 100%;
  box-sizing: border-box;
  font: inherit;
  font-size: var(--fs-sm);
  padding: 0.4rem 0.5rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  margin-bottom: 0.45rem;
}
.enc-dlg-err {
  margin: 0 0 0.5rem;
  font-size: var(--fs-xs);
  color: var(--danger-text);
}
.enc-dlg-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.35rem;
}
.enc-dlg-btn {
  padding: 0.38rem 0.75rem;
  border-radius: 8px;
  font: inherit;
  font-size: var(--fs-xs);
  cursor: pointer;
  border: 1px solid var(--border);
  background: var(--bg);
}
.enc-dlg-primary {
  background: var(--accent);
  color: var(--text-on-accent);
  border-color: transparent;
  font-weight: 600;
}
.enc-dlg-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.grammar-dlg {
  width: min(780px, 100%);
}
.grammar-compare {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.55rem;
  margin: 0 0 0.65rem;
}
.grammar-col-lab {
  font-size: var(--fs-2xs);
  font-weight: 650;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--note-list-meta);
  margin-bottom: 0.28rem;
}
.grammar-text {
  margin: 0;
  min-height: 5rem;
  max-height: 12rem;
  overflow: auto;
  padding: 0.5rem 0.55rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface-1);
  font: inherit;
  font-size: var(--fs-xs);
  white-space: pre-wrap;
  word-break: break-word;
  line-height: var(--lh-normal);
}
.grammar-text--new {
  border-color: var(--positive-border, var(--accent-border));
  background: var(--positive-subtle, var(--surface-1));
}
.grammar-draft {
  display: block;
  width: 100%;
  resize: vertical;
  box-sizing: border-box;
  color: inherit;
}
.grammar-advice-btn {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.28rem 0.35rem;
  margin: 0;
  padding: 0.12rem 0.2rem;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}
.grammar-advice-btn:hover {
  background: var(--surface-2, var(--border));
}
.grammar-advice {
  margin-top: 0.65rem;
}
.grammar-advice-list {
  max-height: 10rem;
}
.grammar-advice-old {
  color: var(--text-2);
}
.grammar-advice-new {
  color: var(--text-1);
  font-weight: 650;
}
.gseg--error {
  background: var(--danger-subtle);
  color: var(--danger-text);
  border-bottom: 2px solid var(--danger);
  border-radius: 2px;
  box-decoration-break: clone;
}
.gseg--fix {
  background: var(--positive-subtle);
  color: var(--positive-text);
  border-bottom: 2px solid var(--positive);
  border-radius: 2px;
  box-decoration-break: clone;
}
.grammar-changes {
  margin: 0 0 0.65rem;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.28rem;
  font-size: var(--fs-2xs);
  max-height: 7rem;
  overflow: auto;
}
.grammar-changes li {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.28rem 0.35rem;
  line-height: 1.35;
}
.grammar-chg-old {
  color: var(--danger-text);
  text-decoration: line-through;
  text-decoration-thickness: 1px;
}
.grammar-chg-new {
  color: var(--positive-text);
  font-weight: 650;
}
.grammar-chg-arrow {
  color: var(--text-4);
}
.grammar-issues {
  margin: 0 0 0.55rem;
  padding-left: 1.1rem;
  font-size: var(--fs-2xs);
  color: var(--text-3);
  line-height: 1.4;
}
@media (max-width: 640px) {
  .grammar-compare {
    grid-template-columns: 1fr;
  }
}
.tb:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.tb {
  padding: 0.28rem 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg);
  font-size: var(--fs-xs);
  cursor: pointer;
}
.tb:hover {
  border-color: var(--accent);
}
.tbOn {
  border-color: var(--accent);
  background: var(--accent-subtle);
  color: var(--accent-text);
}
.tb-letter {
  min-width: 1.65rem;
  font-weight: 700;
  font-size: var(--fs-xs);
}
.word-dd {
  position: relative;
  display: inline-flex;
  align-items: stretch;
  vertical-align: middle;
}
.word-dd-summary {
  list-style: none;
  display: flex;
  align-items: stretch;
  cursor: pointer;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg);
  padding: 0;
  font: inherit;
  user-select: none;
}
.word-dd-summary::-webkit-details-marker {
  display: none;
}
.word-dd-left {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  padding: 0.22rem 0.4rem 0.25rem;
  min-width: 1.85rem;
}
.word-dd-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-2);
  line-height: 1;
}
.word-dd-icon--letter {
  font-weight: 800;
  font-size: var(--fs-sm);
  font-family: system-ui, 'Segoe UI', sans-serif;
}
.word-dd-icon--hi svg {
  display: block;
}
.word-dd-bar {
  display: block;
  height: 3px;
  width: 100%;
  min-width: 1.35rem;
  margin-top: 3px;
  border-radius: 1px;
  box-sizing: border-box;
}
.word-dd-chev-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 0.28rem;
  border-left: 1px solid var(--border);
  background: var(--surface-wash);
}
.word-dd-chev {
  font-size: var(--fs-2xs);
  line-height: 1;
  color: var(--text-4);
  transform: scaleY(0.85);
}
.word-dd:hover .word-dd-summary,
.word-dd[open] .word-dd-summary {
  border-color: var(--accent-border);
}
.word-dd-panel {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 50;
  min-width: 11.5rem;
  padding: 0.5rem 0.55rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--panel);
  box-shadow: 0 8px 24px var(--shadow-tint);
}
.word-dd-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 0.45rem;
}
.word-dd-dot {
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 50%;
  border: 2px solid var(--surface-1);
  box-shadow: 0 0 0 1px var(--shadow-tint);
  cursor: pointer;
  padding: 0;
  flex-shrink: 0;
}
.word-dd-dot.on {
  box-shadow: 0 0 0 2px var(--accent);
}
.word-dd-presets--sq {
  gap: 0.28rem;
}
.word-dd-sq {
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 4px;
  border: 1px solid var(--border-strong);
  cursor: pointer;
  padding: 0;
  box-sizing: border-box;
}
.word-dd-sq.on {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}
.word-dd-custom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 0.35rem;
  font-size: var(--fs-2xs);
  color: var(--text-muted);
  cursor: pointer;
}
.word-dd-color-input {
  width: 2rem;
  height: 1.35rem;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  background: transparent;
}
.word-dd-clear {
  display: block;
  width: 100%;
  margin-top: 0.15rem;
  padding: 0.22rem 0.35rem;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--accent-text);
  font: inherit;
  font-size: var(--fs-2xs);
  cursor: pointer;
  text-align: left;
}
.word-dd-clear:hover {
  text-decoration: underline;
}
.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.editor-content :deep(.ProseMirror) {
  min-height: 220px;
  padding: 0.75rem 1rem;
  outline: none;
  line-height: var(--lh-normal);
}
.editor-content :deep(.ProseMirror::after) {
  content: '';
  display: table;
  clear: both;
}
.editor-content :deep(.ProseMirror > p) {
  margin: 0.2em 0;
}
/* Маркеры и номера: высота как у переноса в обычном тексте, без широкого отступа. */
.editor-content :deep(.ProseMirror ul:not([data-type='taskList'])),
.editor-content :deep(.ProseMirror ol) {
  margin: 0.2em 0;
  padding: 0 0 0 1.2em;
  line-height: var(--lh-normal);
}
.editor-content :deep(.ProseMirror ul:not([data-type='taskList']) ul),
.editor-content :deep(.ProseMirror ol ol),
.editor-content :deep(.ProseMirror ul:not([data-type='taskList']) ol),
.editor-content :deep(.ProseMirror ol ul:not([data-type='taskList'])) {
  margin: 0;
  padding-left: 1.15em;
}
.editor-content :deep(.ProseMirror ul:not([data-type='taskList']) > li),
.editor-content :deep(.ProseMirror ol > li) {
  margin: 0;
  padding: 0;
  line-height: var(--lh-normal);
}
.editor-content :deep(.ProseMirror ul:not([data-type='taskList']) > li > p),
.editor-content :deep(.ProseMirror ol > li > p) {
  margin: 0;
  padding: 0;
  line-height: var(--lh-normal);
}
.editor-content :deep(.ProseMirror img) {
  max-width: 100%;
  height: auto;
}
.editor-content :deep(.ProseMirror mark) {
  border-radius: 3px;
  /* Заливка приходит из заметки инлайном и всегда пастельная — текст держим тёмным. */
  color: var(--text-on-highlight);
  padding: 0.06em 0.1em;
  box-decoration-break: clone;
  -webkit-box-decoration-break: clone;
}
/* Чек-бокс: без отступов списка, пункт = одна строка «галочка | текст» */
.editor-content :deep(ul[data-type='taskList']) {
  list-style: none;
  padding: 0;
  margin: 0.25rem 0;
}
.editor-content :deep(ul[data-type='taskList'] ul[data-type='taskList']) {
  margin: 0.15rem 0 0 0.5rem;
}
/* li по умолчанию display:list-item — ломает раскладку; только flex + nowrap */
.editor-content :deep(ul[data-type='taskList'] > li) {
  display: flex !important;
  flex-direction: row !important;
  flex-wrap: nowrap !important;
  align-items: center;
  gap: 0.4rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.editor-content :deep(ul[data-type='taskList'] > li > label) {
  flex: 0 0 auto;
  display: inline-flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  margin: 0;
  padding: 0;
  user-select: none;
  line-height: 1;
  vertical-align: middle;
}
.editor-content :deep(ul[data-type='taskList'] > li > label input[type='checkbox']) {
  width: 0.95rem;
  height: 0.95rem;
  margin: 0;
  cursor: pointer;
  accent-color: var(--accent);
  flex-shrink: 0;
  vertical-align: middle;
}
.editor-content :deep(ul[data-type='taskList'] > li > label > span) {
  display: none;
  width: 0;
  height: 0;
  overflow: hidden;
}
/* contentDOM TipTap — текст пункта, одна линия с чекбоксом */
.editor-content :deep(ul[data-type='taskList'] > li > div) {
  flex: 1 1 auto;
  min-width: 0;
  margin: 0;
  padding: 0;
  align-self: center;
}
.editor-content :deep(ul[data-type='taskList'] > li > div > p) {
  margin: 0;
  padding: 0;
  line-height: var(--lh-normal);
}
.editor-content :deep(ul[data-type='taskList'] > li[data-checked='true'] > div p) {
  opacity: 0.65;
  text-decoration: line-through;
}

/* —— Таблицы (TipTap TableKit) —— */
.table-dd {
  position: relative;
  display: inline-flex;
  align-items: stretch;
  vertical-align: middle;
}
.table-dd-summary {
  list-style: none;
  display: inline-flex;
  align-items: center;
  gap: 0.28rem;
  cursor: pointer;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  padding: 0.28rem 0.45rem;
  font: inherit;
  font-size: var(--fs-xs);
  user-select: none;
}
.table-dd-summary::-webkit-details-marker {
  display: none;
}
.table-dd-label {
  font-weight: 500;
}
.table-dd-chev {
  font-size: var(--fs-2xs);
  color: var(--text-4);
  line-height: 1;
}
.table-dd:hover .table-dd-summary,
.table-dd[open] .table-dd-summary {
  border-color: var(--accent-border);
}
.table-dd-panel {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 60;
  width: min(19.5rem, calc(100vw - 2rem));
  padding: 0.55rem 0.6rem 0.6rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--panel);
  box-shadow: 0 8px 24px var(--shadow-tint);
}
.table-dd-hint {
  margin: 0 0 0.4rem;
  font-size: var(--fs-2xs);
  font-weight: 600;
  color: var(--text-3);
}
.table-dd-hint--tight {
  margin-top: 0.55rem;
}
.table-dd-custom {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 0.35rem 0.45rem;
  margin-bottom: 0.15rem;
}
.table-dd-custom-field {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  min-width: 0;
}
.table-dd-custom-lab {
  font-size: var(--fs-2xs);
  color: var(--text-4);
}
.table-dd-custom-x {
  align-self: center;
  padding-bottom: 0.28rem;
  font-size: var(--fs-sm);
  color: var(--text-3);
  line-height: 1;
}
.table-dd-act--insert {
  flex: 0 0 auto;
  min-width: 5.5rem;
  align-self: flex-end;
}
.table-dd-custom-err {
  margin: 0.15rem 0 0;
  font-size: var(--fs-2xs);
  color: var(--danger-text);
}
.table-dd-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.35rem;
}
.table-dd-preset {
  padding: 0.38rem 0.45rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--bg);
  font: inherit;
  font-size: var(--fs-2xs);
  font-weight: 600;
  cursor: pointer;
  color: var(--accent-text);
}
.table-dd-preset:hover {
  border-color: var(--accent-border);
  background: var(--accent-subtle);
}
.table-dd-note {
  margin: 0.45rem 0 0;
  font-size: var(--fs-2xs);
  line-height: var(--lh-normal);
  color: var(--text-4);
}
.table-dd-inp {
  width: 100%;
  box-sizing: border-box;
  padding: 0.32rem 0.4rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: inherit;
  font: inherit;
  font-size: var(--fs-xs);
}
.table-dd-actions {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.table-dd-grp-lab {
  font-size: var(--fs-2xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-4);
  margin-top: 0.15rem;
}
.table-dd-grp-lab:first-child {
  margin-top: 0;
}
.table-dd-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
}
.table-dd-row--sizes {
  align-items: center;
}
.table-dd-inline-size {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.28rem;
  flex: 1 1 7.5rem;
  min-width: 6.75rem;
  margin: 0;
  padding: 0;
  border: none;
  background: transparent;
}
.table-dd-live-pill {
  font-size: var(--fs-2xs);
  font-weight: 700;
  color: var(--accent-text);
  white-space: nowrap;
  padding: 0.12rem 0.32rem;
  border-radius: 4px;
  background: var(--accent-subtle);
}
.table-dd-inp--inline {
  width: 3.75rem;
  min-width: 0;
  flex: 0 0 auto;
  padding: 0.26rem 0.32rem;
  font-size: var(--fs-2xs);
}
.table-dd-act--narrow {
  flex: 0 0 auto;
  min-width: 2.1rem;
  padding: 0.26rem 0.4rem;
  font-weight: 600;
}
.table-dd-filter-toggle {
  display: flex;
  align-items: flex-start;
  gap: 0.45rem;
  margin-top: 0.35rem;
  font-size: var(--fs-xs);
  color: var(--text-2);
  cursor: pointer;
}
.table-dd-filter-toggle input {
  margin-top: 0.12rem;
  flex-shrink: 0;
}
.table-dd-row--footer {
  margin-top: 0.25rem;
  padding-top: 0.45rem;
  border-top: 1px solid var(--border);
}
.table-dd-act {
  flex: 1 1 auto;
  min-width: 0;
  padding: 0.32rem 0.4rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg);
  font: inherit;
  font-size: var(--fs-2xs);
  cursor: pointer;
  color: var(--text-2);
}
.table-dd-act:hover:not(:disabled) {
  border-color: var(--accent-border);
}
.table-dd-act:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.table-dd-act.danger {
  color: var(--danger-text);
  border-color: var(--danger-border-strong);
}
.table-dd-act.danger:hover:not(:disabled) {
  background: var(--danger-subtle);
}

.editor-content :deep(.tableWrapper),
.editor-content :deep(.ProseMirror > table) {
  margin: 0.65rem 0;
  overflow: visible;
  /* Таблица по ширине содержимого/колонок, без отдельного скролла обёртки */
  width: max-content;
  max-width: 100%;
}
.editor-content :deep(.ProseMirror table) {
  border-collapse: collapse;
  table-layout: fixed;
  width: auto;
  max-width: 100%;
  overflow: hidden;
  font-size: var(--fs-sm);
}
.editor-content :deep(.ProseMirror table td),
.editor-content :deep(.ProseMirror table th) {
  border: 1px solid var(--border);
  padding: 0.35rem 0.45rem;
  vertical-align: top;
  min-width: 2rem;
  box-sizing: border-box;
  position: relative;
}
.editor-content :deep(.ProseMirror table th) {
  background: var(--surface-wash);
  font-weight: 600;
  text-align: left;
}
.editor-content :deep(.tableWrapper .selectedCell:after) {
  z-index: 2;
  position: absolute;
  content: '';
  left: 0;
  right: 0;
  top: 0;
  bottom: 0;
  background: var(--accent-subtle-hover);
  pointer-events: none;
}
.editor-content :deep(.tableWrapper .column-resize-handle) {
  position: absolute;
  right: -3px;
  top: 0;
  bottom: -2px;
  width: 6px;
  background: var(--accent);
  cursor: col-resize;
  pointer-events: auto;
  z-index: 3;
  opacity: 0.65;
}
.editor-content :deep(.ProseMirror table p) {
  margin: 0;
}
.editor-content :deep(.ProseMirror table p + p) {
  margin-top: 0.35em;
}
.editor-content :deep(tr.note-table-row--filtered-out) {
  display: none;
}
</style>
