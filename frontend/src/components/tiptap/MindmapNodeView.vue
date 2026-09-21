<script setup lang="ts">
import { nodeViewProps, NodeViewWrapper } from '@tiptap/vue-3'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import BlockTitleField from '../BlockTitleField.vue'
import { parseMindmapScene, stringifyMindmapScene } from './mindmapDefaultScene'
import { useAuthStore } from '../../stores/auth'
import { downloadTextFile, safeDownloadBaseName } from '../../utils/downloadTextFile'
import { primeMindmapOnIntent } from '../../utils/mindmapWarmup'

const props = defineProps(nodeViewProps)

const auth = useAuthStore()
const canExport = computed(() => !!auth.user?.can_export_mindmaps)

const PLACEHOLDER_ROOT = new Set(['главная', 'центр', 'root', 'central topic'])

const blockTitle = computed(() => {
  const raw = props.node.attrs.title
  if (typeof raw === 'string' && raw.trim()) return raw.trim()
  try {
    const text = String(parseMindmapScene(String(props.node.attrs.scene || '{}')).root?.data?.text || '')
      .replace(/<[^>]+>/g, ' ')
      .replace(/&nbsp;/gi, ' ')
      .replace(/\s+/g, ' ')
      .trim()
    if (text && !PLACEHOLDER_ROOT.has(text.toLowerCase())) return text.slice(0, 80)
  } catch {
    /* */
  }
  return 'Карта'
})

function saveBlockTitle(next: string) {
  if (!props.editor.isEditable) return
  props.updateAttributes({ title: next })
}

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

const scene = computed(() => (props.node.attrs.scene as string) || '{}')
const frameRef = ref<HTMLIFrameElement | null>(null)
const fullscreenShellRef = ref<HTMLElement | null>(null)
const shellInNativeFullscreen = ref(false)
const noteWideUi = ref(false)
const noteWideInset = reactive({ top: 0, left: 0, width: 0, height: 0 })
const lastEmittedScene = ref<string | null>(null)

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
const frameKey = ref(0)
const frameRequested = ref(expandedFromAttrs())
let saveTimer: ReturnType<typeof setTimeout> | null = null
let initSent = false

function primeFrame() {
  if (!frameRequested.value) frameRequested.value = true
  primeMindmapOnIntent()
}

watch(
  expanded,
  (open) => {
    if (open) frameRequested.value = true
  },
  { immediate: true }
)

const frameSrc = computed(() => {
  const id = typeof props.node.attrs.blockId === 'string' ? props.node.attrs.blockId : 'map'
  return `/mindmap-app/embed.html?v=logical21&id=${encodeURIComponent(id)}`
})

function normalizeSceneJson(s: string): string {
  try {
    return JSON.stringify(JSON.parse(s || '{}'))
  } catch {
    return s
  }
}

function postInit(ev?: Event) {
  const fromEvent = ev?.target instanceof HTMLIFrameElement ? ev.target.contentWindow : null
  const win = fromEvent || frameRef.value?.contentWindow
  if (!win || initSent) return
  initSent = true
  win.postMessage(
    {
      type: 'em-note-mindmap-init',
      data: parseMindmapScene(scene.value),
      readonly: !props.editor.isEditable,
    },
    '*'
  )
}

function onSceneDebounced(json: string) {
  if (!props.editor.isEditable) return
  lastEmittedScene.value = json
  props.updateAttributes({ scene: json })
}

function onFrameMessage(ev: MessageEvent) {
  const frameWin = frameRef.value?.contentWindow
  if (!frameWin || ev.source !== frameWin) return
  try {
    if (ev.origin && ev.origin !== 'null' && new URL(ev.origin).hostname !== window.location.hostname) return
  } catch {
    return
  }
  const msg = ev.data
  if (!msg || typeof msg !== 'object') return
  if (msg.type === 'em-note-mindmap-ready') {
    postInit()
    return
  }
  if (msg.type !== 'em-note-mindmap-save' || !props.editor.isEditable) return
  const json = stringifyMindmapScene(msg.data ?? {})
  if (normalizeSceneJson(json) === normalizeSceneJson(lastEmittedScene.value || scene.value)) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveTimer = null
    onSceneDebounced(json)
  }, 400)
}

