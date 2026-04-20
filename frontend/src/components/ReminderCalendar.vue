<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { notesApi } from '../api/client'
import type { Note } from '../api/types'
import { fmtCompactMsk } from '../utils/datetime'

const props = defineProps<{ disabled?: boolean; refreshSignal?: number }>()
const emit = defineEmits<{ openNote: [id: string] }>()

type CalView = 'month' | 'week' | 'day'
const view = ref<CalView>('month')
const cursor = ref(new Date())

const reminders = ref<Note[]>([])
const loading = ref(false)

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

function dayKeyLocal(iso: string): string {
  const d = new Date(iso)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function rangeForView(): { from: Date; to: Date } {
  const d = cursor.value
  if (view.value === 'day') {
    const from = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0)
    const to = new Date(from.getTime() + 86400000)
    return { from, to }
  }
  if (view.value === 'week') {
    const day = d.getDay()
    const diff = (day + 6) % 7
    const from = new Date(d.getFullYear(), d.getMonth(), d.getDate() - diff, 0, 0, 0, 0)
    const to = new Date(from.getTime() + 7 * 86400000)
    return { from, to }
  }
  const from = new Date(d.getFullYear(), d.getMonth(), 1, 0, 0, 0, 0)
  const to = new Date(d.getFullYear(), d.getMonth() + 1, 1, 0, 0, 0, 0)
  return { from, to }
}

async function loadReminders() {
  if (props.disabled) {
    reminders.value = []
    return
  }
  loading.value = true
  try {
    const { from, to } = rangeForView()
    reminders.value = await notesApi.listReminders({
      from: from.toISOString(),
      to: to.toISOString(),
    })
  } catch {
    reminders.value = []
  } finally {
    loading.value = false
  }
}

watch(
  [cursor, view, () => props.disabled, () => props.refreshSignal],
  () => void loadReminders(),
  { immediate: true }
)

const byDay = computed(() => {
  const m = new Map<string, Note[]>()
  for (const n of reminders.value) {
    if (!n.reminder_at) continue
    const k = dayKeyLocal(n.reminder_at)
    const arr = m.get(k) ?? []
    arr.push(n)
    m.set(k, arr)
  }
  return m
})

const titleRange = computed(() => {
  const d = cursor.value
  if (view.value === 'day') {
    return d.toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
  }
  if (view.value === 'week') {
    const { from, to } = rangeForView()
    const a = from.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
    const b = new Date(to.getTime() - 1).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' })
    return `${a} — ${b}`
  }
  return d.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' })
})

function prev() {
  const d = cursor.value
  if (view.value === 'day') {
    cursor.value = new Date(d.getFullYear(), d.getMonth(), d.getDate() - 1)
  } else if (view.value === 'week') {
    cursor.value = new Date(d.getFullYear(), d.getMonth(), d.getDate() - 7)
  } else {
    cursor.value = new Date(d.getFullYear(), d.getMonth() - 1, 1)
  }
}

function next() {
  const d = cursor.value
  if (view.value === 'day') {
    cursor.value = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1)
  } else if (view.value === 'week') {
    cursor.value = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 7)
  } else {
    cursor.value = new Date(d.getFullYear(), d.getMonth() + 1, 1)
  }
}

function today() {
  cursor.value = new Date()
}

function monthGrid(): { key: string; label: number; inMonth: boolean; d: Date }[] {
  const y = cursor.value.getFullYear()
  const mo = cursor.value.getMonth()
  const first = new Date(y, mo, 1)
  const startPad = (first.getDay() + 6) % 7
  const out: { key: string; label: number; inMonth: boolean; d: Date }[] = []
  const start = new Date(y, mo, 1 - startPad)
  for (let i = 0; i < 42; i++) {
    const d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i)
    const inMonth = d.getMonth() === mo
    const key = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
    out.push({ key, label: d.getDate(), inMonth, d })
  }
  return out
}

const weekDays = computed(() => {
  const { from } = rangeForView()
  const cells: { key: string; label: string; short: number; d: Date }[] = []
  for (let i = 0; i < 7; i++) {
    const d = new Date(from.getTime() + i * 86400000)
    const key = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
    const label = d.toLocaleDateString('ru-RU', { weekday: 'short' })
    cells.push({ key, label, short: d.getDate(), d })
  }
  return cells
})

const dayKeyCursor = computed(() => {
  const d = cursor.value
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
})

const daySlots = computed(() => {
  if (view.value !== 'day') return []
  const list = byDay.value.get(dayKeyCursor.value) ?? []
  return list.sort((a, b) => {
    const ta = new Date(a.reminder_at || 0).getTime()
    const tb = new Date(b.reminder_at || 0).getTime()
    return ta - tb
  })
})

