<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { notesApi } from '../api/client'
import type { Note } from '../api/types'
import { calendarDayKeyFromDate, fmtCompactMsk, reminderCalendarDayKeyFromIso } from '../utils/datetime'
import { DEFAULT_NOTE_TITLE } from '../utils/noteDefaults'
import { remindersEqual } from '../utils/noteListSync'

const props = defineProps<{
  disabled?: boolean
  refreshSignal?: number
  /** ID заметок из текущей выборки списка — в фильтре: приглушённый синий; вне фильтра: приглушённый красный */
  scopeNoteIds?: string[]
  /** Показывать «n из N» по напоминаниям при сужении списка метками / поиском (N — все напоминания в периоде). */
  fractionFromListFilter?: boolean
  /** В боковой панели заголовок «Календарь» уже снаружи — дублировать не нужно */
  embedInSidebar?: boolean
  /** Активный фильтр списка заметок по дате (YYYY-MM-DD). */
  selectedDayFilterKey?: string | null
}>()
const emit = defineEmits<{
  openNote: [id: string]
  toggleDayFilter: [payload: { key: string; date: Date }]
}>()

/** Высота прокручиваемой области списка напоминаний (день / колонки недели). */
const DAY_LIST_H_KEY = 'rem-cal-list-h'
const DAY_LIST_H_DEFAULT = 220
const DAY_LIST_H_MIN = 96
const DAY_LIST_H_MAX = 720

function readListHeight(): number {
  try {
    const raw = localStorage.getItem(DAY_LIST_H_KEY)
    if (!raw) return DAY_LIST_H_DEFAULT
    const n = parseInt(raw, 10)
    if (Number.isNaN(n)) return DAY_LIST_H_DEFAULT
    return Math.min(DAY_LIST_H_MAX, Math.max(DAY_LIST_H_MIN, n))
  } catch {
    return DAY_LIST_H_DEFAULT
  }
}

function persistListHeight(n: number) {
  try {
    localStorage.setItem(DAY_LIST_H_KEY, String(n))
  } catch {
    /* */
  }
}

const listAreaHeightPx = ref(readListHeight())
let resizeUnbind: (() => void) | null = null

function onListResizeDown(e: MouseEvent) {
  e.preventDefault()
  const startY = e.clientY
  const startH = listAreaHeightPx.value
  const onMove = (ev: MouseEvent) => {
    const dy = ev.clientY - startY
    listAreaHeightPx.value = Math.min(
      DAY_LIST_H_MAX,
      Math.max(DAY_LIST_H_MIN, startH + dy)
    )
  }
  const onUp = () => {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    persistListHeight(listAreaHeightPx.value)
    resizeUnbind = null
  }
  resizeUnbind = onUp
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
  document.body.style.cursor = 'row-resize'
  document.body.style.userSelect = 'none'
}

onBeforeUnmount(() => {
  resizeUnbind?.()
})

type CalView = 'month' | 'week' | 'day'
const view = ref<CalView>('week')
const cursor = ref(new Date())

const scopeTintActive = computed(() => props.scopeNoteIds !== undefined)
const scopeSet = computed(() => new Set(props.scopeNoteIds ?? []))

function dotScopeClass(n: Note): Record<string, boolean> {
  if (!scopeTintActive.value) return {}
  return {
    'rem-dot--in-scope': scopeSet.value.has(n.id),
    'rem-dot--out-scope': !scopeSet.value.has(n.id),
  }
}

function dayItemScopeClass(n: Note): Record<string, boolean> {
  if (!scopeTintActive.value) return {}
  return {
    'rem-cal-dayitem--in-scope': scopeSet.value.has(n.id),
    'rem-cal-dayitem--out-scope': !scopeSet.value.has(n.id),
  }
}

const reminders = ref<Note[]>([])
const loading = ref(false)

