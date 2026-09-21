<script setup lang="ts">
import { nodeViewProps, NodeViewWrapper } from '@tiptap/vue-3'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import BlockTitleField from '../BlockTitleField.vue'
import {
  diagramNameFromXml,
  normalizeDrawioXml,
  parseDrawioScene,
  stringifyDrawioScene,
} from './drawioDefaultScene'
import { useAuthStore } from '../../stores/auth'
import { downloadTextFile, safeDownloadBaseName } from '../../utils/downloadTextFile'

const props = defineProps(nodeViewProps)

const auth = useAuthStore()
const canExport = computed(() => !!auth.user?.can_export_diagrams)

const PLACEHOLDER_NAMES = new Set(['страница-1', 'page-1', 'diagram'])

const blockTitle = computed(() => {
  const raw = props.node.attrs.title
  if (typeof raw === 'string' && raw.trim()) return raw.trim()
  const fromXml = diagramNameFromXml(String(props.node.attrs.scene || ''))
  if (fromXml && !PLACEHOLDER_NAMES.has(fromXml.toLowerCase())) return fromXml.slice(0, 80)
  return 'Диаграмма'
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

const scene = computed(() => (props.node.attrs.scene as string) || '')
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
let saveTimer: ReturnType<typeof setTimeout> | null = null
let initSent = false

const frameSrc = computed(() => {
  const id = typeof props.node.attrs.blockId === 'string' ? props.node.attrs.blockId : 'map'
  return `/drawio-app/embed.html?v=ru1&id=${encodeURIComponent(id)}`
})

function normalizeSceneXml(s: string): string {
  return normalizeDrawioXml(s)
}

function postInit(ev?: Event) {
  const fromEvent = ev?.target instanceof HTMLIFrameElement ? ev.target.contentWindow : null
  const win = fromEvent || frameRef.value?.contentWindow
  if (!win || initSent) return
  initSent = true
  win.postMessage(
    {
      type: 'em-note-drawio-init',
      xml: parseDrawioScene(scene.value),
      readonly: !props.editor.isEditable,
    },
    '*'
  )
}

function onSceneDebounced(xml: string) {
  if (!props.editor.isEditable) return
  lastEmittedScene.value = xml
  props.updateAttributes({ scene: xml })
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
  if (msg.type === 'em-note-drawio-ready') {
    postInit()
    return
  }
  if (msg.type !== 'em-note-drawio-save' || !props.editor.isEditable) return
  const xml = stringifyDrawioScene(typeof msg.xml === 'string' ? msg.xml : '')
  if (normalizeSceneXml(xml) === normalizeSceneXml(lastEmittedScene.value || scene.value)) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveTimer = null
    onSceneDebounced(xml)
  }, 400)
}

watch(scene, (newScene) => {
  if (lastEmittedScene.value === null) {
    lastEmittedScene.value = newScene
    return
  }
  if (normalizeSceneXml(newScene) === normalizeSceneXml(lastEmittedScene.value)) return
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
    if (text.includes('<mxfile') || text.includes('<mxGraphModel')) {
      const xml = stringifyDrawioScene(text)
      lastEmittedScene.value = xml
      props.updateAttributes({ scene: xml })
      initSent = false
      frameKey.value++
      if (!expanded.value) expanded.value = true
    }
  }
  reader.readAsText(file, 'utf-8')
}

function exportSceneFile() {
  const title = safeDownloadBaseName(blockTitle.value, 'diagram')
  downloadTextFile(
    `${title}.drawio`,
    stringifyDrawioScene(scene.value),
    'application/xml'
  )
}

