<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: string
    disabled?: boolean
    placeholder?: string
    ariaLabel?: string
  }>(),
  { placeholder: 'Название' }
)

const emit = defineEmits<{
  'update:modelValue': [string]
  save: [string]
}>()

const draft = ref(props.modelValue)

watch(
  () => props.modelValue,
  (v) => {
    draft.value = v
  }
)

const sizerText = computed(() => `${draft.value.trim() ? draft.value : props.placeholder}\u00a0`)

function commit() {
  const next = draft.value.trim() || props.placeholder || 'Без названия'
  draft.value = next
  if (next === props.modelValue) return
  emit('update:modelValue', next)
  emit('save', next)
}
</script>

<template>
  <div class="block-title-wrap" @mousedown.stop @click.stop>
    <span class="block-title-sizer" aria-hidden="true">{{ sizerText }}</span>
    <input
      class="block-title-field"
      type="text"
      maxlength="80"
      :value="draft"
      :disabled="disabled"
      :placeholder="placeholder"
      :aria-label="ariaLabel || placeholder"
      @input="draft = ($event.target as HTMLInputElement).value"
      @blur="commit"
      @keydown.enter.prevent="($event.target as HTMLInputElement).blur()"
    />
  </div>
</template>

<style scoped>
.block-title-wrap {
  display: inline-grid;
  align-items: center;
  min-width: 12rem;
  max-width: min(36rem, 100%);
  box-sizing: border-box;
}
.block-title-sizer,
.block-title-field {
  grid-area: 1 / 1;
  box-sizing: border-box;
  padding: 0.22rem 0.45rem;
  font: inherit;
  font-weight: 600;
  line-height: 1.25;
  white-space: pre;
}
.block-title-sizer {
  visibility: hidden;
  overflow: hidden;
  min-width: 12rem;
}
.block-title-field {
  width: 100%;
  min-width: 0;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-1);
}
.block-title-field:hover:not(:disabled) {
  border-color: var(--accent);
}
.block-title-field:focus {
  outline: none;
  border-color: var(--accent);
}
.block-title-field:disabled {
  opacity: 0.85;
  cursor: default;
}
</style>