function dayKeyLocal(iso: string): string {
  return reminderCalendarDayKeyFromIso(iso)
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
    if (reminders.value.length > 0) reminders.value = []
    return
  }
  const hadData = reminders.value.length > 0
  loading.value = !hadData
  try {
    const { from, to } = rangeForView()
    const next = await notesApi.listReminders({
      from: from.toISOString(),
      to: to.toISOString(),
    })
    if (!remindersEqual(reminders.value, next)) {
      reminders.value = next
    }
  } catch {
    if (hadData) {
      /* сохраняем предыдущие точки — без «мигания» пустым календарём */
    } else {
      reminders.value = []
    }
  } finally {
    loading.value = false
  }
}

const showInitialLoadHint = computed(() => loading.value && reminders.value.length === 0)
const showBackgroundRefresh = computed(() => loading.value && reminders.value.length > 0)

const reminderFractionLabel = computed(() => {
  if (!props.fractionFromListFilter || !scopeTintActive.value || loading.value) return ''
  const total = reminders.value.length
  if (total === 0) return ''
  let inScope = 0
  const s = scopeSet.value
  for (const n of reminders.value) {
    if (s.has(n.id)) inScope++
  }
  return `${inScope} из ${total}`
})

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

function fmtDayMonthShort(x: Date): string {
  return x
    .toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
    .replace(/\.$/, '')
    .trim()
}

const titleRange = computed(() => {
  const d = cursor.value
  if (view.value === 'day') {
    return d
      .toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'short' })
      .replace(/,/g, '')
      .trim()
  }
  if (view.value === 'week') {
    const { from, to } = rangeForView()
    const end = new Date(to.getTime() - 86400000)
    const sameMonth = from.getMonth() === end.getMonth() && from.getFullYear() === end.getFullYear()
    if (sameMonth) {
      const mo = from.toLocaleDateString('ru-RU', { month: 'short' }).replace(/\.$/, '')
      return `${from.getDate()}—${end.getDate()} ${mo}`
    }
    return `${fmtDayMonthShort(from)} — ${fmtDayMonthShort(end)}`
  }
  const y = d.getFullYear()
  const nowY = new Date().getFullYear()
  if (y !== nowY) {
    return d.toLocaleDateString('ru-RU', { month: 'short', year: '2-digit' }).replace(/\.$/, '')
  }
  return d.toLocaleDateString('ru-RU', { month: 'long' })
})

const titleRangeTooltip = computed(() => {
  const d = cursor.value
  if (view.value === 'day') {
    return d.toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
  }
  if (view.value === 'week') {
    const { from, to } = rangeForView()
    const end = new Date(to.getTime() - 86400000)
    const a = from.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
    const b = end.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
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
    const key = calendarDayKeyFromDate(d)
    out.push({ key, label: d.getDate(), inMonth, d })
  }
  return out
}

/** Недели месяца без полностью пустых строк (только «хвост» из чужих месяцев). */
const monthWeekRows = computed(() => {
  const flat = monthGrid()
  const rows: (typeof flat)[] = []
  for (let r = 0; r < 6; r++) {
    const row = flat.slice(r * 7, r * 7 + 7)
    if (row.some((c) => c.inMonth)) rows.push(row)
  }
  return rows
})

const weekDays = computed(() => {
  const { from } = rangeForView()
  const cells: { key: string; label: string; short: number; d: Date; titleFull: string }[] = []
  for (let i = 0; i < 7; i++) {
    const d = new Date(from.getTime() + i * 86400000)
    const key = calendarDayKeyFromDate(d)
    const label = d.toLocaleDateString('ru-RU', { weekday: 'short' }).replace(/\.$/, '')
    const titleFull = d.toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
    cells.push({ key, label, short: d.getDate(), d, titleFull })
  }
  return cells
})

const dayKeyCursor = computed(() => calendarDayKeyFromDate(cursor.value))

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
  const t = (n.title || DEFAULT_NOTE_TITLE).trim()
  return `${t} — ${fmtCompactMsk(n.reminder_at!)}`
}

