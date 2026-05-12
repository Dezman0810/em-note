<script setup lang="ts">
import { nodeViewProps, NodeViewWrapper } from '@tiptap/vue-3'
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue'
import { createRoot } from 'react-dom/client'
import * as React from 'react'
import { ExcalidrawApp } from './ExcalidrawApp'

const props = defineProps(nodeViewProps)

/** Состояние свёрнутости хранится в attrs.collapsed (сохраняется в content_json). */
function expandedFromAttrs(): boolean {
  return props.node.attrs.collapsed !== true
}

const expanded = ref(expandedFromAttrs())

watch(
  () => props.node.attrs.collapsed,
  () => {
    expanded.value = expandedFromAttrs()
  }
)
const hostRef = ref<HTMLDivElement | null>(null)
const fullscreenShellRef = ref<HTMLElement | null>(null)
/** Нативный Fullscreen API для оболочки схемы (без fallback fixed). */
const shellInNativeFullscreen = ref(false)
const fullscreenFallback = ref(false)
const sceneKey = ref(0)
let reactRoot: ReturnType<typeof createRoot> | null = null

/** Почти на весь экран в окне браузера: перекрывает и шапку приложения (поиск, админка). */
const noteWideUi = ref(false)
const noteWideInset = reactive({ top: 0, left: 0, width: 0, height: 0 })

const noteWideShellStyle = computed(() => {
  if (!noteWideUi.value) return {} as Record<string, string>
  const n = noteWideInset
  return {
    top: `${n.top}px`,
    left: `${n.left}px`,
    width: `${n.width}px`,
    height: `${n.height}px`,
  }
})

function updateNoteWideInset() {
  if (!noteWideUi.value) return
  const vv = typeof window !== 'undefined' ? window.visualViewport : null
  if (vv) {
    noteWideInset.top = vv.offsetTop
    noteWideInset.left = vv.offsetLeft
    noteWideInset.width = vv.width
    noteWideInset.height = vv.height
    return
  }
  const d = document.documentElement
  noteWideInset.top = 0
  noteWideInset.left = 0
  noteWideInset.width = d.clientWidth
  noteWideInset.height = d.clientHeight
}

function teardownNoteWideLayout() {
  if (typeof window === 'undefined') return
  window.removeEventListener('resize', updateNoteWideInset)
  window.removeEventListener('scroll', updateNoteWideInset, true)
  const vv = window.visualViewport
  if (vv) {
    vv.removeEventListener('resize', updateNoteWideInset)
    vv.removeEventListener('scroll', updateNoteWideInset)
  }
}

function setupNoteWideLayout() {
  teardownNoteWideLayout()
  if (!noteWideUi.value || typeof window === 'undefined') return
  const vv = window.visualViewport
  if (vv) {
    vv.addEventListener('resize', updateNoteWideInset)
    vv.addEventListener('scroll', updateNoteWideInset)
  }
  window.addEventListener('resize', updateNoteWideInset)
  window.addEventListener('scroll', updateNoteWideInset, true)
  updateNoteWideInset()
}

/** Верхняя панель с «На всю рабочую область» / «На весь экран» скрыта в режиме полного экрана схемы (выход — Esc или системная кнопка браузера). */
const hideExcTopBarWhileFullscreen = computed(
  () => fullscreenFallback.value || shellInNativeFullscreen.value
)

function syncShellNativeFullscreenFlag() {
  const el = fullscreenShellRef.value
  shellInNativeFullscreen.value = !!(el && document.fullscreenElement === el)
}

const scene = computed(() => (props.node.attrs.scene as string) || '{}')

const excalReadOnly = computed(() => !props.editor.isEditable)

/** Последняя сцена, отправленная из Excalidraw (debounce). Нужна, чтобы не путать с обновлением с сервера / setContent. */
const lastEmittedScene = ref<string | null>(null)

