<script setup lang="ts">
import { NodeViewWrapper, nodeViewProps } from '@tiptap/vue-3'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  codeSnippetLanguageLabel,
  defaultCodeSnippetTitle,
  type CodeSnippetLanguage,
} from '../../utils/highlightCode'
import { createCodeMirrorHost, type CodeMirrorHost } from '../../utils/codeMirrorHost'
import { formatSqlCode } from '../../utils/formatSql'
import { formatPythonCode } from '../../utils/formatPython'

const props = defineProps(nodeViewProps)

const expanded = ref(!props.node.attrs.collapsed)
const copyDone = ref(false)
const formatErr = ref('')
const formatting = ref(false)
const cmHostRef = ref<HTMLDivElement | null>(null)
let cmHost: CodeMirrorHost | null = null
let syncingDoc = false

const code = computed(() => String(props.node.attrs.code ?? ''))

const language = computed({
  get: () => (props.node.attrs.language === 'python' ? 'python' : 'sql') as CodeSnippetLanguage,
  set: (v: CodeSnippetLanguage) => {
    const prevDefault = defaultCodeSnippetTitle(String(props.node.attrs.language ?? 'sql'))
    const title = String(props.node.attrs.title ?? '').trim()
    const nextTitle = !title || title === prevDefault ? defaultCodeSnippetTitle(v) : title
    props.updateAttributes({ language: v, title: nextTitle })
  },
})

const title = computed({
  get: () => String(props.node.attrs.title ?? ''),
  set: (v: string) => props.updateAttributes({ title: v }),
})

const collapseLabel = computed(() => {
  const lang = codeSnippetLanguageLabel(language.value)
  return expanded.value ? `▼ ${lang}` : `▶ ${lang}`
})

watch(
  () => props.node.attrs.collapsed,
  (c) => {
    expanded.value = !c
  }
)

watch(expanded, async (on) => {
  if (on) {
    await nextTick()
    mountCodeMirror()
  } else {
    destroyCodeMirror()
  }
})

watch(
  () => props.node.attrs.code,
  (next) => {
    if (!cmHost || syncingDoc) return
    cmHost.setDoc(String(next ?? ''))
  }
)

watch(language, (next) => {
  cmHost?.setLanguage(next)
})

watch(
  () => props.editor.isEditable,
  (next) => {
    cmHost?.setEditable(next)
  }
)

onMounted(async () => {
  if (expanded.value) {
    await nextTick()
    mountCodeMirror()
  }
})

onBeforeUnmount(() => {
  destroyCodeMirror()
})

function mountCodeMirror() {
  destroyCodeMirror()
  const parent = cmHostRef.value
  if (!parent) return

  cmHost = createCodeMirrorHost(parent, {
    doc: code.value,
    language: language.value,
    editable: props.editor.isEditable,
    placeholder: props.editor.isEditable ? 'Вставьте или введите код…' : undefined,
    onDocChange: (value) => {
      if (syncingDoc) return
      formatErr.value = ''
      props.updateAttributes({ code: value })
    },
  })
}

function destroyCodeMirror() {
  cmHost?.destroy()
  cmHost = null
}

function toggle() {
  const next = !expanded.value
  expanded.value = next
  props.updateAttributes({ collapsed: !next })
}

async function copyCode() {
  const text = code.value
  if (!text.trim()) return
  try {
    await navigator.clipboard.writeText(text)
    copyDone.value = true
    window.setTimeout(() => {
      copyDone.value = false
    }, 1600)
  } catch {
    /* ignore */
  }
}

function stopBubble(ev: Event) {
  ev.stopPropagation()
}

function applyFormattedCode(formatted: string) {
  syncingDoc = true
  props.updateAttributes({ code: formatted })
  cmHost?.setDoc(formatted)
  syncingDoc = false
  cmHost?.focus()
}

function formatSql() {
  formatErr.value = ''
  const src = code.value
  if (!src.trim()) return
  try {
    applyFormattedCode(formatSqlCode(src))
  } catch {
    formatErr.value = 'Не удалось отформатировать SQL'
  }
}

async function formatPython() {
  formatErr.value = ''
  const src = code.value
  if (!src.trim()) return
  formatting.value = true
  try {
    applyFormattedCode(await formatPythonCode(src))
  } catch {
    formatErr.value = 'Не удалось отформатировать Python'
  } finally {
    formatting.value = false
  }
}
</script>