function reloadBlock() {
  initSent = false
  lastEmittedScene.value = scene.value
  frameKey.value++
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
  <NodeViewWrapper class="drawio-node" :class="{ 'drawio-node--note-wide': noteWideUi }">
    <div class="drawio-node-head">
      <button type="button" class="drawio-toggle drawio-toggle-main" @click="toggle">
        {{ expanded ? '▼ Диаграмма' : '▶ Диаграмма' }}
      </button>
      <BlockTitleField
        :model-value="blockTitle"
        :disabled="!editor.isEditable"
        placeholder="Диаграмма"
        aria-label="Название диаграммы"
        @save="saveBlockTitle"
      />
      <label v-if="editor.isEditable" class="drawio-import">
        <input type="file" accept=".drawio,.xml,text/xml,application/xml" class="visually-hidden" @change="onImportFile" />
        <span class="drawio-import-btn">Импорт</span>
      </label>
      <button v-if="canExport" type="button" class="drawio-import-btn" @click="exportSceneFile">Экспорт</button>
      <button
        v-if="editor.isEditable"
        type="button"
        class="drawio-toggle"
        title="Перезагрузить диаграмму, если загрузка зависла"
        @click="reloadBlock"
      >
        Обновить
      </button>
      <button v-if="editor.isEditable" type="button" class="drawio-toggle" @click="deleteNode">Удалить блок</button>
    </div>
    <div
      v-show="expanded"
      ref="fullscreenShellRef"
      class="drawio-fullscreen-shell"
      :class="{ 'drawio-fullscreen-shell--note-wide': noteWideUi }"
      :style="noteWideShellStyle"
    >
      <div v-show="!shellInNativeFullscreen" class="drawio-innerbar">
        <span v-if="!editor.isEditable" class="drawio-readonly-hint">Только просмотр</span>
        <div class="drawio-innerbar-spacer" />
        <button
          type="button"
          class="drawio-fs-btn"
          title="Почти во весь экран в окне браузера. Не браузерный F11."
          @click="toggleNoteWide"
        >
          {{ noteWideUi ? 'Свернуть рабочую область' : 'На всю рабочую область' }}
        </button>
        <button type="button" class="drawio-fs-btn" title="Диаграмма на весь экран. Выход — Esc" @click="toggleFullscreen">
          На весь экран
        </button>
      </div>
      <iframe
        :key="frameKey"
        ref="frameRef"
        class="drawio-host"
        data-drawio-frame
        :src="frameSrc"
        title="draw.io"
        @load="postInit"
      />
    </div>
  </NodeViewWrapper>
</template>

<style scoped>
.drawio-node {
  border: 1px solid var(--border);
  border-radius: 8px;
  margin: 0.5rem 0;
  overflow: hidden;
  background: var(--panel);
}
.drawio-node-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
  padding: 0.5rem 0.65rem;
  border-bottom: 1px solid var(--border);
  font-size: var(--fs-xs);
}
.drawio-toggle {
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg);
  cursor: pointer;
  font: inherit;
}
.drawio-toggle:hover {
  border-color: var(--accent);
}
.drawio-toggle-main {
  font-weight: 600;
}
.drawio-import {
  cursor: pointer;
}
.drawio-import-btn {
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
.drawio-fullscreen-shell {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--panel);
}
.drawio-fullscreen-shell:fullscreen {
  background: var(--panel);
}
.drawio-node--note-wide {
  overflow: visible !important;
  position: relative;
  z-index: 9999;
}
.drawio-fullscreen-shell--note-wide {
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
.drawio-innerbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: 0.35rem 0.5rem;
  border-bottom: 1px solid var(--border);
  gap: 0.5rem;
  flex-shrink: 0;
}
.drawio-innerbar-spacer {
  flex: 1;
  min-width: 0.5rem;
}
.drawio-readonly-hint {
  color: var(--muted, #888);
  font-size: var(--fs-2xs);
  font-weight: 600;
}
.drawio-fs-btn {
  padding: 0.28rem 0.55rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg);
  cursor: pointer;
  font: inherit;
  font-size: var(--fs-2xs);
  font-weight: 600;
}
.drawio-fs-btn:hover {
  border-color: var(--accent);
  color: var(--accent-text);
}
.drawio-host {
  display: block;
  width: 100%;
  height: min(598px, 80.5vh);
  min-height: 360px;
  border: 0;
  background: #fff;
}
.drawio-fullscreen-shell:fullscreen .drawio-host,
.drawio-fullscreen-shell--note-wide .drawio-host {
  flex: 1;
  min-height: 0;
  height: auto;
  max-height: none;
}
</style>