function normalizeSceneJson(s: string): string {
  try {
    return JSON.stringify(JSON.parse(s || '{}'))
  } catch {
    return s
  }
}

function onSceneDebounced(json: string) {
  if (!props.editor.isEditable) return
  lastEmittedScene.value = json
  props.updateAttributes({ scene: json })
}

/** Синхронизация схемы с документом (другая вкладка, публичная ссылка, refetch заметки). */
watch(
  scene,
  (newScene) => {
    if (lastEmittedScene.value === null) {
      lastEmittedScene.value = newScene
      return
    }
    if (normalizeSceneJson(newScene) === normalizeSceneJson(lastEmittedScene.value)) return
    lastEmittedScene.value = newScene
    sceneKey.value++
  },
  { immediate: true }
)

function mountReact() {
  if (!hostRef.value) return
  if (reactRoot) {
    reactRoot.unmount()
    reactRoot = null
  }
  reactRoot = createRoot(hostRef.value)
  reactRoot.render(
    React.createElement(ExcalidrawApp, {
      sceneJson: scene.value,
      readOnly: excalReadOnly.value,
      sceneKey: sceneKey.value,
      onSceneDebounced,
    })
  )
}

function unmountReact() {
  if (reactRoot) {
    reactRoot.unmount()
    reactRoot = null
  }
}

watch(
  expanded,
  async (open) => {
    await nextTick()
    if (open) {
      mountReact()
    } else {
      unmountReact()
      noteWideUi.value = false
      teardownNoteWideLayout()
      shellInNativeFullscreen.value = false
      if (fullscreenShellRef.value && document.fullscreenElement === fullscreenShellRef.value) {
        void document.exitFullscreen()
      }
      fullscreenFallback.value = false
      document.body.style.overflow = ''
    }
  },
  { immediate: true }
)

watch(
  () => sceneKey.value,
  () => {
    if (expanded.value && hostRef.value) {
      mountReact()
    }
  }
)

watch(excalReadOnly, () => {
  if (expanded.value && hostRef.value) {
    mountReact()
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onExcalFullscreenEscape, true)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  teardownNoteWideLayout()
  unmountReact()
  shellInNativeFullscreen.value = false
  if (fullscreenShellRef.value && document.fullscreenElement === fullscreenShellRef.value) {
    void document.exitFullscreen()
  }
  fullscreenFallback.value = false
  document.body.style.overflow = ''
})

function isFullscreenUi() {
  const el = fullscreenShellRef.value
  if (!el) return false
  return document.fullscreenElement === el || fullscreenFallback.value
}

async function exitFullscreenIfNeeded() {
  const el = fullscreenShellRef.value
  if (!el) return
  if (document.fullscreenElement === el) {
    try {
      await document.exitFullscreen()
    } catch {
      /* ignore */
    }
  }
  fullscreenFallback.value = false
  shellInNativeFullscreen.value = false
  document.body.style.overflow = ''
}

watch(noteWideUi, async (on) => {
  if (typeof document === 'undefined') return
  if (on) {
    await exitFullscreenIfNeeded()
    document.body.style.overflow = 'hidden'
    await nextTick()
    setupNoteWideLayout()
    return
  }
  teardownNoteWideLayout()
  document.body.style.overflow = ''
})

function toggleNoteWide() {
  noteWideUi.value = !noteWideUi.value
}

async function toggleFullscreen() {
  const el = fullscreenShellRef.value
  if (!el) return
  if (isFullscreenUi()) {
    await exitFullscreenIfNeeded()
    return
  }
  if (noteWideUi.value) {
    noteWideUi.value = false
  }
  if (typeof el.requestFullscreen === 'function') {
    try {
      await el.requestFullscreen()
      syncShellNativeFullscreenFlag()
    } catch {
      fullscreenFallback.value = true
      document.body.style.overflow = 'hidden'
    }
  } else {
    fullscreenFallback.value = true
    document.body.style.overflow = 'hidden'
  }
}