<template>
  <NodeViewWrapper class="code-snippet-node" contenteditable="false">
    <div class="code-snippet-head">
      <button type="button" class="code-snippet-btn code-snippet-btn-main" @click="toggle">
        {{ collapseLabel }}
      </button>
      <input
        v-if="editor.isEditable"
        v-model="title"
        type="text"
        class="code-snippet-title"
        placeholder="Название блока"
        @mousedown="stopBubble"
        @click="stopBubble"
        @keydown="stopBubble"
      />
      <span v-else class="code-snippet-title-read">{{ title.trim() || codeSnippetLanguageLabel(language) }}</span>
      <div class="code-snippet-head-spacer" />
      <label v-if="editor.isEditable" class="code-snippet-lang-wrap" @mousedown="stopBubble">
        <span class="code-snippet-lang-lab">Язык</span>
        <select v-model="language" class="code-snippet-lang" @click="stopBubble" @keydown="stopBubble">
          <option value="sql">SQL</option>
          <option value="python">Python</option>
        </select>
      </label>
      <span v-else class="code-snippet-lang-read">{{ codeSnippetLanguageLabel(language) }}</span>
      <button
        v-if="editor.isEditable && language === 'sql'"
        type="button"
        class="code-snippet-btn"
        :disabled="!code.trim() || formatting"
        title="Отформатировать SQL: переносы полей, JOIN, WHERE, отступы"
        @click="formatSql"
      >
        Форматировать SQL
      </button>
      <button
        v-if="editor.isEditable && language === 'python'"
        type="button"
        class="code-snippet-btn"
        :disabled="!code.trim() || formatting"
        title="Отформатировать Python (Ruff / PEP 8: отступы, кавычки, переносы строк)"
        @click="formatPython"
      >
        {{ formatting ? 'Форматирование…' : 'Форматировать Python' }}
      </button>
      <button
        type="button"
        class="code-snippet-btn"
        :disabled="!code.trim()"
        :title="code.trim() ? 'Скопировать код' : 'Нет кода для копирования'"
        @click="copyCode"
      >
        {{ copyDone ? 'Скопировано' : 'Копировать' }}
      </button>
      <button v-if="editor.isEditable" type="button" class="code-snippet-btn" @click="deleteNode">Удалить</button>
    </div>
    <p v-if="formatErr" class="code-snippet-err">{{ formatErr }}</p>
    <div v-show="expanded" class="code-snippet-body">
      <div ref="cmHostRef" class="code-snippet-cm" @mousedown="stopBubble" @click="stopBubble" />
    </div>
  </NodeViewWrapper>
</template>

<style scoped>
.code-snippet-node {
  border: 1px solid var(--border);
  border-radius: 8px;
  margin: 0.5rem 0;
  overflow: hidden;
  background: #f1f5f9;
}
.code-snippet-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.45rem 0.65rem;
  padding: 0.5rem 0.65rem;
  border-bottom: 1px solid var(--border);
  font-size: 0.78rem;
  background: var(--panel);
}
.code-snippet-head-spacer {
  flex: 1;
  min-width: 0.5rem;
}
.code-snippet-btn {
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg);
  cursor: pointer;
  font: inherit;
  white-space: nowrap;
}
.code-snippet-btn:hover:not(:disabled) {
  border-color: var(--accent);
}
.code-snippet-btn:disabled {
  opacity: 0.45;
  cursor: default;
}
.code-snippet-btn-main {
  font-weight: 600;
}
.code-snippet-title {
  min-width: 6rem;
  max-width: 14rem;
  padding: 0.2rem 0.45rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg);
  font: inherit;
}
.code-snippet-title-read {
  font-weight: 600;
  color: var(--text, inherit);
}
.code-snippet-lang-wrap {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}
.code-snippet-lang-lab {
  color: var(--muted, #64748b);
  font-size: 0.72rem;
}
.code-snippet-lang {
  padding: 0.2rem 0.35rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg);
  font: inherit;
  cursor: pointer;
}
.code-snippet-lang-read {
  font-size: 0.72rem;
  color: var(--muted, #64748b);
}
.code-snippet-err {
  margin: 0;
  padding: 0.35rem 0.65rem 0;
  font-size: 0.72rem;
  color: #b91c1c;
}
.code-snippet-body {
  padding: 0.55rem 0.65rem 0.65rem;
}
.code-snippet-cm {
  border: 1px solid rgba(148, 163, 184, 0.55);
  border-radius: 6px;
  overflow: hidden;
  background: #fff;
}
.code-snippet-cm :deep(.cm-editor) {
  min-height: 7rem;
}
.code-snippet-cm :deep(.cm-editor.cm-focused) {
  border-radius: 6px;
}
</style>
