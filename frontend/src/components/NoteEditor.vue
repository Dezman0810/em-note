<script setup lang="ts">
import Color from '@tiptap/extension-color'
import Highlight from '@tiptap/extension-highlight'
import Image from '@tiptap/extension-image'
import TaskList from '@tiptap/extension-task-list'
import { splitSelectedBlocksAtHardBreaks } from './tiptap/splitBlocksAtHardBreaks'
import { TaskItemNote } from './tiptap/taskItemNote'
import { TaskListEnterKeymap } from './tiptap/taskListEnterKeymap'
import { TextStyle } from '@tiptap/extension-text-style'
import StarterKit from '@tiptap/starter-kit'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import { computed, onBeforeUnmount, ref, watch } from 'vue'

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

function parseDoc(raw: string) {
  try {
    const j = JSON.parse(raw || '{}')
    return j && typeof j === 'object' ? j : {}
  } catch {
    return {}
  }
}

const editor = useEditor({
  editable: props.editable,
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

function addImageFromUrl() {
  const url = window.prompt('URL изображения')
  if (url) editor.value?.chain().focus().setImage({ src: url }).run()
}

onBeforeUnmount(() => editor.value?.destroy())
</script>

<template>
  <div class="editor-wrap" v-if="editor">
    <div class="toolbar" v-if="editable">
      <button type="button" class="tb" @click="editor.chain().focus().toggleBold().run()">Жирный</button>
      <button type="button" class="tb" @click="editor.chain().focus().toggleItalic().run()">Курсив</button>
      <button type="button" class="tb" @click="editor.chain().focus().toggleBulletList().run()">Список</button>
      <button
        type="button"
        class="tb"
        :class="{ tbOn: taskListOn }"
        @click="toggleChecklist()"
      >
        Чек-лист
      </button>
      <div class="color-group">
        <span class="color-group-lab">Буквы</span>
        <div class="color-presets" role="group" aria-label="Цвет букв">
          <button
            v-for="hex in TEXT_COLOR_PRESETS"
            :key="'t-' + hex"
            type="button"
            class="color-dot"
            :title="hex"
            :style="{ background: hex }"
            :class="{ on: isTextPresetActive(hex) }"
            @click="setTextColor(hex)"
          />
        </div>
        <label class="color-picker-wrap" title="Свой цвет букв">
          <span class="visually-hidden">Палитра цвета букв</span>
          <input
            class="color-picker-input"
            type="color"
            :value="colorPickerValue"
            @input="setTextColor(($event.target as HTMLInputElement).value)"
          />
        </label>
        <button type="button" class="tb tb-compact" @click="unsetTextColor">Сброс букв</button>
      </div>
      <div class="color-group color-group-extra" role="group" aria-label="Заливка вокруг текста">
        <span class="color-group-lab">Заливка</span>
        <div class="color-squares">
          <button
            v-for="hex in HIGHLIGHT_FILL_PRESETS"
            :key="'h-' + hex"
            type="button"
            class="color-sq"
            :title="hex"
            :style="{ backgroundColor: hex }"
            :class="{ on: isHighlightFillActive(hex) }"
            @click="setHighlightFill(hex)"
          />
        </div>
        <label class="color-picker-wrap color-picker-square" title="Своя заливка">
          <span class="visually-hidden">Палитра заливки</span>
          <input
            class="color-picker-input"
            type="color"
            :value="highlightPickerValue"
            @input="setHighlightFill(($event.target as HTMLInputElement).value)"
          />
        </label>
        <button type="button" class="tb tb-compact" @click="unsetHighlightFill">Сброс заливки</button>
      </div>
      <button type="button" class="tb" @click="addImageFromUrl">Картинка</button>
    </div>
    <EditorContent :editor="editor" class="editor-content" />
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
.tb-compact {
  font-size: 0.72rem;
}
.color-group {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem 0.45rem;
  padding: 0.15rem 0.35rem;
  border-radius: 8px;
  background: rgba(148, 163, 184, 0.08);
}
.color-group-lab {
  font-size: 0.68rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
}
.color-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}
.color-dot {
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.9);
  box-shadow: 0 0 0 1px rgba(15, 23, 42, 0.12);
  cursor: pointer;
  padding: 0;
  flex-shrink: 0;
}
.color-dot:hover {
  transform: scale(1.06);
}
.color-dot.on {
  box-shadow: 0 0 0 2px var(--accent);
}
.color-group-extra {
  border: 1px dashed rgba(148, 163, 184, 0.45);
}
.color-squares {
  display: flex;
  flex-wrap: wrap;
  gap: 0.28rem;
}
.color-sq {
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 4px;
  /* Заливка задаётся inline backgroundColor */
  border: 1px solid rgba(15, 23, 42, 0.28);
  box-sizing: border-box;
  cursor: pointer;
  padding: 0;
  flex-shrink: 0;
}
.color-sq:hover {
  filter: brightness(1.06);
  border-color: rgba(15, 23, 42, 0.45);
}
.color-sq.on {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}
.color-picker-square .color-picker-input {
  border-radius: 4px;
}
.color-picker-wrap {
  display: inline-flex;
  align-items: center;
  cursor: pointer;
}
.color-picker-input {
  width: 1.55rem;
  height: 1.25rem;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  background: transparent;
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
