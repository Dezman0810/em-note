<script setup lang="ts">
import { nodeViewProps, NodeViewWrapper } from '@tiptap/vue-3'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps(nodeViewProps)

type Handle = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'

const HANDLES: Handle[] = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']

const boxRef = ref<HTMLElement | null>(null)
const liveWidthPercent = ref<number | null>(null)
const liveHeightPx = ref<number | null>(null)
const resizing = ref(false)
const resizeKind = ref<'prop' | 'free' | null>(null)

const widthPercent = computed(() => {
  if (liveWidthPercent.value != null) return liveWidthPercent.value
  const n = Number(props.node.attrs.widthPercent)
  return Number.isFinite(n) ? Math.min(100, Math.max(8, n)) : 100
})

const heightPx = computed(() => {
  if (liveHeightPx.value != null) return liveHeightPx.value
  const n = Number(props.node.attrs.heightPx)
  return Number.isFinite(n) && n > 0 ? n : null
})

const wrap = computed(() => {
  const w = String(props.node.attrs.wrap || 'none')
  return w === 'left' || w === 'right' ? w : 'none'
})

const wrapping = computed(() => wrap.value !== 'none')

const rootStyle = computed(() => {
  const w = wrapping.value ? `${widthPercent.value}%` : '100%'
  return {
    width: w,
    maxWidth: wrapping.value ? 'calc(100% - 0.5rem)' : '100%',
    whiteSpace: 'normal' as const,
  }
})

function wrapperEl(): HTMLElement | null {
  return (boxRef.value?.closest('[data-node-view-wrapper]') as HTMLElement | null) ?? null
}

function applyWrapperWidth() {
  const el = wrapperEl()
  if (!el) return
  const w = wrapping.value ? `${widthPercent.value}%` : '100%'
  el.style.setProperty('width', w, 'important')
  el.style.setProperty('max-width', wrapping.value ? 'calc(100% - 0.5rem)' : '100%', 'important')
}

watch([widthPercent, wrapping], () => {
  void nextTick(applyWrapperWidth)
})

onMounted(() => {
  void nextTick(applyWrapperWidth)
})

const boxStyle = computed(() => {
  const style: Record<string, string> = wrapping.value
    ? { width: '100%' }
    : { width: `${widthPercent.value}%` }
  if (heightPx.value != null) style.height = `${Math.round(heightPx.value)}px`
  return style
})

const imgStyle = computed(() => {
  if (heightPx.value != null) {
    return { width: '100%', height: '100%', objectFit: 'fill' as const }
  }
  return { width: '100%', height: 'auto', objectFit: 'contain' as const }
})

const badge = computed(() => {
  const w = `${Math.round(widthPercent.value)}%`
  if (heightPx.value != null) return `${w} × ${Math.round(heightPx.value)}px`
  return w
})

let unbind: (() => void) | null = null

function setWrap(next: 'none' | 'left' | 'right') {
  if (!props.editor.isEditable) return
  const patch: Record<string, unknown> = { wrap: next }
  const cur = Number(props.node.attrs.widthPercent)
  if (next !== 'none' && (!Number.isFinite(cur) || cur >= 92)) {
    patch.widthPercent = 48
  }
  if (next === 'none' && Number.isFinite(cur) && cur <= 55) {
    patch.widthPercent = 100
    patch.heightPx = null
  }
  props.updateAttributes(patch)
}

function clamp(n: number, min: number, max: number) {
  return Math.min(max, Math.max(min, n))
}

