<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { isAxiosError } from 'axios'
import { useRoute, useRouter } from 'vue-router'
import { errMessage, habitsApi, publicHabitsApi } from '../api/client'
import type { Habit } from '../api/types'
import AppSectionNav from '../components/AppSectionNav.vue'
import { useAuthStore } from '../stores/auth'
import { useTheme } from '../composables/useTheme'

const ICONS = ['💧', '🏃', '📚', '🧘', '💊', '🍎', '✍️', '🧹', '🌙', '🎯', '🧠', '🚶']
const WEEK = [
  { id: 1, label: 'Пн' },
  { id: 2, label: 'Вт' },
  { id: 3, label: 'Ср' },
  { id: 4, label: 'Чт' },
  { id: 5, label: 'Пт' },
  { id: 6, label: 'Сб' },
  { id: 7, label: 'Вс' },
] as const

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const { label: themeLabel, icon: themeIcon, cycleTheme } = useTheme()
const isPublic = computed(() => route.name === 'public-habits')
const publicToken = computed(() => String(route.params.token || '').trim())
const ownerName = ref('')
const shareToken = ref('')
const shareBusy = ref(false)
const shareCopied = ref(false)
const shareOpen = ref(false)
const habits = ref<Habit[]>([])
const loading = ref(true)
const error = ref('')
const busyId = ref<string | null>(null)

const shareUrl = computed(() => {
  if (!shareToken.value || typeof window === 'undefined') return ''
  return `${window.location.origin}${router.resolve({ name: 'public-habits', params: { token: shareToken.value } }).href}`
})

async function loadShare() {
  if (isPublic.value) return
  try {
    const row = await habitsApi.getPublicLink()
    shareToken.value = row.token
  } catch (e) {
    if (isAxiosError(e) && e.response?.status === 404) shareToken.value = ''
    else shareToken.value = ''
  }
}

async function createShare() {
  shareBusy.value = true
  error.value = ''
  try {
    const row = await habitsApi.createPublicLink()
    shareToken.value = row.token
  } catch (e) {
    error.value = errMessage(e)
  } finally {
    shareBusy.value = false
  }
}

async function toggleShare() {
  if (shareOpen.value) {
    shareOpen.value = false
    return
  }
  shareOpen.value = true
  if (!shareToken.value) await createShare()
}

async function revokeShare() {
  if (!confirm('Закрыть доступ по ссылке? Открыть её уже будет нельзя.')) return
  shareBusy.value = true
  error.value = ''
  try {
    await habitsApi.deletePublicLink()
    shareToken.value = ''
    shareCopied.value = false
    shareOpen.value = false
  } catch (e) {
    error.value = errMessage(e)
  } finally {
    shareBusy.value = false
  }
}

async function copyShare() {
  if (!shareUrl.value) return
  try {
    await navigator.clipboard.writeText(shareUrl.value)
    shareCopied.value = true
    setTimeout(() => {
      shareCopied.value = false
    }, 2000)
  } catch {
    error.value = 'Не удалось скопировать ссылку'
  }
}
function localIso(d = new Date()) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function addDaysIso(iso: string, days: number) {
  const [y, m, d] = iso.split('-').map(Number)
  return localIso(new Date(y, m - 1, d + days))
}

function startOfWeekMonday(d = new Date()) {
  const dt = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const fromMonday = (dt.getDay() + 6) % 7
  dt.setDate(dt.getDate() - fromMonday)
  return localIso(dt)
}

/** Две недели: понедельник текущей недели … +13 дней. */
const RANGE_EXTRA_DAYS = 13
const RANGE_MAX = 62

function defaultRange() {
  const from = startOfWeekMonday()
  return { from, to: addDaysIso(from, RANGE_EXTRA_DAYS) }
}

const _def = defaultRange()
const rangeFrom = ref(_def.from)
const rangeTo = ref(_def.to)

function onRangeFromChange() {
  rangeTo.value = addDaysIso(rangeFrom.value, RANGE_EXTRA_DAYS)
}

function onRangeToChange() {
  if (rangeTo.value < rangeFrom.value) {
    rangeFrom.value = rangeTo.value
  }
  if (addDaysIso(rangeFrom.value, RANGE_MAX - 1) < rangeTo.value) {
    rangeTo.value = addDaysIso(rangeFrom.value, RANGE_MAX - 1)
  }
}

