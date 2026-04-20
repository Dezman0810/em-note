<script setup lang="ts">
import { nodeViewProps, NodeViewWrapper } from '@tiptap/vue-3'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { createRoot } from 'react-dom/client'
import * as React from 'react'
import { ExcalidrawApp } from './ExcalidrawApp'

const props = defineProps(nodeViewProps)

/** По умолчанию развёрнуто, чтобы сразу видеть схему. */
const expanded = ref(true)
const hostRef = ref<HTMLDivElement | null>(null)
const fullscreenShellRef = ref<HTMLElement | null>(null)
const fullscreenFallback = ref(false)
const sceneKey = ref(0)
let reactRoot: ReturnType<typeof createRoot> | null = null

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
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  unmountReact()
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

async function toggleFullscreen() {
  const el = fullscreenShellRef.value
  if (!el) return
  if (isFullscreenUi()) {
    if (document.fullscreenElement === el) {
      try {
        await document.exitFullscreen()
      } catch {
        /* ignore */
      }
    }
    fullscreenFallback.value = false
    document.body.style.overflow = ''
    return
  }
  if (typeof el.requestFullscreen === 'function') {
    try {
      await el.requestFullscreen()
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
  if (document.fullscreenElement !== el) {
    fullscreenFallback.value = false
    document.body.style.overflow = ''
  }
}

onMounted(() => {
  document.addEventListener('fullscreenchange', onFullscreenChange)
})

function toggle() {
  expanded.value = !expanded.value
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
  <NodeViewWrapper class="excalidraw-node">
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
      :class="{ 'excal-fullscreen-shell--fallback': fullscreenFallback }"
    >
      <div class="excal-innerbar">
        <button type="button" class="excal-fs-btn" @click="toggleFullscreen">
          {{ isFullscreenUi() ? 'Выйти из полноэкранного' : 'На весь экран' }}
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
.excal-fullscreen-shell--fallback {
  position: fixed;
  inset: 0;
  z-index: 10000;
  box-shadow: 0 0 0 9999px rgba(15, 23, 42, 0.45);
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
  height: min(520px, 70vh);
  min-height: 280px;
}
.excal-fullscreen-shell:fullscreen .excal-host,
.excal-fullscreen-shell--fallback .excal-host {
  flex: 1;
  min-height: 0;
  height: auto;
  max-height: none;
}
</style>