function onFullscreenChange() {
  const el = fullscreenShellRef.value
  if (!el) return
  syncShellNativeFullscreenFlag()
  if (document.fullscreenElement !== el) {
    fullscreenFallback.value = false
    document.body.style.overflow = ''
  }
}

function onExcalFullscreenEscape(ev: KeyboardEvent) {
  if (ev.key !== 'Escape') return
  const el = fullscreenShellRef.value
  if (!el) return
  const inOurFullscreen =
    fullscreenFallback.value ||
    shellInNativeFullscreen.value ||
    document.fullscreenElement === el
  if (!inOurFullscreen) return
  ev.stopPropagation()
  void exitFullscreenIfNeeded()
}

onMounted(() => {
  document.addEventListener('fullscreenchange', onFullscreenChange)
  window.addEventListener('keydown', onExcalFullscreenEscape, true)
  syncShellNativeFullscreenFlag()
})

function toggle() {
  const next = !expanded.value
  expanded.value = next
  props.updateAttributes({ collapsed: !next })
}

function onImportFile(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    const text = String(reader.result || '')
    try {
      JSON.parse(text)
      lastEmittedScene.value = text
      props.updateAttributes({ scene: text })
      sceneKey.value++
      if (!expanded.value) expanded.value = true
      else void nextTick(() => mountReact())
    } catch {
      /* ignore */
    }
  }
  reader.readAsText(file, 'utf-8')
}
</script>

<template>
  <NodeViewWrapper class="excalidraw-node" :class="{ 'excalidraw-node--note-wide': noteWideUi }">
    <div class="excalidraw-node-head">
      <button type="button" class="excal-toggle excal-toggle-main" @click="toggle">
        {{ expanded ? '▼ Свернуть' : '▶ Схема' }}
      </button>
      <label v-if="editor.isEditable" class="excal-import">
        <input type="file" accept=".excalidraw,application/json" class="visually-hidden" @change="onImportFile" />
        <span class="excal-import-btn">Импорт</span>
      </label>
      <button v-if="editor.isEditable" type="button" class="excal-toggle" @click="deleteNode">Удалить блок</button>
    </div>
    <div
      v-show="expanded"
      ref="fullscreenShellRef"
      class="excal-fullscreen-shell"
      :class="{
        'excal-fullscreen-shell--fallback': fullscreenFallback && !noteWideUi,
        'excal-fullscreen-shell--note-wide': noteWideUi,
      }"
      :style="noteWideShellStyle"
    >
      <div v-show="!hideExcTopBarWhileFullscreen" class="excal-innerbar">
        <div class="excal-innerbar-spacer" />
        <button
          type="button"
          class="excal-fs-btn"
          title="Почти во весь экран в окне браузера (вместе со шапкой приложения — поиск, админка). Не браузерный F11 и не режим только схемы."
          @click="toggleNoteWide"
        >
          {{ noteWideUi ? 'Свернуть рабочую область' : 'На всю рабочую область' }}
        </button>
        <button
          type="button"
          class="excal-fs-btn"
          title="Только схема на весь экран; верхняя панель скрыта. Выход — Esc"
          @click="toggleFullscreen"
        >
          На весь экран
        </button>
      </div>
      <div ref="hostRef" class="excal-host" />
    </div>
  </NodeViewWrapper>
</template>

