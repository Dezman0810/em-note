<script setup lang="ts">
import { useRouter } from 'vue-router'
import AppSectionNav from '../components/AppSectionNav.vue'
import { useAuthStore } from '../stores/auth'
import { useTheme } from '../composables/useTheme'

const auth = useAuthStore()
const router = useRouter()
const { label: themeLabel, icon: themeIcon, cycleTheme } = useTheme()

function logout() {
  auth.logout()
  void router.push({ name: 'login' })
}
</script>

<template>
  <div class="workspace budget-workspace">
    <header class="workspace-header">
      <div class="header-left">
        <button
          type="button"
          class="logo logo-wordmark logo-home-btn"
          lang="ru"
          @click="router.push({ name: 'notes' })"
        >
          <span class="logo-brand"
            ><span class="logo-brand-accent">Em</span><span class="logo-brand-dash">-</span><span>Note</span></span
          >
        </button>
        <span class="budget-shared-hint">общий · все с доступом видят одни операции</span>
      </div>
      <div class="header-end">
        <AppSectionNav active="budget" />
        <div class="header-user">
          <span v-if="auth.user" class="user">{{ auth.user.email }}</span>
          <button
            type="button"
            class="theme-toggle"
            :aria-label="themeLabel"
            :title="themeLabel"
            @click="cycleTheme"
          >
            <span class="theme-toggle-glyph" aria-hidden="true">{{ themeIcon }}</span>
          </button>
          <button type="button" class="btn ghost" @click="logout">Выйти</button>
        </div>
      </div>
    </header>
    <iframe class="budget-frame" src="/budget-app/index.html" title="Семейный бюджет" />
  </div>
</template>

<style scoped>
.budget-workspace {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--bg);
}
.workspace-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem 1rem;
  padding: 0.5rem 1rem 0.55rem;
  border-bottom: 1px solid var(--border);
  background: var(--surface-translucent);
  backdrop-filter: blur(10px);
  flex-shrink: 0;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  min-width: 0;
}
.logo-home-btn {
  display: inline-flex;
  background: transparent;
  border: none;
  padding: 0;
  cursor: pointer;
  font: inherit;
}
.logo-wordmark {
  font-family: 'Sora', 'Inter', system-ui, sans-serif;
  font-size: var(--fs-xl);
  font-weight: 700;
  letter-spacing: -0.055em;
  color: var(--text-1);
}
.logo-brand {
  display: inline-flex;
}
.logo-brand-accent {
  color: var(--accent-text);
}
.logo-brand-dash {
  color: var(--text-4);
}
.budget-shared-hint {
  font-size: var(--fs-2xs);
  color: var(--text-4);
}
.header-user {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  padding-left: 0.85rem;
  border-left: 1px solid var(--border);
  flex-shrink: 0;
}
.user {
  font-family: inherit;
  font-size: var(--fs-2xs);
  font-weight: 400;
  line-height: var(--lh-tight);
  color: var(--text-muted);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.budget-frame {
  flex: 1 1 auto;
  width: 100%;
  min-height: 0;
  border: 0;
  background: #f5f5f7;
}
</style>