watch(scene, (newScene) => {
  if (lastEmittedScene.value === null) {
    lastEmittedScene.value = newScene
    return
  }
  if (normalizeSceneJson(newScene) === normalizeSceneJson(lastEmittedScene.value)) return
  lastEmittedScene.value = newScene
  initSent = false
  frameKey.value++
})

watch(
  () => props.editor.isEditable,
  () => {
    initSent = false
    frameKey.value++
  }
)

function syncShellNativeFullscreenFlag() {
  const el = fullscreenShellRef.value
  shellInNativeFullscreen.value = !!(el && document.fullscreenElement === el)
}

function onFullscreenChange() {
  syncShellNativeFullscreenFlag()
}

watch(noteWideUi, async (on) => {
  if (typeof document === 'undefined') return
  if (on) {
    const el = fullscreenShellRef.value
    if (el && document.fullscreenElement === el) {
      try {
        await document.exitFullscreen()
      } catch {
        /* */
      }
    }
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
  if (document.fullscreenElement === el) {
    await document.exitFullscreen()
    return
  }
  if (noteWideUi.value) noteWideUi.value = false
  await el.requestFullscreen()
}

function toggle() {
  const next = !expanded.value
  if (next) primeFrame()
  expanded.value = next
  if (!props.editor.isEditable) return
  props.updateAttributes({ collapsed: !next })
}

function onImportFile(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !props.editor.isEditable) return
  const reader = new FileReader()
  reader.onload = () => {
    const text = String(reader.result || '')
    try {
      const json = stringifyMindmapScene(JSON.parse(text))
      lastEmittedScene.value = json
      props.updateAttributes({ scene: json })
      initSent = false
      frameKey.value++
      if (!expanded.value) {
        primeFrame()
        expanded.value = true
      }
    } catch {
      /* ignore */
    }
  }
  reader.readAsText(file, 'utf-8')
}

function exportSceneFile() {
  const title = safeDownloadBaseName(blockTitle.value, 'map')
  downloadTextFile(`${title}.json`, stringifyMindmapScene(scene.value), 'application/json')
}

function reloadBlock() {
  initSent = false
  lastEmittedScene.value = scene.value
  frameKey.value++
  frameRequested.value = true
  primeMindmapOnIntent()
  if (!expanded.value) {
    expanded.value = true
    if (props.editor.isEditable) props.updateAttributes({ collapsed: false })
  }
}

onMounted(() => {
  window.addEventListener('message', onFrameMessage)
  document.addEventListener('fullscreenchange', onFullscreenChange)
})

onBeforeUnmount(() => {
  window.removeEventListener('message', onFrameMessage)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  teardownNoteWideLayout()
  noteWideUi.value = false
  document.body.style.overflow = ''
  if (saveTimer) clearTimeout(saveTimer)
})
</script>

<template>
  <NodeViewWrapper class="mindmap-node" :class="{ 'mindmap-node--note-wide': noteWideUi }">
    <div class="mindmap-node-head">
      <button
        type="button"
        class="mindmap-toggle mindmap-toggle-main"
        @mouseenter="primeFrame"
        @focus="primeFrame"
        @click="toggle"
      >
        {{ expanded ? '▼ Карта' : '▶ Карта' }}
      </button>
      <BlockTitleField
        :model-value="blockTitle"
        :disabled="!editor.isEditable"
        placeholder="Карта"
        aria-label="Название карты"
        @save="saveBlockTitle"
      />
      <label v-if="editor.isEditable" class="mindmap-import">
        <input type="file" accept=".json,.smm,application/json" class="visually-hidden" @change="onImportFile" />
        <span class="mindmap-import-btn">Импорт</span>
      </label>
      <button v-if="canExport" type="button" class="mindmap-import-btn" @click="exportSceneFile">Экспорт</button>
      <button
        v-if="editor.isEditable"
        type="button"
        class="mindmap-toggle"
        title="Перезагрузить карту, если загрузка зависла"
        @click="reloadBlock"
      >
        Обновить
      </button>
      <button v-if="editor.isEditable" type="button" class="mindmap-toggle" @click="deleteNode">Удалить блок</button>
    </div>
    <div
      v-if="frameRequested"
      ref="fullscreenShellRef"
      class="mindmap-fullscreen-shell"
      :class="{
        'mindmap-fullscreen-shell--note-wide': noteWideUi,
        'mindmap-fullscreen-shell--preloading': !expanded,
      }"
      :style="noteWideShellStyle"
    >
      <div v-show="expanded && !shellInNativeFullscreen" class="mindmap-innerbar">
        <span v-if="!editor.isEditable" class="mindmap-readonly-hint">Только просмотр</span>
        <div class="mindmap-innerbar-spacer" />
        <button
          type="button"
          class="mindmap-fs-btn"
          title="Почти во весь экран в окне браузера. Не браузерный F11."
          @click="toggleNoteWide"
        >
          {{ noteWideUi ? 'Свернуть рабочую область' : 'На всю рабочую область' }}
        </button>
        <button type="button" class="mindmap-fs-btn" title="Карта на весь экран. Выход — Esc" @click="toggleFullscreen">
          На весь экран
        </button>
      </div>
      <iframe
        :key="frameKey"
        ref="frameRef"
        class="mindmap-host"
        data-mindmap-frame
        :src="frameSrc"
        title="Интеллект-карта"
        @load="postInit"
      />
    </div>
  </NodeViewWrapper>