function cellDateTitle(d: Date): string {
  const base = d.toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
  return isToday(d) ? `Сегодня, ${base}` : base
}

function isToday(d: Date): boolean {
  const t = new Date()
  return d.getFullYear() === t.getFullYear() && d.getMonth() === t.getMonth() && d.getDate() === t.getDate()
}

function isDayFilterSelected(key: string): boolean {
  return props.selectedDayFilterKey === key
}

function onDayFilterClick(key: string, d: Date, e: MouseEvent) {
  if ((e.target as Element).closest('.rem-dot')) return
  emit('toggleDayFilter', { key, date: d })
}

function dayFilterTitle(d: Date, hasReminders: boolean): string {
  const base = cellDateTitle(d)
  const hint = isDayFilterSelected(calendarDayKeyFromDate(d))
    ? 'Повторный клик — снять фильтр списка заметок'
    : 'Клик — фильтр списка заметок по напоминаниям на эту дату'
  if (!hasReminders) return `${base}. ${hint}`
  return `${base}. ${hint}`
}
</script>

<template>
  <div
    class="rem-cal"
    :class="{
      'rem-cal--disabled': disabled,
      'rem-cal--resizable': view === 'week',
      'rem-cal--embed': embedInSidebar,
    }"
    :style="{ '--rem-cal-list-h': listAreaHeightPx + 'px' }"
  >
    <div class="rem-cal-head">
      <span v-if="!embedInSidebar" class="rem-cal-title">Календарь</span>
      <div class="rem-cal-views">
        <button type="button" :class="{ on: view === 'day' }" @click="view = 'day'">День</button>
        <button type="button" :class="{ on: view === 'week' }" @click="view = 'week'">Неделя</button>
        <button type="button" :class="{ on: view === 'month' }" @click="view = 'month'">Месяц</button>
      </div>
    </div>
    <div class="rem-cal-nav">
      <button type="button" class="rem-cal-arrow" aria-label="Назад" title="Назад" @click="prev">‹</button>
      <span
        class="rem-cal-range rem-cal-range--pickable"
        :class="{ 'rem-cal-range--selected': isDayFilterSelected(dayKeyCursor) }"
        :title="dayFilterTitle(cursor, (byDay.get(dayKeyCursor)?.length ?? 0) > 0)"
        @click="onDayFilterClick(dayKeyCursor, cursor, $event)"
        >{{ titleRange }}</span
      >
      <button type="button" class="rem-cal-arrow" aria-label="Вперёд" title="Вперёд" @click="next">›</button>
      <button type="button" class="rem-cal-today" @click="today">Сегодня</button>
    </div>
    <p
      v-if="reminderFractionLabel"
      class="rem-cal-frac muted small"
      title="Сколько напоминаний попало в текущий список (метки, поиск) из всех в выбранном периоде календаря"
    >
      Напоминания: {{ reminderFractionLabel }}
    </p>
    <p v-if="showInitialLoadHint" class="rem-cal-hint muted small">Загрузка…</p>
    <div
      v-if="view === 'month'"
      class="rem-cal-month"
      :class="{ 'rem-cal-body--refreshing': showBackgroundRefresh }"
    >
      <div class="rem-cal-dow">
        <span v-for="w in ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']" :key="w">{{ w }}</span>
      </div>
      <div class="rem-cal-grid">
        <template v-for="(week, wi) in monthWeekRows" :key="'w' + wi">
          <div
            v-for="c in week"
            :key="c.key"
            class="rem-cal-cell"
            :class="{
              'rem-cal-cell--dots': c.inMonth && (byDay.get(c.key)?.length ?? 0) > 0,
              'rem-cal-cell--pickable': c.inMonth,
              'rem-cal-cell--selected': c.inMonth && isDayFilterSelected(c.key),
            }"
            :title="c.inMonth ? dayFilterTitle(c.d, (byDay.get(c.key)?.length ?? 0) > 0) : undefined"
            @click="c.inMonth ? onDayFilterClick(c.key, c.d, $event) : undefined"
          >
            <template v-if="c.inMonth">
              <span
                class="rem-cal-daynum"
                :class="{ 'rem-cal-daynum--today': isToday(c.d) }"
                :title="cellDateTitle(c.d)"
                >{{ c.label }}</span
              >
              <div v-if="byDay.get(c.key)?.length" class="rem-cal-dots">
                <span
                  v-for="n in (byDay.get(c.key) ?? []).slice(0, 6)"
                  :key="n.id"
                  class="rem-dot"
                  :class="dotScopeClass(n)"
                  :title="reminderDetailTitle(n)"
                  @click.stop="open(n.id)"
                />
                <span v-if="(byDay.get(c.key) ?? []).length > 6" class="rem-more"
                  >+{{ (byDay.get(c.key) ?? []).length - 6 }}</span
                >
              </div>
            </template>
          </div>
        </template>
      </div>
    </div>
    <div
      v-else-if="view === 'week'"
      class="rem-cal-week"
      :class="{ 'rem-cal-body--refreshing': showBackgroundRefresh }"
    >
      <div class="rem-cal-week-grid">
        <div
          v-for="c in weekDays"
          :key="c.key"
          class="rem-cal-wcol"
          :class="{
            'rem-cal-wcol--has': (byDay.get(c.key)?.length ?? 0) > 0,
            'rem-cal-wcol--pickable': true,
            'rem-cal-wcol--selected': isDayFilterSelected(c.key),
          }"
          :title="dayFilterTitle(c.d, (byDay.get(c.key)?.length ?? 0) > 0)"
          @click="onDayFilterClick(c.key, c.d, $event)"
        >
          <div
            class="rem-cal-whead"
            :class="{ 'rem-cal-whead--today': isToday(c.d) }"
            :title="isToday(c.d) ? `Сегодня, ${c.titleFull}` : c.titleFull"
          >
            {{ c.label }}<span class="rem-cal-wnum">{{ c.short }}</span>
          </div>
          <div class="rem-cal-wdots">
            <div v-if="(byDay.get(c.key) ?? []).length" class="rem-cal-dots rem-cal-dots--week">
              <span
                v-for="n in byDay.get(c.key) ?? []"
                :key="n.id"
                class="rem-dot"
                :class="dotScopeClass(n)"
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
    <div
      v-else-if="view === 'day'"
      class="rem-cal-dayview"
      :class="{ 'rem-cal-body--refreshing': showBackgroundRefresh }"
    >
      <ul v-if="daySlots.length" class="rem-cal-daylist">
        <li v-for="n in daySlots" :key="n.id">
          <button
            type="button"
            class="rem-cal-dayitem"
            :class="dayItemScopeClass(n)"
            @click="open(n.id)"
          >
            <span class="rem-cal-ntime">{{ fmtCompactMsk(n.reminder_at!) }}</span>
            <span class="rem-cal-nt">{{ n.title || DEFAULT_NOTE_TITLE }}</span>
          </button>
        </li>
      </ul>
      <p v-else class="muted small rem-cal-empty">Нет напоминаний в этот день</p>
    </div>
    <div
      v-if="view === 'week'"
      class="rem-cal-resize"
      title="Потяните — высота области с точками в колонках недели"
      @mousedown="onListResizeDown"
    />
  </div>
