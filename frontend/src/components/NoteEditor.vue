<script setup lang="ts">
import Color from '@tiptap/extension-color'
import Highlight from '@tiptap/extension-highlight'
import Image from '@tiptap/extension-image'
import TaskList from '@tiptap/extension-task-list'
import { splitSelectedBlocksAtHardBreaks } from './tiptap/splitBlocksAtHardBreaks'
import { EncryptedInline } from './tiptap/EncryptedInlineExtension'
import { AudioNoteBlock } from './tiptap/AudioNoteExtension'
import { ExcalidrawBlock } from './tiptap/ExcalidrawExtension'
import { TaskItemNote } from './tiptap/taskItemNote'
import { TaskListEnterKeymap } from './tiptap/taskListEnterKeymap'
import { TextStyle } from '@tiptap/extension-text-style'
import StarterKit from '@tiptap/starter-kit'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { encryptText, HTTPS_REQUIRED_MSG, isSecureBrowserContext } from '../utils/cryptoSecret'

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
  defineProps<{ contentJson: string; editable?: boolean }>(),
  { editable: true }
)
const emit = defineEmits<{ (e: 'update:contentJson', value: string): void }>()

const toolbarTick = ref(0)

const MAX_AUDIO_BYTES = 12 * 1024 * 1024

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

function parseDoc(raw: string) {
  try {
    const j = JSON.parse(raw || '{}')
    return j && typeof j === 'object' ? j : {}
  } catch {
    return {}
  }
}

function isUndoRedoShortcut(event: KeyboardEvent) {
  const mod = event.ctrlKey || event.metaKey
  if (!mod) return false
  const k = event.key.toLowerCase()
  if (k === 'z') return true
  if (k === 'y') return true
  return false
}