function open(id: string) {
  emit('openNote', id)
}

/** Подпись для точки в сетке и для title при наведении (заголовок — дата и время). */
function reminderDetailTitle(n: Note): string {
  const t = (n.title || 'Без названия').trim()
  return `${t} — ${fmtCompactMsk(n.reminder_at!)}`
}
</script>

<template>
  <div class="rem-cal" :class="{ 'rem-cal--disabled': disabled }">
    <div class="rem-cal-head">
      <span class="rem-cal-title">Календарь</span>
      <div class="rem-cal-views">
        <button type="button" :class="{ on: view === 'day' }" @click="view = 'day'">День</button>
        <button type="button" :class="{ on: view === 'week' }" @click="view = 'week'">Неделя</button>
        <button type="button" :class="{ on: view === 'month' }" @click="view = 'month'">Месяц</button>
      </div>
    </div>
    <div class="rem-cal-nav">
      <button type="button" class="rem-cal-arrow" title="Назад" @click="prev">‹</button>
      <span class="rem-cal-range">{{ titleRange }}</span>
      <button type="button" class="rem-cal-arrow" title="Вперёд" @click="next">›</button>
      <button type="button" class="rem-cal-today" @click="today">Сегодня</button>
    </div>
    <p v-if="loading" class="rem-cal-hint muted small">Загрузка…</p>
    <div v-else-if="view === 'month'" class="rem-cal-month">
      <div class="rem-cal-dow">
        <span v-for="w in ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']" :key="w">{{ w }}</span>
      </div>
      <div class="rem-cal-grid">
        <div
          v-for="c in monthGrid()"
          :key="c.key"
          class="rem-cal-cell"
          :class="{ 'rem-cal-cell--muted': !c.inMonth, 'rem-cal-cell--dots': (byDay.get(c.key)?.length ?? 0) > 0 }"
        >
          <span class="rem-cal-daynum">{{ c.label }}</span>
          <div v-if="byDay.get(c.key)?.length" class="rem-cal-dots">
            <span
              v-for="n in (byDay.get(c.key) ?? []).slice(0, 3)"
              :key="n.id"
              class="rem-dot"
              :title="reminderDetailTitle(n)"
              @click.stop="open(n.id)"
            />
            <span v-if="(byDay.get(c.key) ?? []).length > 3" class="rem-more"
              >+{{ (byDay.get(c.key) ?? []).length - 3 }}</span
            >
          </div>
        </div>
      </div>
    </div>
    <div v-else-if="view === 'week'" class="rem-cal-week">
      <div class="rem-cal-week-grid">
        <div
          v-for="c in weekDays"
          :key="c.key"
          class="rem-cal-wcol"
          :class="{ 'rem-cal-wcol--has': (byDay.get(c.key)?.length ?? 0) > 0 }"
        >
          <div class="rem-cal-whead">{{ c.label }}<span class="rem-cal-wnum">{{ c.short }}</span></div>
          <div class="rem-cal-wdots">
            <div v-if="(byDay.get(c.key) ?? []).length" class="rem-cal-dots rem-cal-dots--week">
              <span
                v-for="n in byDay.get(c.key) ?? []"
                :key="n.id"
                class="rem-dot"
                :title="reminderDetailTitle(n)"
                role="button"
                tabindex="0"
                @click.stop="open(n.id)"
                @keydown.enter.prevent="open(n.id)"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
    <div v-else class="rem-cal-dayview">
      <ul v-if="daySlots.length" class="rem-cal-daylist">
        <li v-for="n in daySlots" :key="n.id">
          <button type="button" class="rem-cal-dayitem" @click="open(n.id)">
            <span class="rem-cal-ntime">{{ fmtCompactMsk(n.reminder_at!) }}</span>
            <span class="rem-cal-nt">{{ n.title || 'Без названия' }}</span>
          </button>
        </li>
      </ul>
      <p v-else class="muted small rem-cal-empty">Нет напоминаний в этот день</p>
    </div>
  </div>
</template>

<style scoped>
.rem-cal {
  flex-shrink: 0;
  margin-bottom: 0.4rem;
  padding: 0.55rem 0.5rem 0.6rem;
  border-radius: var(--radius-md, 10px);
  border: 1px solid var(--border);
  background: var(--panel);
  box-shadow: var(--shadow-soft, 0 1px 3px rgba(15, 23, 42, 0.06));
  font-family: inherit;
  font-size: 0.8125rem;
  color: #334155;
}
.rem-cal--disabled {
  opacity: 0.45;
  pointer-events: none;
}
.rem-cal-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.4rem;
  margin-bottom: 0.45rem;
}
.rem-cal-title {
  font-size: 0.6875rem;
  font-weight: 650;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}