</template>

<style scoped>
.rem-cal {
  flex-shrink: 0;
  margin-bottom: 0.4rem;
  padding: 0.55rem 0.5rem 0.35rem;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--panel);
  box-shadow: var(--shadow-sm);
  font-family: inherit;
  font-size: var(--fs-xs);
  color: var(--text-2);
  --rem-cal-list-h: 220px;
}
.rem-cal--resizable {
  padding-bottom: 0.15rem;
}
.rem-cal--disabled {
  opacity: 0.45;
  pointer-events: none;
}
.rem-cal--embed {
  font-size: var(--fs-2xs);
  color: var(--text-3);
}
.rem-cal--embed .rem-cal-head {
  margin-bottom: 0.35rem;
}
.rem-cal-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.4rem;
  margin-bottom: 0.45rem;
  width: 100%;
}
.rem-cal-title {
  font-size: var(--fs-2xs);
  font-weight: 650;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}
.rem-cal-views {
  display: flex;
  flex: 1;
  min-width: 0;
  gap: 3px;
  padding: 2px;
  border-radius: 8px;
  background: var(--surface-wash);
}
.rem-cal-views button {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: inherit;
  font-size: var(--fs-2xs);
  font-weight: 500;
  padding: 0.2rem 0.35rem;
  border-radius: 6px;
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--text-muted);
}
.rem-cal-views button.on {
  background: var(--panel);
  color: var(--accent-text);
  font-weight: 600;
  box-shadow: 0 1px 2px var(--shadow-tint-weak);
}
.rem-cal-nav {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.3rem;
  margin-bottom: 0.45rem;
}
.rem-cal-frac {
  margin: -0.15rem 0 0.4rem;
  font-variant-numeric: tabular-nums;
}
.rem-cal-arrow {
  width: 1.35rem;
  height: 1.35rem;
  border: none;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  font-size: var(--fs-xs);
  line-height: 1;
  color: var(--text-muted);
  transition: background var(--dur-fast) var(--ease);
}
.rem-cal-arrow:hover {
  background: var(--list-row-hover);
  color: var(--accent-text);
}
.rem-cal-range {
  flex: 1;
  min-width: 0;
  font-size: var(--fs-2xs);
  font-weight: 500;
  color: var(--text-4);
  text-align: center;
}
.rem-cal-range--pickable {
  cursor: pointer;
  border-radius: 8px;
  padding: 0.12rem 0.25rem;
  transition:
    background var(--dur-fast) var(--ease),
    color var(--dur-fast) var(--ease);
}
.rem-cal-range--pickable:hover {
  background: var(--list-row-hover);
  color: var(--accent-text);
}
.rem-cal-range--selected {
  background: var(--accent-subtle);
  color: var(--accent-text);
  box-shadow: inset 0 0 0 1px var(--accent-border);
}
.rem-cal-today {
  font-family: inherit;
  font-size: var(--fs-2xs);
  font-weight: 500;
  padding: 0.2rem 0.4rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-4);
  cursor: pointer;
}
.rem-cal-today:hover {
  border-color: var(--accent-border);
  color: var(--accent-text);
}
.rem-cal-hint {
  margin: 0 0 0.35rem;
  font-size: var(--fs-2xs);
  color: var(--text-muted);
}
.rem-cal-body--refreshing {
  opacity: 0.92;
  transition: opacity var(--dur-base) var(--ease);
}
.rem-cal-dow {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
  margin-bottom: 4px;
  font-size: var(--fs-2xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-4);
  text-align: center;
}
.rem-cal-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 3px;
}
.rem-cal-cell {
  min-height: 2rem;
  border-radius: 8px;
  padding: 0.16rem 0.18rem;
  background: var(--list-row-hover);
  font-size: var(--fs-2xs);
  display: flex;
  flex-direction: column;
  gap: 2px;
  border: 1px solid transparent;
  transition: border-color var(--dur-fast) var(--ease);
}
.rem-cal-cell--dots:hover,
.rem-cal-cell--pickable {
  cursor: pointer;
}
.rem-cal-cell--pickable:hover {
  border-color: var(--accent-border-soft);
}
.rem-cal-cell--selected {
  border-color: var(--accent-border);
  background: var(--accent-subtle);
  box-shadow: inset 0 0 0 1px var(--accent-glow);
}
.rem-cal-daynum {
  font-size: var(--fs-2xs);
  font-weight: 600;
  color: var(--text-3);
}
.rem-cal-daynum--today {
  color: var(--accent-text);
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
.rem-dot--in-scope {
  background: var(--cal-in-scope);
  box-shadow: 0 0 0 1px var(--cal-in-scope-ring);
}
.rem-dot--out-scope {
  background: var(--cal-out-scope);
  box-shadow: 0 0 0 1px var(--cal-out-scope-ring);
}
.rem-more {
  font-size: var(--fs-2xs);
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
  border-radius: var(--radius-md);
  padding: 0.35rem 0.3rem 0.45rem;
  background: var(--bg);
  min-height: 4.25rem;
  display: flex;
  flex-direction: column;
}
.rem-cal-wcol--has {
  border-color: var(--accent-border-soft);
}
.rem-cal-wcol--pickable {
  cursor: pointer;
}
.rem-cal-wcol--pickable:hover {
  border-color: var(--accent-border);
  box-shadow: var(--shadow-sm);
}
.rem-cal-wcol--selected {
  border-color: var(--accent-border);
  background: var(--accent-subtle);
  box-shadow: inset 0 0 0 1px var(--accent-glow);
}
.rem-cal-whead {
  font-size: var(--fs-2xs);
  font-weight: 600;
  color: var(--text-4);
  margin-bottom: 0.3rem;
  display: flex;
  flex-direction: column;
  gap: 1px;
  line-height: var(--lh-tight);
}
.rem-cal-wnum {
  font-size: var(--fs-2xs);
  font-weight: 600;
  color: var(--text-3);
}
.rem-cal-whead--today,
.rem-cal-whead--today .rem-cal-wnum {
  color: var(--accent-text);
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
  max-height: var(--rem-cal-list-h, 220px);
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
  font-size: var(--fs-2xs);
  color: var(--note-list-meta);
  font-variant-numeric: tabular-nums;
}
.rem-cal-daylist {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: var(--rem-cal-list-h, 220px);
  min-height: 0;
  overflow-y: auto;
}
/** День: показываем все напоминания по высоте, без внутреннего скролла (высота по содержимому). */
.rem-cal-dayview .rem-cal-daylist {
  max-height: none;
  overflow-y: visible;
  min-height: 0;
}
.rem-cal-resize {
  height: 9px;
  margin: 0.4rem -0.35rem 0;
  border-radius: 6px;
  cursor: row-resize;
  flex-shrink: 0;
  background: var(--surface-wash);
  border: 1px solid transparent;
  transition:
    background var(--dur-fast) var(--ease),
    border-color var(--dur-fast) var(--ease);
}
.rem-cal-resize:hover {
  background: var(--accent-subtle-hover);
  border-color: var(--accent-border-soft);
}
.rem-cal-resize:active {
  background: var(--accent-subtle-strong);
}
.rem-cal-dayitem {
  width: 100%;
  text-align: left;
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.45rem 0.5rem;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--panel);
  cursor: pointer;
  font-family: inherit;
  font-size: var(--fs-xs);
  margin-bottom: 0.35rem;
  transition:
    border-color var(--dur-fast) var(--ease),
    box-shadow var(--dur-fast) var(--ease);
}
.rem-cal-dayitem:hover {
  border-color: var(--accent-border);
  box-shadow: var(--shadow-sm);
}
.rem-cal-dayitem--in-scope {
  border-color: var(--cal-in-scope-border);
  background: var(--cal-in-scope-subtle);
}
.rem-cal-dayitem--in-scope:hover {
  border-color: var(--cal-in-scope-border-strong);
}
.rem-cal-dayitem--out-scope {
  border-color: var(--cal-out-scope-border);
  background: var(--cal-out-scope-subtle);
}
.rem-cal-dayitem--out-scope:hover {
  border-color: var(--cal-out-scope-border-strong);
}
.rem-cal-empty {
  margin: 0.45rem 0;
  font-size: var(--fs-2xs);
  color: var(--text-muted);
}
</style>