</template>

<style scoped>
.mindmap-node {
  border: 1px solid var(--border);
  border-radius: 8px;
  margin: 0.5rem 0;
  overflow: hidden;
  background: var(--panel);
}
.mindmap-node-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
  padding: 0.5rem 0.65rem;
  border-bottom: 1px solid var(--border);
  font-size: var(--fs-xs);
}
.mindmap-toggle {
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg);
  cursor: pointer;
  font: inherit;
}
.mindmap-toggle:hover {
  border-color: var(--accent);
}
.mindmap-toggle-main {
  font-weight: 600;
}
.mindmap-import {
  cursor: pointer;
}
.mindmap-import-btn {
  cursor: pointer;
  color: var(--accent-text);
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
.mindmap-fullscreen-shell {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--panel);
}
.mindmap-fullscreen-shell:fullscreen {
  background: var(--panel);
}
.mindmap-node--note-wide {
  overflow: visible !important;
  position: relative;
  z-index: 9999;
}
.mindmap-fullscreen-shell--note-wide {
  position: fixed;
  z-index: 10000;
  max-height: none !important;
  margin: 0;
  flex: unset;
  display: flex;
  flex-direction: column;
  box-shadow: 0 0 0 9999px var(--shadow-tint-strong);
  border-radius: 0;
}
.mindmap-fullscreen-shell--preloading {
  position: absolute !important;
  width: 0 !important;
  height: 0 !important;
  min-height: 0 !important;
  overflow: hidden !important;
  opacity: 0 !important;
  pointer-events: none !important;
  visibility: hidden !important;
  border: 0 !important;
  margin: 0 !important;
}
.mindmap-innerbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: 0.35rem 0.5rem;
  border-bottom: 1px solid var(--border);
  gap: 0.5rem;
  flex-shrink: 0;
}
.mindmap-innerbar-spacer {
  flex: 1;
  min-width: 0.5rem;
}
.mindmap-readonly-hint {
  color: var(--muted, #888);
  font-size: var(--fs-2xs);
  font-weight: 600;
}
.mindmap-fs-btn {
  padding: 0.28rem 0.55rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg);
  cursor: pointer;
  font: inherit;
  font-size: var(--fs-2xs);
  font-weight: 600;
}
.mindmap-fs-btn:hover {
  border-color: var(--accent);
  color: var(--accent-text);
}
.mindmap-host {
  display: block;
  width: 100%;
  height: min(598px, 80.5vh);
  min-height: 360px;
  border: 0;
  background: #fff;
}
.mindmap-fullscreen-shell:fullscreen .mindmap-host,
.mindmap-fullscreen-shell--note-wide .mindmap-host {
  flex: 1;
  min-height: 0;
  height: auto;
  max-height: none;
}
</style>
