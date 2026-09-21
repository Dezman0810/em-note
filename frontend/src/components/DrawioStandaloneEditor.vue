<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import { parseDrawioScene, stringifyDrawioScene, normalizeDrawioXml } from './tiptap/drawioDefaultScene'
import { downloadTextFile, safeDownloadBaseName } from '../utils/downloadTextFile'

const props = defineProps<{
  scene: string
  readOnly: boolean
  blockId?: string | null
  canExport?: boolean
  exportTitle?: string
  hideFileToolbar?: boolean
}>()

const emit = defineEmits<{
  change: [scene: string]
}>()

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
  const id = props.blockId || 'map'
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
      xml: parseDrawioScene(props.scene),
      readonly: props.readOnly,
    },
    '*'
  )
}

function onSceneDebounced(xml: string) {
  if (props.readOnly) return
  lastEmittedScene.value = xml
  emit('change', xml)
}

function onFrameMessage(ev: MessageEvent) {
  const frameWin = frameRef.value?.contentWindow
  if (!frameWin || ev.source !== frameWin) return
  try {
    if (ev.origin && ev.origin !== 'null' && new URL(ev.origin).hostname !== window.location.hostname) {
      return
    }
  } catch {
    return
  }
  const msg = ev.data
  if (!msg || typeof msg !== 'object') return
  if (msg.type === 'em-note-drawio-ready') {
    postInit()
    return
  }
  if (msg.type !== 'em-note-drawio-save' || props.readOnly) return
  const xml = stringifyDrawioScene(typeof msg.xml === 'string' ? msg.xml : '')
  if (normalizeSceneXml(xml) === normalizeSceneXml(lastEmittedScene.value || props.scene)) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveTimer = null
    onSceneDebounced(xml)
  }, 400)
}

watch(
  () => props.scene,
  (newScene) => {
    if (lastEmittedScene.value === null) {
      lastEmittedScene.value = newScene
      return
    }
    if (normalizeSceneXml(newScene) === normalizeSceneXml(lastEmittedScene.value)) return
    lastEmittedScene.value = newScene
    initSent = false
    frameKey.value++
  }
)

watch(
  () => props.readOnly,
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

function onImportFile(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || props.readOnly) return
  const reader = new FileReader()
  reader.onload = () => {
    applyImportText(String(reader.result || ''))
  }
  reader.readAsText(file, 'utf-8')
}

function exportSceneFile() {
  const title = safeDownloadBaseName(props.exportTitle || 'diagram', 'diagram')
  downloadTextFile(`${title}.drawio`, stringifyDrawioScene(props.scene), 'application/xml')
}

function applyImportText(text: string) {
  if (props.readOnly) return
  if (text.includes('<mxfile') || text.includes('<mxGraphModel')) {
    const xml = stringifyDrawioScene(text)
    lastEmittedScene.value = xml
    emit('change', xml)
    initSent = false
    frameKey.value++
  }
}

function reloadEditor() {
  initSent = false
  lastEmittedScene.value = props.scene
  frameKey.value++
}

defineExpose({ exportSceneFile, applyImportText, reloadEditor })

onMounted(() => {
  lastEmittedScene.value = props.scene
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
  <div class="mindmap-standalone" :class="{ 'mindmap-standalone--note-wide': noteWideUi }">
    <div
      ref="fullscreenShellRef"
      class="mindmap-fullscreen-shell"
      :class="{ 'mindmap-fullscreen-shell--note-wide': noteWideUi }"
      :style="noteWideShellStyle"
    >
      <div v-show="!shellInNativeFullscreen" class="mindmap-innerbar">
        <span v-if="readOnly" class="mindmap-readonly-hint">Только просмотр</span>
        <template v-if="!hideFileToolbar">
          <label v-if="!readOnly" class="mindmap-import">
            <input type="file" accept=".drawio,.xml,text/xml,application/xml" class="visually-hidden" @change="onImportFile" />
            <span class="mindmap-import-btn">Импорт</span>
          </label>
          <button v-if="canExport" type="button" class="mindmap-import-btn" @click="exportSceneFile">Экспорт</button>
          <button
            v-if="!readOnly"
            type="button"
            class="mindmap-fs-btn"
            title="Перезагрузить диаграмму, если загрузка зависла"
            @click="reloadEditor"
          >
            Обновить
          </button>
        </template>
        <div class="mindmap-innerbar-spacer" />
        <button
          type="button"
          class="mindmap-fs-btn"
          title="Почти во весь экран в окне браузера. Не браузерный F11."
          @click="toggleNoteWide"
        >
          {{ noteWideUi ? 'Свернуть рабочую область' : 'На всю рабочую область' }}
        </button>
        <button type="button" class="mindmap-fs-btn" title="Диаграмма на весь экран. Выход — Esc" @click="toggleFullscreen">
          На весь экран
        </button>
      </div>
      <iframe
        :key="frameKey"
        ref="frameRef"
        class="mindmap-host"
        data-drawio-frame
        :src="frameSrc"
        title="Интеллект-карта"
        @load="postInit"
      />
    </div>
  </div>
</template>

<style scoped>
.mindmap-standalone {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--panel);
}
.mindmap-standalone--note-wide {
  overflow: visible;
  position: relative;
  z-index: 9999;
}
.mindmap-fullscreen-shell {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--panel);
}
.mindmap-fullscreen-shell:fullscreen {
  background: var(--panel);
}
.mindmap-fullscreen-shell--note-wide {
  position: fixed;
  z-index: 10000;
  max-height: none !important;
  margin: 0;
  flex: unset;
  box-shadow: 0 0 0 9999px var(--shadow-tint-strong);
  border-radius: 0;
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
.mindmap-import {
  cursor: pointer;
}
.mindmap-import-btn {
  cursor: pointer;
  color: var(--accent-text);
  text-decoration: underline;
  font-size: var(--fs-2xs);
  font-weight: 600;
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
  flex: 1 1 auto;
  width: 100%;
  min-height: 0;
  height: auto;
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