const editor = useEditor({
  editable: props.editable,
  editorProps: {
    handleDOMEvents: {
      keydown(_view, event) {
        const ae = document.activeElement
        if (!ae?.closest('[data-excalidraw-root]')) return false
        if (!isUndoRedoShortcut(event)) return false
        return true
      },
    },
  },
  extensions: [
    StarterKit.configure({
      heading: { levels: [2, 3] },
    }),
    TaskList,
    TaskItemNote.configure({ nested: false }),
    TaskListEnterKeymap,
    TextStyle,
    Color,
    Highlight.configure({ multicolor: true }),
    Image.configure({ inline: true, allowBase64: true }),
    EncryptedInline,
    ExcalidrawBlock,
    AudioNoteBlock,
  ],
  content: parseDoc(props.contentJson),
  onUpdate: ({ editor: ed }) => {
    emit('update:contentJson', JSON.stringify(ed.getJSON()))
  },
  onSelectionUpdate: () => {
    toolbarTick.value++
  },
  onTransaction: () => {
    toolbarTick.value++
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

watch(
  () => props.contentJson,
  (v) => {
    const ed = editor.value
    if (!ed || ed.isDestroyed) return
    const next = parseDoc(v)
    const cur = ed.getJSON()
    if (JSON.stringify(cur) === JSON.stringify(next)) return
    ed.commands.setContent(next, { emitUpdate: false })
  }
)

const colorPickerValue = computed(() => {
  void toolbarTick.value
  const c = editor.value?.getAttributes('textStyle')?.color
  if (typeof c === 'string' && /^#[0-9A-Fa-f]{6}$/.test(c)) return c
  return '#1e293b'
})

const highlightPickerValue = computed(() => {
  void toolbarTick.value
  const c = editor.value?.getAttributes('highlight')?.color
  if (typeof c === 'string' && /^#[0-9A-Fa-f]{6}$/i.test(c)) return c.toLowerCase()
  return '#fef08a'
})

const taskListOn = computed(() => {
  void toolbarTick.value
  return editor.value?.isActive('taskList') ?? false
})

const boldOn = computed(() => {
  void toolbarTick.value
  return editor.value?.isActive('bold') ?? false
})

const italicOn = computed(() => {
  void toolbarTick.value
  return editor.value?.isActive('italic') ?? false
})

const textColorDd = ref<HTMLDetailsElement | null>(null)
const highlightDd = ref<HTMLDetailsElement | null>(null)

function pickTextColor(hex: string) {
  setTextColor(hex)
  if (textColorDd.value) textColorDd.value.open = false
}

function clearTextColorFromMenu() {
  unsetTextColor()
  if (textColorDd.value) textColorDd.value.open = false
}

function pickHighlightFill(hex: string) {
  setHighlightFill(hex)
  if (highlightDd.value) highlightDd.value.open = false
}

function clearHighlightFromMenu() {
  unsetHighlightFill()
  if (highlightDd.value) highlightDd.value.open = false
}

function closeTextColorDd() {
  if (textColorDd.value) textColorDd.value.open = false
}

function closeHighlightDd() {
  if (highlightDd.value) highlightDd.value.open = false
}

/** Несколько абзацев или строк в одном абзаце (переносы) → отдельные пункты чек-листа. */
function toggleChecklist() {
  const ed = editor.value
  if (!ed) return
  ed.chain()
    .focus()
    .command(({ tr, state }) => {
      splitSelectedBlocksAtHardBreaks(state, tr)
      return true
    })
    .toggleTaskList()
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

function pickAudioMime(): string {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']
  for (const c of candidates) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(c)) return c
  }
  return ''
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
    recordStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const mime = pickAudioMime()
    const opts = mime ? { mimeType: mime } : undefined
    mediaRecorder = new MediaRecorder(recordStream, opts)
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
      const mimeType = mr?.mimeType || 'audio/webm'
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
      const reader = new FileReader()
      reader.onload = () => {
        const src = reader.result as string
        const edNow = editor.value
        if (!edNow) return
        edNow.chain().focus().insertAudioNote({ src, mime: blob.type, label: '' }).run()
      }
      reader.onerror = () => {
        recordErr.value = 'Не удалось прочитать запись.'
      }
      reader.readAsDataURL(blob)
    }
    mediaRecorder.start(400)
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

onBeforeUnmount(() => {
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
  <div class="editor-wrap" v-if="editor">
    <div class="toolbar" v-if="editable">
      <button
        type="button"
        class="tb tb-letter"
        title="Жирный"
        :class="{ tbOn: boldOn }"
        @click="editor.chain().focus().toggleBold().run()"
      >
        Ж
      </button>
      <button
        type="button"
        class="tb tb-letter"
        title="Курсив"
        :class="{ tbOn: italicOn }"
        @click="editor.chain().focus().toggleItalic().run()"
      >
        К
      </button>
      <button type="button" class="tb" @click="editor.chain().focus().toggleBulletList().run()">Список</button>
      <button
        type="button"
        class="tb"
        :class="{ tbOn: taskListOn }"
        @click="toggleChecklist()"
      >
        Чек-лист
      </button>
      <details ref="textColorDd" class="word-dd">
        <summary class="word-dd-summary" title="Цвет текста">
          <span class="word-dd-left" aria-hidden="true">
            <span class="word-dd-icon word-dd-icon--letter">A</span>
            <span class="word-dd-bar" :style="{ background: colorPickerValue }" />
          </span>
          <span class="word-dd-chev-wrap" aria-hidden="true">
            <span class="word-dd-chev">▼</span>
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
              :value="colorPickerValue"
              @input="setTextColor(($event.target as HTMLInputElement).value)"
              @change="closeTextColorDd"
            />
          </label>
          <button type="button" class="word-dd-clear" @click="clearTextColorFromMenu">Авто (как в теме)</button>
        </div>
      </details>
      <details ref="highlightDd" class="word-dd">
        <summary class="word-dd-summary" title="Цвет выделения">
          <span class="word-dd-left" aria-hidden="true">
            <span class="word-dd-icon word-dd-icon--hi">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                <path
                  d="M4 20h4l9.5-9.5a2.5 2.5 0 0 0 0-3.5L17 3.5a2.5 2.5 0 0 0-3.5 0L4 13v7z"
                  stroke="currentColor"
                  stroke-width="1.75"
                  stroke-linejoin="round"
                />
                <path d="M13 6l5 5" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" />
              </svg>
            </span>
            <span class="word-dd-bar" :style="{ background: highlightPickerValue }" />
          </span>
          <span class="word-dd-chev-wrap" aria-hidden="true">
            <span class="word-dd-chev">▼</span>
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
              :value="highlightPickerValue"
              @input="setHighlightFill(($event.target as HTMLInputElement).value)"
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
      <button type="button" class="tb" @click="insertExcalidraw">Схема</button>
      <button
        v-if="editable"
        type="button"
        class="tb tb-mic"
        :class="{ tbOn: recording }"
        :title="recording ? 'Остановить запись' : 'Записать аудиозаметку (микрофон)'"
        @click="recording ? stopRecording() : startRecording()"
      >
        {{ recording ? '■ Стоп' : '🎤 Аудио' }}
      </button>
    </div>
    <p v-if="recordErr" class="record-err">{{ recordErr }}</p>
    <p v-if="encryptHint" class="encrypt-hint">{{ encryptHint }}</p>
    <EditorContent :editor="editor" class="editor-content" />
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
  </div>
</template>

<style scoped>
.editor-wrap {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem 0.55rem;
  align-items: center;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--border);
}
.record-err {
  margin: 0;
  padding: 0.25rem 0.75rem 0.45rem;
  font-size: 0.72rem;
  color: var(--danger);
  background: rgba(220, 38, 38, 0.06);
}
.tb-mic.tbOn {
  border-color: #dc2626;
  color: #dc2626;
  background: rgba(220, 38, 38, 0.1);
}
.encrypt-hint {
  margin: 0;
  padding: 0.25rem 0.75rem 0.45rem;
  font-size: 0.72rem;
  color: var(--danger);
  background: rgba(220, 38, 38, 0.06);
}
.enc-dlg-root {
  position: fixed;
  inset: 0;
  z-index: 1200;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  box-sizing: border-box;
}
.enc-dlg {
  width: min(400px, 100%);
  padding: 1rem 1.05rem;
  border-radius: var(--radius-lg, 14px);
  border: 1px solid var(--border);
  background: var(--panel);
  box-shadow: var(--shadow-panel, 0 8px 40px rgba(15, 23, 42, 0.15));
}
.enc-dlg-title {
  margin: 0 0 0.35rem;
  font-size: 0.95rem;
  font-weight: 650;
}
.enc-dlg-lead {
  margin: 0 0 0.65rem;
  line-height: 1.4;
}
.enc-dlg-input {
  width: 100%;
  box-sizing: border-box;
  font: inherit;
  font-size: 0.85rem;
  padding: 0.4rem 0.5rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  margin-bottom: 0.45rem;
}
.enc-dlg-err {
  margin: 0 0 0.5rem;
  font-size: 0.78rem;
  color: var(--danger);
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
  font-size: 0.8rem;
  cursor: pointer;
  border: 1px solid var(--border);
  background: var(--bg);
}
.enc-dlg-primary {
  background: var(--accent);
  color: #fff;
  border-color: transparent;
  font-weight: 600;
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
  font-size: 0.78rem;
  cursor: pointer;
}
.tb:hover {
  border-color: var(--accent);
}
.tbOn {
  border-color: var(--accent);
  background: rgba(37, 99, 235, 0.08);
  color: var(--accent);
}
.tb-letter {
  min-width: 1.65rem;
  font-weight: 700;
  font-size: 0.82rem;
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
  color: #334155;
  line-height: 1;
}
.word-dd-icon--letter {
  font-weight: 800;
  font-size: 0.88rem;
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
  background: rgba(148, 163, 184, 0.06);
}
.word-dd-chev {
  font-size: 0.5rem;
  line-height: 1;
  color: #64748b;
  transform: scaleY(0.85);
}
.word-dd:hover .word-dd-summary,
.word-dd[open] .word-dd-summary {
  border-color: rgba(37, 99, 235, 0.35);
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
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
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
  border: 2px solid rgba(255, 255, 255, 0.95);
  box-shadow: 0 0 0 1px rgba(15, 23, 42, 0.12);
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
  border: 1px solid rgba(15, 23, 42, 0.28);
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
  font-size: 0.72rem;
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
  color: var(--accent);
  font: inherit;
  font-size: 0.72rem;
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
  line-height: 1.45;
}
.editor-content :deep(.ProseMirror > p) {
  margin: 0.2em 0;
}
.editor-content :deep(.ProseMirror img) {
  max-width: 100%;
  height: auto;
}
.editor-content :deep(.ProseMirror mark) {
  border-radius: 3px;
  padding: 0.06em 0.1em;
  box-decoration-break: clone;
  -webkit-box-decoration-break: clone;
}
/* Чек-лист: без отступов списка, пункт = одна строка «галочка | текст» как в примере */
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
  padding: 0.1rem 0;
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
  line-height: 1.4;
}
.editor-content :deep(ul[data-type='taskList'] > li[data-checked='true'] > div p) {
  opacity: 0.65;
  text-decoration: line-through;
}
</style>