<style scoped>
.excalidraw-node {
  border: 1px solid var(--border);
  border-radius: 8px;
  margin: 0.5rem 0;
  overflow: hidden;
  background: var(--panel);
}
.excalidraw-node-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
  padding: 0.5rem 0.65rem;
  border-bottom: 1px solid var(--border);
  font-size: 0.78rem;
}
.excal-toggle {
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg);
  cursor: pointer;
  font: inherit;
}
.excal-toggle:hover {
  border-color: var(--accent);
}
.excal-toggle-main {
  font-weight: 600;
}
.excal-fullscreen-shell {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--panel);
}
.excal-fullscreen-shell:fullscreen {
  background: var(--panel);
}
.excalidraw-node--note-wide {
  overflow: visible !important;
  position: relative;
  z-index: 9999;
}
.excal-fullscreen-shell--fallback {
  position: fixed;
  inset: 0;
  z-index: 10000;
  box-shadow: 0 0 0 9999px rgba(15, 23, 42, 0.45);
}
.excal-fullscreen-shell--note-wide {
  position: fixed;
  z-index: 10000;
  max-height: none !important;
  margin: 0;
  flex: unset;
  box-shadow: 0 0 0 9999px rgba(15, 23, 42, 0.28);
  border-radius: 0;
}
.excal-innerbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: 0.35rem 0.5rem;
  border-bottom: 1px solid var(--border);
  gap: 0.5rem;
  flex-shrink: 0;
}
.excal-innerbar-spacer {
  flex: 1;
  min-width: 0.5rem;
}
.excal-fs-btn {
  padding: 0.28rem 0.55rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg);
  cursor: pointer;
  font: inherit;
  font-size: 0.76rem;
  font-weight: 600;
}
.excal-fs-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.excal-host :deep(.excal-embed-footer-actions) {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.45rem;
}
.excal-host :deep(.excal-scroll-schema-btn) {
  padding: 0.32rem 0.65rem;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.55);
  background: #fff;
  color: #1e293b;
  cursor: pointer;
  font: inherit;
  font-size: 0.74rem;
  font-weight: 500;
  white-space: nowrap;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
.excal-host :deep(.excal-scroll-schema-btn:hover) {
  border-color: rgba(100, 116, 139, 0.65);
  background: #f8fafc;
}

.excal-import {
  cursor: pointer;
}
.excal-import-btn {
  cursor: pointer;
  color: var(--accent);
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
  border: 0;
}
.excal-host {
  height: min(598px, 80.5vh);
  min-height: 322px;
}
.excal-fullscreen-shell--note-wide .excal-host {
  flex: 1;
  min-height: 0;
  height: auto;
  max-height: none;
}
.excal-fullscreen-shell:fullscreen .excal-host,
.excal-fullscreen-shell--fallback .excal-host {
  flex: 1;
  min-height: 0;
  height: auto;
  max-height: none;
}

/* Третья «кнопка» в подвале: скругления как у зума/undo (три иконки в одном островке). */
.excal-host :deep(.excal-embed-clipboard .excal-clip-footer-btn--first .ToolIcon_type_button) {
  border-top-left-radius: var(--border-radius-lg) !important;
  border-bottom-left-radius: var(--border-radius-lg) !important;
  border-right: 0 !important;
}
.excal-host :deep(.excal-embed-clipboard .excal-clip-footer-btn--mid .ToolIcon_type_button) {
  border-radius: 0 !important;
  border-right: 0 !important;
}
.excal-host :deep(.excal-embed-clipboard .excal-clip-footer-btn--last .ToolIcon_type_button) {
  border-top-right-radius: var(--border-radius-lg) !important;
  border-bottom-right-radius: var(--border-radius-lg) !important;
}

/* Справка «?»: в 0.18 иконка с классом .help-icon; прячем и обёртку ToolIcon */
.excal-host :deep(.excalidraw .ToolIcon:has(.help-icon)),
.excal-host :deep(.excalidraw .help-icon),
.excal-host :deep(.excalidraw .welcome-screen-decor--help),
.excal-host :deep(.excalidraw .welcome-screen-decor-hint--help) {
  display: none !important;
}

/* Скрыть Library в схеме (в @excalidraw/excalidraw 0.18 нет опции в UIOptions). */
.excal-host :deep(.excalidraw .sidebar-trigger),
.excal-host :deep(.excalidraw .default-sidebar-trigger) {
  display: none !important;
}
.excal-host :deep(.excalidraw .App-toolbar .App-toolbar__divider:last-of-type) {
  display: none !important;
}
</style>