const rangeLen = computed(() => {
  const from = rangeFrom.value
  const to = rangeTo.value
  if (!from || !to || to < from) return 0
  let n = 0
  let cur = from
  while (cur <= to && n < RANGE_MAX + 2) {
    n += 1
    cur = addDaysIso(cur, 1)
  }
  return n
})

const draftTitle = ref('')
const draftIcon = ref('💧')
const draftDays = ref<number[]>([1, 2, 3, 4, 5])
const draftTarget = ref(21)
const draftStartsOn = ref(localIso())
const creating = ref(false)
const editingId = ref<string | null>(null)
const editTitle = ref('')
const editIcon = ref('')
const editDays = ref<number[]>([])
const editTarget = ref(10)
const editStartsOn = ref(localIso())
const editSort = ref(1)

function weekdayLabel(iso: string) {
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(y, m - 1, d)
  return ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'][(dt.getDay() + 6) % 7]!
}

function dayNum(iso: string) {
  return Number(iso.slice(8, 10))
}

const todayIso = computed(() => habits.value[0]?.today || localIso())

type BoardCol = { iso: string; num: number; label: string; isToday: boolean }

const boardCols = computed((): BoardCol[] => {
  const from = rangeFrom.value
  const to = rangeTo.value
  if (!from || !to || to < from) return []
  const out: BoardCol[] = []
  let cur = from
  let guard = 0
  while (cur <= to && guard < RANGE_MAX) {
    out.push({
      iso: cur,
      num: dayNum(cur),
      label: weekdayLabel(cur),
      isToday: cur === todayIso.value,
    })
    cur = addDaysIso(cur, 1)
    guard += 1
  }
  return out
})

function slotMap(h: Habit) {
  return new Map(h.slots.map((s) => [s.day, s]))
}

type CellKind = 'skip' | 'empty' | 'done' | 'missed'

function slotKind(s: Habit['slots'][number] | undefined): CellKind {
  if (!s) return 'skip'
  if (s.state === 'done' || s.state === 'missed') return s.state
  return 'empty'
}

function cellKind(h: Habit, iso: string): CellKind {
  return slotKind(slotMap(h).get(iso))
}

const avgPercent = computed(() => {
  if (!habits.value.length) return 0
  return Math.round(habits.value.reduce((s, h) => s + h.percent, 0) / habits.value.length)
})

const avgSmile = computed(() => {
  const p = avgPercent.value
  const steps: [number, string][] = [
    [0, '🙂'],
    [17, '😊'],
    [34, '😄'],
    [50, '😁'],
    [67, '🥰'],
    [84, '🥳'],
    [100, '🤩'],
  ]
  let emo = '🙂'
  for (const [n, e] of steps) if (p >= n) emo = e
  return emo
})

function logout() {
  auth.logout()
  void router.push('/login')
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    if (isPublic.value) {
      const data = await publicHabitsApi.get(publicToken.value)
      habits.value = sortedHabits(data.habits)
      ownerName.value = data.owner_name
    } else {
      habits.value = sortedHabits(await habitsApi.list())
    }
  } catch (e) {
    error.value = errMessage(e)
  } finally {
    loading.value = false
  }
}

function toggleDraftDay(id: number) {
  const set = new Set(draftDays.value)
  if (set.has(id)) set.delete(id)
  else set.add(id)
  const next = [...set].sort((a, b) => a - b)
  if (next.length) draftDays.value = next
}

function toggleEditDay(id: number) {
  const set = new Set(editDays.value)
  if (set.has(id)) set.delete(id)
  else set.add(id)
  const next = [...set].sort((a, b) => a - b)
  if (next.length) editDays.value = next
}

async function createHabit() {
  const title = draftTitle.value.trim()
  if (!title || creating.value) return
  creating.value = true
  error.value = ''
  try {
    const row = await habitsApi.create({
      title,
      icon: draftIcon.value,
      weekdays: draftDays.value,
      target_days: draftTarget.value,
      starts_on: draftStartsOn.value,
    })
    habits.value = sortedHabits([...habits.value, row])
    draftTitle.value = ''
  } catch (e) {
    error.value = errMessage(e)
  } finally {
    creating.value = false
  }
}