.rem-cal-views {
  display: inline-flex;
  gap: 3px;
  padding: 2px;
  border-radius: 8px;
  background: rgba(148, 163, 184, 0.12);
}
.rem-cal-views button {
  font-family: inherit;
  font-size: 0.6875rem;
  font-weight: 500;
  padding: 0.2rem 0.42rem;
  border-radius: 6px;
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--text-muted);
}
.rem-cal-views button.on {
  background: var(--panel);
  color: var(--accent);
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
}
.rem-cal-nav {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.3rem;
  margin-bottom: 0.45rem;
}
.rem-cal-arrow {
  width: 1.5rem;
  height: 1.5rem;
  border: none;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  font-size: 0.95rem;
  line-height: 1;
  color: var(--text-muted);
  transition: background 0.12s ease;
}
.rem-cal-arrow:hover {
  background: var(--list-row-hover);
  color: var(--accent);
}
.rem-cal-range {
  flex: 1;
  min-width: 0;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--note-list-title);
  text-align: center;
}
.rem-cal-today {
  font-family: inherit;
  font-size: 0.6875rem;
  font-weight: 500;
  padding: 0.22rem 0.45rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: #475569;
  cursor: pointer;
}
.rem-cal-today:hover {
  border-color: rgba(37, 99, 235, 0.35);
  color: var(--accent);
}
.rem-cal-hint {
  margin: 0 0 0.35rem;
  font-size: 0.7rem;
  color: var(--text-muted);
}
.rem-cal-dow {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
  margin-bottom: 4px;
  font-size: 0.625rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--note-list-meta);
  text-align: center;
}
.rem-cal-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 3px;
}
.rem-cal-cell {
  min-height: 2.2rem;
  border-radius: 8px;
  padding: 0.18rem 0.2rem;
  background: var(--list-row-hover);
  font-size: 0.6875rem;
  display: flex;
  flex-direction: column;
  gap: 2px;
  border: 1px solid transparent;
  transition: border-color 0.12s ease;
}
.rem-cal-cell--dots:hover {
  border-color: rgba(37, 99, 235, 0.25);
}
.rem-cal-cell--muted {
  opacity: 0.4;
}
.rem-cal-daynum {
  font-weight: 600;
  color: var(--note-list-title);
}
.rem-cal-dots {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 3px;
}
.rem-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  cursor: pointer;
  flex-shrink: 0;
}
.rem-more {
  font-size: 0.55rem;
  color: var(--text-muted);
}
.rem-cal-week-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 6px;
}
.rem-cal-wcol {
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-md, 10px);
  padding: 0.35rem 0.3rem 0.45rem;
  background: var(--bg);
  min-height: 4.25rem;
  display: flex;
  flex-direction: column;
}
.rem-cal-wcol--has {
  border-color: rgba(37, 99, 235, 0.22);
}
.rem-cal-whead {
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 0.35rem;
  display: flex;
  flex-direction: column;
  gap: 1px;
  line-height: 1.25;
}
.rem-cal-wnum {
  font-size: 0.8125rem;
  font-weight: 700;
  color: var(--note-list-title);
}
.rem-cal-wdots {
  flex: 1;
  display: flex;
  align-items: stretch;
  justify-content: center;
  min-height: 1.5rem;
  min-width: 0;
  width: 100%;
}
.rem-cal-dots--week {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  align-content: flex-start;
  gap: 4px;
  width: 100%;
  max-height: 11rem;
  min-height: 0;
  overflow-y: auto;
  box-sizing: border-box;
  padding: 1px 0;
}
.rem-cal-daylist .rem-cal-nt {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--note-list-title);
}
.rem-cal-daylist .rem-cal-ntime {
  font-size: 0.65rem;
  color: var(--note-list-meta);
  font-variant-numeric: tabular-nums;
}
.rem-cal-daylist {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 220px;
  overflow-y: auto;
}
.rem-cal-dayitem {
  width: 100%;
  text-align: left;
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.45rem 0.5rem;
  border-radius: var(--radius-md, 10px);
  border: 1px solid var(--border);
  background: var(--panel);
  cursor: pointer;
  font-family: inherit;
  font-size: 0.78rem;
  margin-bottom: 0.35rem;
  transition:
    border-color 0.12s ease,
    box-shadow 0.12s ease;
}
.rem-cal-dayitem:hover {
  border-color: rgba(37, 99, 235, 0.35);
  box-shadow: var(--shadow-soft, 0 1px 3px rgba(15, 23, 42, 0.06));
}
.rem-cal-empty {
  margin: 0.45rem 0;
  font-size: 0.75rem;
  color: var(--text-muted);
}
</style>