function onResizeStart(e: PointerEvent, handle: Handle) {
  if (!props.editor.isEditable) return
  const box = boxRef.value
  if (!box) return
  e.preventDefault()
  e.stopPropagation()
  ;(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId)
  const startX = e.clientX
  const startY = e.clientY
  const startRect = box.getBoundingClientRect()
  const editorW = Math.max(1, props.editor.view.dom.clientWidth)
  const startW = startRect.width
  const startH = startRect.height
  const startPct = widthPercent.value
  const startHpx = heightPx.value ?? startH
  const proportional = handle.length === 2
  resizing.value = true
  resizeKind.value = proportional ? 'prop' : 'free'
  liveWidthPercent.value = startPct
  liveHeightPx.value = proportional ? null : startHpx

  const onMove = (ev: PointerEvent) => {
    let dx = ev.clientX - startX
    let dy = ev.clientY - startY
    if (handle.includes('w')) dx = -dx
    if (handle.includes('n')) dy = -dy
    if (proportional) {
      const nextW = clamp(startW + dx, editorW * 0.08, editorW)
      liveWidthPercent.value = Math.round((nextW / editorW) * 1000) / 10
      liveHeightPx.value = null
    } else if (handle === 'e' || handle === 'w') {
      const nextW = clamp(startW + dx, editorW * 0.08, editorW)
      liveWidthPercent.value = Math.round((nextW / editorW) * 1000) / 10
      liveHeightPx.value = Math.round(startHpx)
    } else {
      liveHeightPx.value = Math.round(clamp(startH + dy, 24, 4000))
    }
  }

  const onUp = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
    window.removeEventListener('pointercancel', onUp)
    unbind = null
    const pct = liveWidthPercent.value
    const h = liveHeightPx.value
    resizing.value = false
    resizeKind.value = null
    liveWidthPercent.value = null
    liveHeightPx.value = null
    if (pct == null) return
    props.updateAttributes({
      widthPercent: clamp(Math.round(pct * 10) / 10, 8, 100),
      heightPx: h != null && h > 0 ? Math.round(h) : null,
    })
  }

  unbind = onUp
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
  window.addEventListener('pointercancel', onUp)
}

onBeforeUnmount(() => {
  unbind?.()
})
</script>

<template>
  <NodeViewWrapper
    class="rz-img-root"
    :class="{
      'rz-img-root--left': wrap === 'left',
      'rz-img-root--right': wrap === 'right',
      'rz-img-root--resizing': resizing,
    }"
    :style="rootStyle"
    contenteditable="false"
  >
    <div
      ref="boxRef"
      class="rz-img-box"
      :class="{ 'rz-img-box--resizing': resizing, 'rz-img-box--free': heightPx != null }"
      :style="boxStyle"
    >
      <div v-if="editor.isEditable" class="rz-img-align">
        <button
          type="button"
          class="rz-img-align-btn"
          :class="{ on: wrap === 'left' }"
          title="Картинка слева, текст справа"
          @click.prevent="setWrap('left')"
        >
          ◧
        </button>
        <button
          type="button"
          class="rz-img-align-btn"
          :class="{ on: wrap === 'none' }"
          title="На всю ширину, без обтекания"
          @click.prevent="setWrap('none')"
        >
          ▭
        </button>
        <button
          type="button"
          class="rz-img-align-btn"
          :class="{ on: wrap === 'right' }"
          title="Картинка справа, текст слева"
          @click.prevent="setWrap('right')"
        >
          ◨
        </button>
      </div>
      <img
        class="rz-img"
        data-drag-handle
        draggable="true"
        :src="String(node.attrs.src || '')"
        :alt="String(node.attrs.alt || '')"
        :title="
          editor.isEditable
            ? 'Перетащите в тексте. Уголки — пропорции (%). Кнопки сверху — слева/справа от текста.'
            : String(node.attrs.alt || '')
        "
        :style="imgStyle"
      />
      <template v-if="editor.isEditable">
        <span
          v-for="h in HANDLES"
          :key="h"
          class="rz-h"
          :class="[`rz-h--${h}`, h.length === 2 ? 'rz-h--corner' : 'rz-h--edge']"
          :data-handle="h"
          @pointerdown.stop.prevent="onResizeStart($event, h)"
          @mousedown.stop.prevent
          @dragstart.stop.prevent
        />
      </template>
      <span v-if="resizing" class="rz-badge">{{ badge }}</span>
    </div>
  </NodeViewWrapper>