function sortedHabits(list: Habit[]) {
  return [...list].sort((a, b) => {
    const ao = a.sort_order ?? 0
    const bo = b.sort_order ?? 0
    if (ao !== bo) return ao - bo
    return String(a.created_at).localeCompare(String(b.created_at))
  })
}

function startEdit(h: Habit) {
  if (editingId.value === h.id) {
    cancelEdit()
    return
  }
  editingId.value = h.id
  editTitle.value = h.title
  editIcon.value = h.icon || '💧'
  editDays.value = [...h.weekdays]
  editTarget.value = h.target_days
  editStartsOn.value = h.starts_on || localIso()
  editSort.value = Math.max(1, Number(h.sort_order) || 1)
}

function cancelEdit() {
  editingId.value = null
}

async function saveEdit(id: string) {
  const title = editTitle.value.trim()
  if (!title) return
  busyId.value = id
  try {
    const row = await habitsApi.update(id, {
      title,
      icon: editIcon.value,
      weekdays: editDays.value,
      target_days: editTarget.value,
      starts_on: editStartsOn.value,
      sort_order: Math.max(1, Math.round(Number(editSort.value) || 1)),
    })
    habits.value = sortedHabits(habits.value.map((h) => (h.id === id ? row : h)))
    editingId.value = null
  } catch (e) {
    error.value = errMessage(e)
  } finally {
    busyId.value = null
  }
}

async function removeHabit(h: Habit) {
  if (!confirm(`Удалить привычку «${h.title}»?`)) return
  busyId.value = h.id
  try {
    await habitsApi.remove(h.id)
    habits.value = habits.value.filter((x) => x.id !== h.id)
    if (editingId.value === h.id) editingId.value = null
  } catch (e) {
    error.value = errMessage(e)
  } finally {
    busyId.value = null
  }
}

function replaceHabit(row: Habit) {
  habits.value = habits.value.map((h) => (h.id === row.id ? row : h))
}

type BoardCell = { iso: string; kind: CellKind; comment: string; title: string }
type BoardRow = { habit: Habit; cells: BoardCell[] }

/**
 * Готовая сетка доски. В шаблоне на каждую ячейку вызывались `cellKind`,
 * `cellComment` и `cellTitle` — до девяти раз, и каждый из них строил `Map`
 * из всех отметок привычки заново. На 20 привычках за две недели это были
 * тысячи лишних построений Map на один рендер.
 */
const boardRows = computed<BoardRow[]>(() => {
  const cols = boardCols.value
  return habits.value.map((h) => {
    const byDay = slotMap(h)
    return {
      habit: h,
      cells: cols.map((col) => {
        const comment = String(byDay.get(col.iso)?.comment || '').trim()
        return {
          iso: col.iso,
          kind: slotKind(byDay.get(col.iso)),
          comment,
          title: comment ? `${col.iso} — ${comment}` : col.iso,
        }
      }),
    }
  })
})

function cellComment(h: Habit, iso: string) {
  return String(slotMap(h).get(iso)?.comment || '').trim()
}

const noteHabitId = ref<string | null>(null)
const noteDay = ref('')
const noteTitle = ref('')
const noteDraft = ref('')
const noteBusy = ref(false)

function openNote(h: Habit, iso: string, ev?: Event) {
  ev?.preventDefault()
  if (cellKind(h, iso) === 'skip') return
  noteHabitId.value = h.id
  noteDay.value = iso
  noteTitle.value = h.title
  noteDraft.value = cellComment(h, iso)
}

function closeNote() {
  noteHabitId.value = null
  noteDay.value = ''
  noteDraft.value = ''
}

async function saveNote() {
  if (!noteHabitId.value || isPublic.value || noteBusy.value) return
  noteBusy.value = true
  error.value = ''
  try {
    replaceHabit(await habitsApi.setDay(noteHabitId.value, { day: noteDay.value, comment: noteDraft.value }))
    closeNote()
  } catch (e) {
    error.value = errMessage(e)
  } finally {
    noteBusy.value = false
  }
}

async function onBoardClick(h: Habit, iso: string) {
  if (isPublic.value) return
  const kind = cellKind(h, iso)
  if (kind === 'skip' || busyId.value) return
  const status = kind === 'empty' ? 'done' : kind === 'done' ? 'missed' : 'clear'
  busyId.value = h.id
  error.value = ''
  try {
    const note = cellComment(h, iso)
    replaceHabit(
      await habitsApi.setDay(h.id, {
        day: iso,
        status,
        ...(note ? { comment: note } : {}),
      })
    )
  } catch (e) {
    error.value = errMessage(e)
  } finally {
    busyId.value = null
  }
}

