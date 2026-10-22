<script setup lang="ts">
import { nodeViewProps, NodeViewWrapper } from '@tiptap/vue-3'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { editorContentWidthPx, IMAGE_MIN_WIDTH_PX } from './imageSizing'

const props = defineProps(nodeViewProps)

type Handle = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'

const HANDLES: Handle[] = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']

const boxRef = ref<HTMLElement | null>(null)
const liveWidthPx = ref<number | null>(null)
const liveHeightPx = ref<number | null>(null)
const resizing = ref(false)
const resizeKind = ref<'prop' | 'free' | null>(null)

/** Постоянная ширина в px; null — старая картинка, у которой есть только widthPercent. */
const widthPx = computed(() => {
  if (liveWidthPx.value != null) return liveWidthPx.value
  const n = Number(props.node.attrs.widthPx)
  return Number.isFinite(n) && n > 0 ? n : null
})

/** Ширина старых картинок в % от заметки — пока их не изменили кнопкой или ресайзом. */
const legacyWidthPercent = computed(() => {
  const n = Number(props.node.attrs.widthPercent)
  return Number.isFinite(n) ? Math.min(100, Math.max(8, n)) : 100
})

const widthCss = computed(() =>
  widthPx.value != null ? `${Math.round(widthPx.value)}px` : `${legacyWidthPercent.value}%`
)

const heightPx = computed(() => {
  if (liveHeightPx.value != null) return liveHeightPx.value
  const n = Number(props.node.attrs.heightPx)
  return Number.isFinite(n) && n > 0 ? n : null
})

const wrap = computed(() => {
  const w = String(props.node.attrs.wrap || 'none')
  return w === 'left' || w === 'right' || w === 'center' ? w : 'none'
})

/** Обтекание текстом — только слева/справа; «по центру» и «▭» стоят отдельным блоком. */
const wrapping = computed(() => wrap.value === 'left' || wrap.value === 'right')

/** Старые картинки в % не шире заметки; у картинок в px размер постоянный. */
const rootMaxWidth = computed(() => {
  if (widthPx.value != null) return 'none'
  return wrapping.value ? 'calc(100% - 0.5rem)' : '100%'
})

const rootStyle = computed(() => ({
  width: wrapping.value ? widthCss.value : '100%',
  maxWidth: rootMaxWidth.value,
  whiteSpace: 'normal' as const,
}))

function wrapperEl(): HTMLElement | null {
  return (boxRef.value?.closest('[data-node-view-wrapper]') as HTMLElement | null) ?? null
}

function applyWrapperWidth() {
  const el = wrapperEl()
  if (!el) return
  el.style.setProperty('width', rootStyle.value.width, 'important')
  el.style.setProperty('max-width', rootMaxWidth.value, 'important')
}

watch([widthCss, wrapping, rootMaxWidth], () => {
  void nextTick(applyWrapperWidth)
})

onMounted(() => {
  void nextTick(applyWrapperWidth)
})

const boxStyle = computed(() => {
  const style: Record<string, string> = { width: wrapping.value ? '100%' : widthCss.value }
  if (widthPx.value != null) style.maxWidth = 'none'
  if (heightPx.value != null) style.height = `${Math.round(heightPx.value)}px`
  return style
})

const imgStyle = computed(() => {
  const base = widthPx.value != null ? { maxWidth: 'none' } : {}
  if (heightPx.value != null) {
    return { ...base, width: '100%', height: '100%', objectFit: 'fill' as const }
  }
  return { ...base, width: '100%', height: 'auto', objectFit: 'contain' as const }
})

const badge = computed(() => {
  const w =
    widthPx.value != null
      ? `${Math.round(widthPx.value)}px`
      : `${Math.round(legacyWidthPercent.value)}%`
  if (heightPx.value != null) return `${w} × ${Math.round(heightPx.value)}px`
  return w
})

let unbind: (() => void) | null = null

/** Ширина картинки на экране в px — так старые картинки в % переходят на постоянный размер. */
function currentWidthPx(): number {
  if (widthPx.value != null) return widthPx.value
  const w = boxRef.value?.getBoundingClientRect().width
  return Math.round(w && w > 0 ? w : editorContentWidthPx(props.editor.view))
}

function setWrap(next: 'none' | 'center' | 'left' | 'right') {
  if (!props.editor.isEditable) return
  const editorW = editorContentWidthPx(props.editor.view)
  let w = currentWidthPx()
  // Почти во всю ширину текст обтекать негде — для обтекания уменьшаем до половины.
  if ((next === 'left' || next === 'right') && w >= editorW * 0.92) {
    w = Math.round(editorW * 0.48)
  }
  // «▭» и «по центру» сохраняют текущий размер: сами ничего не растягиваем.
  props.updateAttributes({ wrap: next, widthPx: Math.round(w) })
}

