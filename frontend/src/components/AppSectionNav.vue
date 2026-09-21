<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { primeMindmapOnIntent } from '../utils/mindmapWarmup'

export type AppSectionId = 'notes' | 'habits' | 'budget' | 'schemas' | 'mindmaps' | 'diagrams' | 'tags'

defineProps<{
  active: AppSectionId
}>()

const auth = useAuthStore()
const router = useRouter()

const items = computed(() => {
  const out: { id: AppSectionId; label: string; to: { name: string } }[] = [
    { id: 'notes', label: 'Заметки', to: { name: 'notes' } },
  ]
  if (auth.user?.can_use_schemas) {
    out.push({ id: 'schemas', label: 'Схемы', to: { name: 'schemas' } })
    out.push({ id: 'mindmaps', label: 'Карты', to: { name: 'mindmaps' } })
    out.push({ id: 'diagrams', label: 'Диаграммы', to: { name: 'diagrams' } })
  }
  out.push({ id: 'tags', label: 'Метки', to: { name: 'tags' } })
  if (auth.user?.can_use_habits) {
    out.push({ id: 'habits', label: 'Привычки', to: { name: 'habits' } })
  }
  if (auth.user?.can_use_budget) {
    out.push({ id: 'budget', label: 'Бюджет', to: { name: 'budget' } })
  }
  return out
})

function openSection(item: (typeof items.value)[number]) {
  if (item.id === 'mindmaps') primeMindmapOnIntent()
  void router.push(item.to)
}
</script>

<template>
  <nav class="section-nav" aria-label="Разделы">
    <button
      v-for="item in items"
      :key="item.id"
      type="button"
      class="btn header-tags-btn"
      :class="item.id === active ? 'section-nav-on' : 'secondary'"
      :aria-current="item.id === active ? 'page' : undefined"
      @click="openSection(item)"
    >
      {{ item.label }}
    </button>
  </nav>
</template>

<style scoped>
.section-nav {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  justify-content: flex-end;
  gap: 0.45rem;
  flex: 1 1 auto;
  min-width: 0;
  max-width: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  overscroll-behavior-x: contain;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
  mask-image: linear-gradient(to right, #000 0%, #000 calc(100% - 1.1rem), transparent 100%);
}
.section-nav::-webkit-scrollbar {
  display: none;
}
.header-tags-btn {
  flex-shrink: 0;
  font-family: inherit;
  font-size: var(--fs-2xs);
  font-weight: var(--fw-medium);
  line-height: var(--lh-tight);
  padding: var(--space-3) var(--space-5);
}
.btn.section-nav-on {
  font-size: var(--fs-2xs);
  font-weight: var(--fw-medium);
  padding: var(--space-3) var(--space-5);
  border-radius: var(--radius-pill);
  border: 1px solid var(--accent-border);
  background: var(--accent-subtle);
  color: var(--accent-text);
  cursor: pointer;
}
.btn.section-nav-on:hover:not(:disabled) {
  background: var(--accent-subtle-hover);
  border-color: var(--accent-border);
  color: var(--accent-text);
}
@media (max-width: 768px) {
  .section-nav {
    justify-content: flex-start;
    gap: 0.22rem;
    flex: 1 1 0;
    min-width: 0;
    padding-bottom: 1px;
    mask-image: linear-gradient(to right, #000 0%, #000 calc(100% - 0.85rem), transparent 100%);
  }
  .header-tags-btn,
  .btn.section-nav-on {
    min-width: unset !important;
    min-height: 2rem !important;
    padding: 0.22rem 0.42rem;
    font-size: 0.72rem;
    white-space: nowrap;
  }
}
</style>