onMounted(() => {
  void load()
  void loadShare()
})
</script>

<template>
  <div class="workspace">
    <header class="workspace-header">
      <div class="header-left">
        <button
          type="button"
          class="logo logo-wordmark logo-home-btn"
          lang="ru"
          @click="isPublic ? undefined : router.push({ name: 'notes' })"
        >
          <span class="logo-brand"
            ><span class="logo-brand-accent">Em</span><span class="logo-brand-dash">-</span><span>Note</span></span
          >
        </button>
        <span v-if="isPublic" class="header-sub">Только просмотр</span>
      </div>
      <div class="header-end">
        <AppSectionNav v-if="!isPublic" active="habits" />
        <div class="header-user">
          <span v-if="!isPublic && auth.user" class="user">{{ auth.user.email }}</span>
          <span v-else-if="isPublic" class="user">{{ ownerName }}</span>
          <button
            type="button"
            class="theme-toggle"
            :aria-label="themeLabel"
            :title="themeLabel"
            @click="cycleTheme"
          >
            <span class="theme-toggle-glyph" aria-hidden="true">{{ themeIcon }}</span>
          </button>
          <button v-if="!isPublic" type="button" class="btn ghost" @click="logout">Выйти</button>
        </div>
      </div>
    </header>

    <main class="page">
      <p v-if="error" class="err">{{ error }}</p>
      <p v-if="isPublic" class="public-hint">Только просмотр · сегодня — синяя колонка</p>

      <form v-if="!isPublic" class="composer" @submit.prevent="createHabit">
        <div class="icon-pick">
          <button
            v-for="ic in ICONS"
            :key="ic"
            type="button"
            class="icon-btn"
            :class="{ on: draftIcon === ic }"
            @click="draftIcon = ic"
          >
            {{ ic }}
          </button>
        </div>
        <input
          v-model="draftTitle"
          class="title-input"
          maxlength="200"
          placeholder="Название — например «Стакан воды»"
        />
        <div class="dow">
          <button
            v-for="d in WEEK"
            :key="d.id"
            type="button"
            class="dow-btn"
            :class="{ on: draftDays.includes(d.id) }"
            @click="toggleDraftDay(d.id)"
          >
            {{ d.label }}
          </button>
        </div>
        <label class="target-lab">
          Повторений
          <input v-model.number="draftTarget" class="target-input" type="number" min="1" max="60" />
        </label>
        <label class="target-lab">
          Старт
          <input v-model="draftStartsOn" class="date-input" type="date" />
        </label>
        <button type="submit" class="btn primary" :disabled="creating || !draftTitle.trim()">Добавить</button>
        <div class="composer-share">
          <button type="button" class="btn secondary" :class="{ on: shareOpen }" :disabled="shareBusy" @click="toggleShare">
            Поделиться
          </button>
        </div>
        <div class="hero-smile" :title="avgPercent + '%'">
          <span class="hero-emo">{{ avgSmile }}</span>
          <span class="hero-pct">{{ avgPercent }}%</span>
        </div>
      </form>
      <div v-if="!isPublic && shareOpen" class="share-box">
        <input class="share-url" type="text" readonly :value="shareUrl" @focus="($event.target as HTMLInputElement).select()" />
        <button type="button" class="btn secondary" @click="copyShare">{{ shareCopied ? 'Скопировано' : 'Копировать' }}</button>
        <button type="button" class="btn ghost" :disabled="shareBusy || !shareToken" @click="revokeShare">Закрыть доступ</button>
      </div>
      <div v-if="isPublic" class="public-mood">
        <div class="hero-smile" :title="avgPercent + '%'">
          <span class="hero-emo">{{ avgSmile }}</span>
          <span class="hero-pct">{{ avgPercent }}%</span>
        </div>
      </div>

      <p v-if="loading" class="muted">Загрузка…</p>
      <div v-else class="range-bar">
        <label class="target-lab">
          С
          <input v-model="rangeFrom" class="date-input" type="date" @change="onRangeFromChange" />
        </label>
        <label class="target-lab">
          По
          <input v-model="rangeTo" class="date-input" type="date" @change="onRangeToChange" />
        </label>
        <span class="range-len">{{ rangeLen }} дн.</span>
        <span v-if="!isPublic" class="range-hint">Правый клик по клетке — комментарий</span>
      </div>
      <p v-if="!loading && !habits.length" class="empty">
        {{ isPublic ? 'У автора пока нет привычек на этой доске.' : 'Например: пн–пт и 21 повторение. Сегодня сразу видно по подсвеченной колонке.' }}
      </p>

      <div v-if="habits.length" class="board-wrap">
        <div
          class="board"
          :style="{
            gridTemplateColumns: `max-content repeat(${boardCols.length}, minmax(1.85rem, 1fr))`,
          }"
        >
          <div class="b-head b-name">Привычка</div>
          <div
            v-for="col in boardCols"
            :key="col.iso"
            class="b-head b-col"
          >
            <span class="b-wd">{{ col.label }}</span>
            <span class="b-num">{{ col.num }}</span>
            <span v-if="col.isToday" class="b-today">сегодня</span>
          </div>
          <template v-for="row in boardRows" :key="row.habit.id">
            <div class="b-name-cell" :class="{ editing: editingId === row.habit.id }">
              <span class="hab-icon">{{ row.habit.icon || '💧' }}</span>
              <span class="hab-meta">
                <span class="hab-smile">{{ row.habit.stage_emoji }}</span>
                <span class="hab-count">{{ row.habit.done_count }}/{{ row.habit.target_days }}</span>
              </span>
              <span class="hab-title" :title="row.habit.title">{{ row.habit.title }}</span>
              <div v-if="!isPublic" class="hab-hover-acts">
                <button type="button" class="btn-mini" @click="startEdit(row.habit)">Изменить</button>
                <button type="button" class="btn-mini danger" @click="removeHabit(row.habit)">
                  Удалить
                </button>
              </div>
            </div>
            <button
              v-for="cell in row.cells"
              :key="row.habit.id + cell.iso"
              type="button"
              class="b-cell"
              :class="[`is-${cell.kind}`, { 'has-note': !!cell.comment }]"
              :disabled="cell.kind === 'skip' || busyId === row.habit.id"
              :title="cell.title"
              @click="onBoardClick(row.habit, cell.iso)"
              @contextmenu="openNote(row.habit, cell.iso, $event)"
            >
              <span v-if="cell.kind === 'done'" class="mark-sym ok">✓</span>
              <span v-else-if="cell.kind === 'missed'" class="mark-sym no">✕</span>
              <span v-else-if="cell.kind === 'empty'" class="box" />
              <span v-if="cell.comment" class="note-dot" aria-hidden="true" />
            </button>
            <div
              v-if="!isPublic && editingId === row.habit.id"
              class="edit-box b-edit"
              :style="{ gridColumn: '1 / -1' }"
            >
              <div class="icon-pick">
                <button
                  v-for="ic in ICONS"
                  :key="ic"
                  type="button"
                  class="icon-btn"
                  :class="{ on: editIcon === ic }"
                  @click="editIcon = ic"
                >
                  {{ ic }}
                </button>
              </div>
              <input v-model="editTitle" class="title-input" maxlength="200" />
              <div class="dow">
                <button
                  v-for="d in WEEK"
                  :key="d.id"
                  type="button"
                  class="dow-btn"
                  :class="{ on: editDays.includes(d.id) }"
                  @click="toggleEditDay(d.id)"
                >
                  {{ d.label }}
                </button>
              </div>
              <label class="target-lab">
                Повторений
                <input v-model.number="editTarget" class="target-input" type="number" min="1" max="60" />
              </label>
              <label class="target-lab">
                Старт
                <input v-model="editStartsOn" class="date-input" type="date" />
              </label>
              <label class="target-lab">
                Порядок
                <input v-model.number="editSort" class="target-input" type="number" min="1" max="999" />
              </label>
              <div class="edit-actions">
                <button type="button" class="btn primary" @click="saveEdit(row.habit.id)">
                  Сохранить
                </button>
                <button type="button" class="btn ghost" @click="cancelEdit">Отмена</button>
              </div>
            </div>
          </template>
        </div>
      </div>

      <div v-if="noteHabitId" class="note-mask" @click.self="closeNote">
        <div class="note-pop" role="dialog" aria-label="Комментарий к дню">
          <p class="note-head">{{ noteTitle }} · {{ noteDay }}</p>
          <textarea
            v-model="noteDraft"
            class="note-text"
            rows="4"
            maxlength="2000"
            :readonly="isPublic"
            placeholder="Комментарий к этой отметке"
          />
          <div class="note-acts">
            <button v-if="!isPublic" type="button" class="btn primary" :disabled="noteBusy" @click="saveNote">Сохранить</button>
            <button type="button" class="btn ghost" @click="closeNote">{{ isPublic ? 'Закрыть' : 'Отмена' }}</button>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.workspace {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow-x: auto;
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
.header-sub {
  font-size: var(--fs-xs);
  font-weight: 650;
  color: var(--accent-text);
  background: var(--accent-subtle);
  padding: 0.18rem 0.5rem;
  border-radius: 999px;
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
.page {
  width: 100%;
  margin: 0;
  padding: 1.1rem 0.75rem 2.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  box-sizing: border-box;
}
.hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}
.hero h1 {
  margin: 0;
  font-size: var(--fs-xl);
  letter-spacing: -0.03em;
}
.hero-sub {
  margin: 0.25rem 0 0;
  color: var(--text-muted);
  font-size: var(--fs-sm);
}
.hero-right {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.55rem;
}
.date-pick {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  font-size: var(--fs-2xs);
  font-weight: 650;
  color: var(--text-muted);
}
.date-input {
  font: inherit;
  padding: 0.32rem 0.4rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface-1);
  color: var(--text-1);
}
.range-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.55rem 0.75rem;
}
.range-len {
  font-size: var(--fs-xs);
  font-weight: 650;
  color: var(--text-muted);
}
.range-hint {
  font-size: var(--fs-2xs);
  color: var(--text-muted);
}
.hero-smile {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
}
.hero-emo {
  font-size: 2.15rem;
  line-height: 1;
}
.hero-pct {
  font-size: var(--fs-2xs);
  font-weight: 700;
  color: var(--positive-text);
}
.board-wrap {
  width: 100%;
  overflow-x: auto;
}
.board {
  display: grid;
  gap: 0.18rem;
  align-items: stretch;
  min-width: min(100%, 52rem);
}
.b-head {
  font-size: var(--fs-2xs);
  font-weight: 700;
  color: var(--text-4);
  text-align: center;
}
.b-name {
  text-align: left;
  padding: 0 0.3rem;
  font-size: var(--fs-2xs);
}
.b-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.02rem;
  padding: 0.15rem 0 0.2rem;
  border-radius: 8px;
}
.b-wd {
  text-transform: uppercase;
}
.b-num {
  font-size: var(--fs-xs);
  color: var(--text-1);
}
.b-today {
  font-size: var(--fs-2xs);
  font-weight: 800;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}
