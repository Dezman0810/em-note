<script setup lang="ts">
import { nodeViewProps, NodeViewWrapper } from '@tiptap/vue-3'
import { computed, ref, watch } from 'vue'

const props = defineProps(nodeViewProps)

const src = computed(() => String(props.node.attrs.src || ''))
const mime = computed(() => String(props.node.attrs.mime || 'audio/webm'))

/** Локальное поле, чтобы не терять ввод при обновлениях документа */
const titleDraft = ref(String(props.node.attrs.label ?? ''))
watch(
  () => props.node.attrs.label,
  (v) => {
    titleDraft.value = String(v ?? '')
  }
)

function onTitleBlur() {
  const t = titleDraft.value.trim()
  if (t !== String(props.node.attrs.label ?? '').trim()) {
    props.updateAttributes({ label: t })
  }
}

function onTitleEnter(e: KeyboardEvent) {
  ;(e.target as HTMLInputElement).blur()
}

function remove() {
  props.deleteNode()
}
</script>

<template>
  <NodeViewWrapper class="audio-note-root" contenteditable="false" data-drag-handle>
    <div class="audio-note-card">
      <div class="audio-note-head">
        <label class="audio-note-title-lab">
          <span class="sr-only">Название записи</span>
          <input
            v-model="titleDraft"
            type="text"
            class="audio-note-title-input"
            :readonly="!editor.isEditable"
            placeholder="Название записи"
            maxlength="200"
            @blur="onTitleBlur"
            @keydown.enter.prevent="onTitleEnter"
            @keydown.stop
          />
        </label>
        <button
          v-if="editor.isEditable"
          type="button"
          class="audio-note-remove"
          title="Удалить аудио"
          @click.prevent="remove"
        >
          Удалить
        </button>
      </div>
      <div class="audio-note-inner">
        <audio v-if="src" class="audio-note-player" controls :src="src" :type="mime" />
        <p v-else class="audio-note-empty muted">Нет данных записи</p>
      </div>
    </div>
  </NodeViewWrapper>
</template>

<style scoped>
.sr-only {
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
.muted {
  color: var(--text-muted, #64748b);
}
.audio-note-root {
  margin: 0.5rem 0;
}
.audio-note-card {
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(37, 99, 235, 0.04);
  overflow: hidden;
}
.audio-note-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0.5rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.35);
  background: rgba(255, 255, 255, 0.45);
}
.audio-note-title-lab {
  flex: 1;
  min-width: 0;
  margin: 0;
}
.audio-note-title-input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid transparent;
  border-radius: 6px;
  padding: 0.28rem 0.4rem;
  font: inherit;
  font-size: 0.8rem;
  font-weight: 600;
  color: #1e293b;
  background: transparent;
}
.audio-note-title-input:not(:read-only) {
  border-color: rgba(148, 163, 184, 0.45);
  background: var(--panel, #fff);
}
.audio-note-title-input::placeholder {
  color: #94a3b8;
  font-weight: 500;
}
.audio-note-title-input:focus {
  outline: 2px solid rgba(37, 99, 235, 0.35);
  outline-offset: 0;
}
.audio-note-inner {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.65rem;
  padding: 0.5rem 0.65rem;
}
.audio-note-player {
  flex: 1 1 180px;
  min-width: 160px;
  max-width: 100%;
  height: 32px;
}
.audio-note-empty {
  margin: 0;
  font-size: 0.78rem;
}
.audio-note-remove {
  flex-shrink: 0;
  padding: 0.22rem 0.5rem;
  font-size: 0.72rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--panel);
  cursor: pointer;
  color: var(--danger);
}
.audio-note-remove:hover {
  background: rgba(220, 38, 38, 0.08);
}
</style>
