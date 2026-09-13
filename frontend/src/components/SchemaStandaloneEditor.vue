<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import type { Root } from 'react-dom/client'

const props = defineProps<{
  scene: string
  readOnly: boolean
}>()

const emit = defineEmits<{
  change: [scene: string]
}>()

const hostRef = ref<HTMLDivElement | null>(null)
const fullscreenShellRef = ref<HTMLElement | null>(null)
const shellInNativeFullscreen = ref(false)
const fullscreenFallback = ref(false)
const noteWideUi = ref(false)
const noteWideInset = reactive({ top: 0, left: 0, width: 0, height: 0 })
const sceneKey = ref(0)
let reactRoot: Root | null = null
let mountGen = 0
const lastEmittedScene = ref<string | null>(null)

const hideExcTopBarWhileFullscreen = computed(
  () => fullscreenFallback.value || shellInNativeFullscreen.value
)

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

function syncShellNativeFullscreenFlag() {
  const el = fullscreenShellRef.value
  shellInNativeFullscreen.value = !!(el && document.fullscreenElement === el)
}

function normalizeSceneJson(s: string): string {
  try {
    return JSON.stringify(JSON.parse(s || '{}'))
  } catch {
    return s
  }
}

function onSceneDebounced(json: string) {
  if (props.readOnly) return
  lastEmittedScene.value = json
  emit('change', json)
}

async function mountReact() {
  if (!hostRef.value) return
  const gen = ++mountGen
  const [{ createRoot }, React, { ExcalidrawApp }] = await Promise.all([
    import('react-dom/client'),
    import('react'),
    import('./tiptap/ExcalidrawApp'),
  ])
  if (gen !== mountGen || !hostRef.value) return
  if (reactRoot) {
    reactRoot.unmount()
    reactRoot = null
  }
  reactRoot = createRoot(hostRef.value)
  reactRoot.render(
    React.createElement(ExcalidrawApp, {
      sceneJson: props.scene,
      readOnly: props.readOnly,
      sceneKey: sceneKey.value,
      onSceneDebounced,
    })
  )
}

function unmountReact() {
  mountGen++
  if (reactRoot) {
    reactRoot.unmount()
    reactRoot = null
  }
}

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
  if (noteWideUi.value) noteWideUi.value = false
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

watch(
  () => props.scene,
  (newScene) => {
    if (lastEmittedScene.value === null) {
      lastEmittedScene.value = newScene
      return
    }
    if (normalizeSceneJson(newScene) === normalizeSceneJson(lastEmittedScene.value)) return
    lastEmittedScene.value = newScene
    sceneKey.value++
    void mountReact()
  }
)

watch(
  () => props.readOnly,
  () => {
    void mountReact()
  }
)

watch(
  () => sceneKey.value,
  () => {
    if (hostRef.value) void mountReact()
  }
)

onMounted(() => {
  lastEmittedScene.value = props.scene
  document.addEventListener('fullscreenchange', onFullscreenChange)
  window.addEventListener('keydown', onExcalFullscreenEscape, true)
  syncShellNativeFullscreenFlag()
  void mountReact()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onExcalFullscreenEscape, true)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  teardownNoteWideLayout()
  unmountReact()
  noteWideUi.value = false
  if (fullscreenShellRef.value && document.fullscreenElement === fullscreenShellRef.value) {
    void document.exitFullscreen()
  }
  fullscreenFallback.value = false
  document.body.style.overflow = ''
})
</script>

<template>
  <div class="schema-standalone" :class="{ 'schema-standalone--note-wide': noteWideUi }">
    <div
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
          title="Почти во весь экран в окне браузера. Не браузерный F11."
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
  </div>
</template>

<style scoped>
.schema-standalone {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--panel);
}
.schema-standalone--note-wide {
  overflow: visible;
  position: relative;
  z-index: 9999;
}
.excal-fullscreen-shell {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--panel);
}
.excal-fullscreen-shell:fullscreen {
  background: var(--panel);
}
.excal-fullscreen-shell--fallback {
  position: fixed;
  inset: 0;
  z-index: 10000;
  box-shadow: 0 0 0 9999px var(--shadow-tint-strong);
}
.excal-fullscreen-shell--note-wide {
  position: fixed;
  z-index: 10000;
  max-height: none !important;
  margin: 0;
  flex: unset;
  box-shadow: 0 0 0 9999px var(--shadow-tint-strong);
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
  font-size: var(--fs-2xs);
  font-weight: 600;
}
.excal-fs-btn:hover {
  border-color: var(--accent);
  color: var(--accent-text);
}
.excal-host {
  flex: 1 1 auto;
  min-height: 0;
  height: auto;
}
.excal-fullscreen-shell--note-wide .excal-host,
.excal-fullscreen-shell:fullscreen .excal-host,
.excal-fullscreen-shell--fallback .excal-host {
  flex: 1;
  min-height: 0;
  height: auto;
  max-height: none;
}
.excal-host :deep(.excalidraw .ToolIcon:has(.help-icon)),
.excal-host :deep(.excalidraw .help-icon),
.excal-host :deep(.excalidraw .welcome-screen-decor--help),
.excal-host :deep(.excalidraw .welcome-screen-decor-hint--help),
.excal-host :deep(.excalidraw .sidebar-trigger),
.excal-host :deep(.excalidraw .default-sidebar-trigger) {
  display: none !important;
}
</style>
