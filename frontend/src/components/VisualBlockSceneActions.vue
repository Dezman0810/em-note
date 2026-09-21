<script setup lang="ts">
defineProps<{
  canEdit: boolean
  canExport: boolean
  accept: string
  reloadTitle?: string
}>()

const emit = defineEmits<{
  importText: [text: string]
  export: []
  reload: []
}>()

function onImportFile(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    emit('importText', String(reader.result || ''))
  }
  reader.readAsText(file, 'utf-8')
}
</script>

<template>
  <div class="block-scene-actions">
    <label v-if="canEdit" class="block-scene-import">
      <input type="file" :accept="accept" class="visually-hidden" @change="onImportFile" />
      <span class="block-scene-link-btn">Импорт</span>
    </label>
    <button v-if="canExport" type="button" class="block-scene-link-btn" @click="emit('export')">
      Экспорт
    </button>
    <button
      v-if="canEdit"
      type="button"
      class="block-scene-btn"
      :title="reloadTitle"
      @click="emit('reload')"
    >
      Обновить
    </button>
  </div>
</template>

<style scoped>
.block-scene-actions {
  display: inline-flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
  flex-shrink: 0;
  min-height: 1.85rem;
}
.block-scene-import {
  cursor: pointer;
}
.block-scene-link-btn {
  cursor: pointer;
  color: var(--accent-text);
  text-decoration: underline;
  border: 0;
  background: transparent;
  font: inherit;
  font-size: var(--fs-xs);
  padding: 0;
}
.block-scene-btn {
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg);
  cursor: pointer;
  font: inherit;
  font-size: var(--fs-xs);
}
.block-scene-btn:hover {
  border-color: var(--accent);
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
</style>