.b-name-cell {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  width: max-content;
  max-width: none;
  min-height: 2.45rem;
  padding: 0.28rem 0.42rem;
  background: var(--surface-1);
  border-radius: 10px;
  border: 1px solid var(--border-subtle);
}
.hab-icon {
  flex-shrink: 0;
  font-size: var(--fs-xl);
  line-height: 1;
}
.hab-title {
  flex: 0 0 auto;
  font-weight: 750;
  font-size: var(--fs-md);
  line-height: var(--lh-tight);
  white-space: nowrap;
}
.hab-meta {
  display: flex;
  align-items: center;
  gap: 0.22rem;
  flex-shrink: 0;
}
.hab-smile {
  font-size: var(--fs-xl);
  line-height: 1;
}
.hab-count {
  font-size: var(--fs-xs);
  font-weight: 650;
  color: var(--text-muted);
  white-space: nowrap;
}
.hab-hover-acts {
  display: none;
  position: absolute;
  top: 50%;
  right: 0.28rem;
  transform: translateY(-50%);
  gap: 0.18rem;
  padding: 0.12rem;
  background: var(--surface-translucent);
  border-radius: 8px;
  box-shadow: 0 4px 14px var(--shadow-tint);
}
.b-name-cell:hover .hab-hover-acts,
.b-name-cell:focus-within .hab-hover-acts,
.b-name-cell.editing .hab-hover-acts {
  display: flex;
}
@media (hover: none) {
  .hab-hover-acts {
    display: flex;
    position: static;
    transform: none;
    box-shadow: none;
    padding: 0;
    margin-left: auto;
    align-self: center;
  }
}
.b-cell {
  position: relative;
  min-height: 2.45rem;
  border-radius: 7px;
  border: 1px solid var(--border-subtle);
  background: var(--surface-1);
  cursor: pointer;
  display: grid;
  place-items: center;
  padding: 0;
}
.b-cell.is-skip {
  background: var(--surface-4);
  border-color: var(--border-solid);
  cursor: default;
}
.b-cell.is-empty {
  background: var(--surface-1);
}
.b-cell.is-done {
  background: var(--positive-subtle-strong);
  border-color: var(--positive-border);
}
.b-cell.is-missed {
  background: var(--danger-subtle-hover);
  border-color: var(--danger-border-strong);
}
.b-cell:disabled {
  cursor: default;
}
.box {
  width: 0.95rem;
  height: 0.95rem;
  border: 2px solid var(--border-strong);
  border-radius: 4px;
  background: var(--surface-1);
}
.mark-sym {
  font-size: var(--fs-md);
  font-weight: 800;
  line-height: 1;
}
.mark-sym.ok {
  color: var(--positive-text);
}
.mark-sym.no {
  color: var(--danger-text);
}
.note-dot {
  position: absolute;
  top: 0.18rem;
  right: 0.18rem;
  width: 0.38rem;
  height: 0.38rem;
  border-radius: 999px;
  background: var(--accent);
}
.note-mask {
  position: fixed;
  inset: 0;
  z-index: 40;
  background: var(--scrim);
  display: grid;
  place-items: center;
  padding: 1rem;
}
.note-pop {
  width: min(26rem, 100%);
  background: var(--surface-1);
  border-radius: 14px;
  padding: 0.85rem 0.95rem;
  box-shadow: 0 16px 40px var(--shadow-tint);
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}
.note-head {
  margin: 0;
  font-weight: 700;
  font-size: var(--fs-md);
}
.note-text {
  width: 100%;
  box-sizing: border-box;
  font: inherit;
  padding: 0.5rem 0.55rem;
  border-radius: 10px;
  border: 1px solid var(--border);
  resize: vertical;
  min-height: 5.5rem;
}
.note-acts {
  display: flex;
  gap: 0.4rem;
  justify-content: flex-end;
}
.b-row-acts {
  display: flex;
  align-items: center;
  gap: 0.2rem;
}
.b-edit {
  margin-top: 0.15rem;
}
.strip-day {
  flex: 1 1 0;
  min-width: 0;
  border: 1px solid var(--border-subtle);
  background: var(--surface-1);
  border-radius: 10px;
  padding: 0.35rem 0.1rem;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.12rem;
}
.strip-wd {
  font-size: var(--fs-2xs);
  color: var(--text-4);
  text-transform: uppercase;
  font-weight: 700;
}
.strip-num {
  font-size: clamp(var(--fs-2xs), 1.3vw, var(--fs-md));
  font-weight: 750;
  color: var(--text-1);
}
.strip-day.today {
  box-shadow: 0 0 0 2px var(--accent-ring);
}
.strip-day.anchor {
  background: var(--positive-subtle);
  border-color: var(--positive-border);
}
.strip-hint {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.btn-today {
  padding: 0.15rem 0.45rem;
  font-size: var(--fs-2xs);
}
.composer,
.card,
.edit-box {
  background: var(--panel);
  border: 1px solid var(--border-subtle);
  border-radius: 16px;
  box-shadow: var(--shadow-soft);
}
.composer {
  padding: 0.55rem 0.7rem;
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0.4rem;
  overflow-x: auto;
}
.composer-share {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0.35rem;
  flex-shrink: 0;
}
.share-box {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  padding: 0.45rem 0.6rem;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 12px;
}
.share-url {
  width: 14rem;
  min-width: 10rem;
  font: inherit;
  font-size: var(--fs-2xs);
  padding: 0.32rem 0.4rem;
  border-radius: 8px;
  border: 1px solid var(--border);
}
.btn.secondary.on {
  border-color: var(--positive-border);
  background: var(--positive-subtle);
}
.public-hint {
  margin: 0;
  color: var(--text-muted);
  font-size: var(--fs-sm);
}
.public-mood {
  display: flex;
  justify-content: flex-end;
}
.icon-pick {
  display: flex;
  flex-wrap: nowrap;
  gap: 0.15rem;
  flex-shrink: 0;
}
.title-input {
  flex: 1 1 9rem;
  min-width: 8rem;
  padding: 0.45rem 0.6rem;
  border-radius: 10px;
  border: 1px solid var(--border);
  font: inherit;
}
.dow {
  display: flex;
  flex-wrap: nowrap;
  gap: 0.18rem;
  flex-shrink: 0;
}
.icon-btn {
  width: 1.85rem;
  height: 1.85rem;
  border: 1px solid transparent;
  background: var(--surface-2);
  border-radius: 8px;
  cursor: pointer;
}
.icon-btn.on {
  border-color: var(--positive-border);
  background: var(--positive-subtle);
}
.dow-btn {
  min-width: 2rem;
  padding: 0.28rem 0.32rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface-1);
  cursor: pointer;
  font-size: var(--fs-2xs);
  font-weight: 650;
  color: var(--text-4);
}
.dow-btn.on {
  background: var(--positive-subtle);
  border-color: var(--positive-border);
  color: var(--positive-text);
}
.target-lab {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: var(--fs-xs);
  color: var(--text-muted);
  flex-shrink: 0;
  white-space: nowrap;
}
.target-input {
  width: 3.2rem;
  padding: 0.28rem 0.35rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  font: inherit;
}
.cards {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}
.card {
  padding: 0.55rem 0.65rem;
  min-width: 0;
}
.habit-line {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0.45rem;
  min-width: 0;
}
.slots {
  display: flex;
  flex-wrap: nowrap;
  flex: 1 1 auto;
  min-width: 0;
  gap: 0.18rem;
}
.slot {
  flex: 1 1 0;
  min-width: 0;
  border: 1px solid var(--border-subtle);
  background: var(--surface-1);
  border-radius: 8px;
  padding: 0.18rem 0.08rem;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.05rem;
}
.slot.is-done {
  background: var(--positive-subtle);
  border-color: var(--positive-border);
}
.slot.is-missed {
  background: var(--danger-subtle);
  border-color: var(--danger-border-strong);
}
.slot.today {
  box-shadow: 0 0 0 2px var(--positive-glow);
}
.slot-d {
  font-size: var(--fs-2xs);
  font-weight: 700;
  white-space: nowrap;
  color: var(--text-2);
}
.slot-m {
  font-size: var(--fs-2xs);
  font-weight: 800;
  line-height: 1;
}
.slot.is-done .slot-m {
  color: var(--positive-text);
}
.slot.is-missed .slot-m {
  color: var(--danger-text);
}
.card-acts {
  display: flex;
  gap: 0.22rem;
  flex-shrink: 0;
}
.edit-box {
  margin-top: 0.5rem;
  padding: 0.65rem;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.45rem;
}
.edit-actions {
  display: flex;
  gap: 0.4rem;
}
/* Базовый `.btn-mini`, `.err`, `.muted`, `.empty` — в assets/ui.css. */
.err,
.muted,
.empty {
  margin: 0;
}
/* Базовые `.btn` и его варианты — в assets/ui.css. */

/* Мобильный расклад: страница не уезжает по горизонтали, скроллится только доска. */
@media (max-width: 768px) {
  .workspace {
    overflow-x: hidden;
  }
  .workspace-header {
    padding: var(--space-3) var(--space-5) var(--space-4);
    gap: var(--space-3) var(--space-4);
  }
  .header-user {
    margin-left: auto;
  }
  .user {
    max-width: 45vw;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .page {
    padding: var(--space-6) var(--space-5) var(--space-9);
  }
  .hero {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-5);
  }
  .hero-right {
    width: 100%;
  }
  /* Горизонтальный скролл остаётся у самой доски — это ожидаемо. */
  .board-wrap {
    -webkit-overflow-scrolling: touch;
  }
  .composer,
  .share-box {
    flex-wrap: wrap;
    overflow-x: visible;
  }
  .date-input {
    min-height: var(--tap-min);
    font-size: var(--fs-xs);
  }
  .note-text {
    font-size: var(--fs-xs);
  }
  .b-cell,
  .strip-day {
    min-height: var(--tap-min);
  }
  .note-pop {
    width: 100%;
  }
}
</style>