/** Явное «растянуть»: ширина текста заметки на момент нажатия, дальше размер постоянный. */
function stretchFullWidth() {
  if (!props.editor.isEditable) return
  const patch: Record<string, unknown> = {
    widthPx: Math.round(editorContentWidthPx(props.editor.view)),
    heightPx: null,
  }
  if (wrapping.value) patch.wrap = 'none'
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
  // Ресайзом не выходим за ширину текста: иначе картинка уедет под горизонтальную прокрутку.
  const maxW = Math.max(IMAGE_MIN_WIDTH_PX, editorContentWidthPx(props.editor.view))
  const startW = startRect.width
  const startH = startRect.height
  const startHpx = heightPx.value ?? startH
  const proportional = handle.length === 2
  resizing.value = true
  resizeKind.value = proportional ? 'prop' : 'free'
  liveWidthPx.value = Math.round(startW)
  liveHeightPx.value = proportional ? null : startHpx

  const onMove = (ev: PointerEvent) => {
    let dx = ev.clientX - startX
    let dy = ev.clientY - startY
    if (handle.includes('w')) dx = -dx
    if (handle.includes('n')) dy = -dy
    // По центру ширина растёт в обе стороны — иначе ручка отставала бы от курсора вдвое.
    if (wrap.value === 'center') dx *= 2
    if (proportional) {
      liveWidthPx.value = Math.round(clamp(startW + dx, IMAGE_MIN_WIDTH_PX, maxW))
      liveHeightPx.value = null
    } else if (handle === 'e' || handle === 'w') {
      liveWidthPx.value = Math.round(clamp(startW + dx, IMAGE_MIN_WIDTH_PX, maxW))
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
    const w = liveWidthPx.value
    const h = liveHeightPx.value
    resizing.value = false
    resizeKind.value = null
    liveWidthPx.value = null
    liveHeightPx.value = null
    if (w == null) return
    props.updateAttributes({
      widthPx: Math.round(w),
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
      'rz-img-root--center': wrap === 'center',
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
          aria-label="Картинка слева, текст справа"
          title="Картинка слева, текст справа"
          @click.prevent="setWrap('left')"
        >
          ◧
        </button>
        <button
          type="button"
          class="rz-img-align-btn"
          :class="{ on: wrap === 'none' }"
          aria-label="На всю ширину, без обтекания"
          title="На всю ширину, без обтекания"
          @click.prevent="setWrap('none')"
        >
          ▭
        </button>
        <button
          type="button"
          class="rz-img-align-btn"
          :class="{ on: wrap === 'center' }"
          aria-label="По центру, без обтекания"
          title="По центру, без обтекания"
          @click.prevent="setWrap('center')"
        >
          ⊡
        </button>
        <button
          type="button"
          class="rz-img-align-btn"
          aria-label="Растянуть на всю ширину"
          title="Растянуть на всю ширину заметки"
          @click.prevent="stretchFullWidth"
        >
          ↔
        </button>
        <button
          type="button"
          class="rz-img-align-btn"
          :class="{ on: wrap === 'right' }"
          aria-label="Картинка справа, текст слева"
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
            ? 'Перетащите в тексте. Уголки — размер с пропорциями (px). Кнопки сверху — положение.'
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
/* По центру: отдельным блоком под плавающими картинками, пустота слева и справа поровну */
.rz-img-root--center {
  display: flex;
  justify-content: center;
  clear: both;
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
  background: var(--surface-translucent);
  border: 1px solid var(--border);
  box-shadow: 0 1px 3px var(--shadow-tint-weak);
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
  color: var(--text-4);
  cursor: pointer;
  font-size: var(--fs-2xs);
  line-height: 1;
}
.rz-img-align-btn.on {
  background: var(--accent-subtle-hover);
  color: var(--accent-text);
}
.rz-img-align-btn:hover {
  background: var(--surface-wash);
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
  background: var(--surface-1);
  border: 1.5px solid var(--accent);
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
  background: var(--accent);
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
  font-size: var(--fs-2xs);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-on-accent);
  background: var(--scrim-strong);
  border-radius: 6px;
  padding: 0.12rem 0.4rem;
  pointer-events: none;
  line-height: var(--lh-tight);
}
</style>
