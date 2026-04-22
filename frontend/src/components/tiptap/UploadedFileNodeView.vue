<script setup lang="ts">
import { nodeViewProps, NodeViewWrapper } from '@tiptap/vue-3'
import { onBeforeUnmount, ref, watch } from 'vue'
import { fetchAttachmentBlob } from '../../utils/attachmentBlob'

const props = defineProps(nodeViewProps)

const blobUrl = ref<string | null>(null)
const loadErr = ref('')
let revokeOnUnmount: string | null = null

async function loadBlob() {
  const id = String(props.node.attrs.attachmentId || '').trim()
  loadErr.value = ''
  if (revokeOnUnmount) {
    URL.revokeObjectURL(revokeOnUnmount)
    revokeOnUnmount = null
  }
  blobUrl.value = null
  if (!id) return
  try {
    const blob = await fetchAttachmentBlob(id)
    const u = URL.createObjectURL(blob)
    revokeOnUnmount = u
    blobUrl.value = u
  } catch (e) {
    loadErr.value = e instanceof Error ? e.message : 'Не удалось загрузить файл'
  }
}

watch(
  () => props.node.attrs.attachmentId,
  () => void loadBlob(),
  { immediate: true }
)

function remove() {
  props.deleteNode()
}

async function downloadFile() {
  const id = String(props.node.attrs.attachmentId || '').trim()
  const name = String(props.node.attrs.filename || 'download')
  if (!id) return
  try {
    const blob = await fetchAttachmentBlob(id)
    const u = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = u
    a.download = name
    a.click()
    URL.revokeObjectURL(u)
  } catch {
    loadErr.value = 'Не удалось скачать'
  }
}

onBeforeUnmount(() => {
  if (revokeOnUnmount) URL.revokeObjectURL(revokeOnUnmount)
})
</script>

<template>
  <NodeViewWrapper class="uploaded-file-root" contenteditable="false" data-drag-handle>
    <div class="uploaded-file-card">
      <div class="uploaded-file-head">
        <span class="uploaded-file-name" :title="String(node.attrs.filename || '')">{{
          node.attrs.filename || 'Файл'
        }}</span>
        <div class="uploaded-file-actions">
          <button
            v-if="!node.attrs.isImage"
            type="button"
            class="uploaded-file-btn"
            @click.prevent="downloadFile"
          >
            Скачать
          </button>
          <button
            v-if="editor.isEditable"
            type="button"
            class="uploaded-file-btn danger"
            title="Удалить из заметки"
            @click.prevent="remove"
          >
            Удалить
          </button>
        </div>
      </div>
      <p v-if="loadErr" class="uploaded-file-err">{{ loadErr }}</p>
      <div v-else-if="node.attrs.isImage && blobUrl" class="uploaded-file-img-wrap">
        <img class="uploaded-file-img" :src="blobUrl" :alt="String(node.attrs.filename || '')" />
      </div>
      <p v-else-if="node.attrs.isImage && !blobUrl" class="muted small">Загрузка…</p>
      <p v-else class="muted small">Вложение сохранено на сервере.</p>
    </div>
  </NodeViewWrapper>
</template>

<style scoped>
.uploaded-file-root {
  margin: 0.6rem 0;
}
.uploaded-file-card {
  border: 1px solid var(--border, #e5e5e5);
  border-radius: 8px;
  padding: 0.65rem 0.75rem;
  background: var(--panel, #fafafa);
}
.uploaded-file-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.35rem;
}
.uploaded-file-name {
  font-size: 0.88rem;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.uploaded-file-actions {
  display: flex;
  gap: 0.35rem;
  flex-shrink: 0;
}
.uploaded-file-btn {
  font-size: 0.8rem;
  padding: 0.2rem 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--border, #ddd);
  background: var(--bg, #fff);
  cursor: pointer;
}
.uploaded-file-btn.danger {
  color: var(--danger, #b91c1c);
  border-color: color-mix(in srgb, var(--danger, #b91c1c) 35%, transparent);
}
.uploaded-file-err {
  color: var(--danger, #b91c1c);
  font-size: 0.85rem;
  margin: 0.25rem 0 0;
}
.uploaded-file-img-wrap {
  margin-top: 0.35rem;
}
.uploaded-file-img {
  max-width: 100%;
  height: auto;
  border-radius: 6px;
  display: block;
}
.muted.small {
  margin: 0.25rem 0 0;
  font-size: 0.82rem;
}
</style>