</template>

<style scoped>
.rz-img-root {
  display: block;
  margin: 0.45rem 0;
  max-width: 100%;
}
.rz-img-root--left,
.rz-img-root--right {
  position: relative;
  z-index: 2;
  margin-top: 0.2rem;
  margin-bottom: 0.45rem;
  max-width: calc(100% - 0.5rem);
}
.rz-img-root--left:hover,
.rz-img-root--right:hover,
.rz-img-root--resizing {
  z-index: 5;
}
.rz-img-root--left {
  float: left;
  margin-right: 0.85rem;
}
.rz-img-root--right {
  float: right;
  margin-left: 0.85rem;
}
.rz-img-align {
  display: none;
  position: absolute;
  top: 6px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 4;
  gap: 2px;
  padding: 2px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(148, 163, 184, 0.45);
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
}
.rz-img-box:hover .rz-img-align,
.rz-img-box--resizing .rz-img-align {
  display: flex;
}
.rz-img-align-btn {
  width: 1.35rem;
  height: 1.2rem;
  padding: 0;
  border: none;
  border-radius: 5px;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  font-size: 0.75rem;
  line-height: 1;
}
.rz-img-align-btn.on {
  background: rgba(37, 99, 235, 0.12);
  color: var(--accent, #2563eb);
}
.rz-img-align-btn:hover {
  background: rgba(148, 163, 184, 0.18);
}
.rz-img-box {
  position: relative;
  display: block;
  max-width: 100%;
  vertical-align: top;
  line-height: 0;
}
.rz-img {
  display: block;
  max-width: 100%;
  border-radius: 4px;
  cursor: grab;
}
.rz-img:active {
  cursor: grabbing;
}
.rz-h {
  position: absolute;
  z-index: 6;
  box-sizing: border-box;
  background: #fff;
  border: 1.5px solid var(--accent, #2563eb);
  border-radius: 2px;
  opacity: 0;
  pointer-events: auto;
  touch-action: none;
}
.rz-h::after {
  content: '';
  position: absolute;
  inset: -8px;
}
.rz-img-box:hover .rz-h,
.rz-img-box--resizing .rz-h {
  opacity: 1;
}
.rz-h--corner {
  width: 12px;
  height: 12px;
}
.rz-h--edge {
  background: var(--accent, #2563eb);
  border-radius: 1px;
}
.rz-h--n,
.rz-h--s {
  left: 50%;
  width: 18px;
  height: 6px;
  margin-left: -9px;
  cursor: ns-resize;
}
.rz-h--e,
.rz-h--w {
  top: 50%;
  width: 6px;
  height: 18px;
  margin-top: -9px;
  cursor: ew-resize;
}
.rz-h--n {
  top: -4px;
}
.rz-h--s {
  bottom: -4px;
}
.rz-h--e {
  right: -4px;
}
.rz-h--w {
  left: -4px;
}
.rz-h--ne,
.rz-h--nw,
.rz-h--se,
.rz-h--sw {
  cursor: nwse-resize;
}
.rz-h--nw,
.rz-h--sw {
  cursor: nesw-resize;
}
.rz-h--nw {
  top: -4px;
  left: -4px;
  cursor: nwse-resize;
}
.rz-h--ne {
  top: -4px;
  right: -4px;
  cursor: nesw-resize;
}
.rz-h--sw {
  bottom: -4px;
  left: -4px;
  cursor: nesw-resize;
}
.rz-h--se {
  bottom: -4px;
  right: -4px;
  cursor: nwse-resize;
}
.rz-badge {
  position: absolute;
  left: 50%;
  bottom: 8px;
  transform: translateX(-50%);
  z-index: 3;
  font-size: 0.6875rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: #fff;
  background: rgba(15, 23, 42, 0.72);
  border-radius: 6px;
  padding: 0.12rem 0.4rem;
  pointer-events: none;
  line-height: 1.2;
}
</style>
