import { computed, ref } from 'vue'

/** Выбор пользователя: явная светлая/тёмная тема либо «как в системе». */
export type ThemePreference = 'light' | 'dark' | 'system'
/** Тема, которая реально применена к документу. */
export type ResolvedTheme = 'light' | 'dark'

const THEME_STORAGE_KEY = 'note_theme'
const DARK_MQ = '(prefers-color-scheme: dark)'

const preference = ref<ThemePreference>('system')
const systemDark = ref(false)

let mq: MediaQueryList | null = null
let initialized = false

function isThemePreference(v: unknown): v is ThemePreference {
  return v === 'light' || v === 'dark' || v === 'system'
}

function readStoredPreference(): ThemePreference {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY)
    return isThemePreference(raw) ? raw : 'system'
  } catch {
    return 'system'
  }
}

function writeStoredPreference(value: ThemePreference) {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, value)
  } catch {
    /* приватный режим / заблокированное хранилище — тема просто не запомнится */
  }
}

function resolve(pref: ThemePreference, sysDark: boolean): ResolvedTheme {
  if (pref === 'system') return sysDark ? 'dark' : 'light'
  return pref
}

function applyToDocument(theme: ResolvedTheme) {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  root.setAttribute('data-theme', theme)
  root.style.colorScheme = theme
}

/**
 * Читает сохранённый выбор и сразу ставит `data-theme` на `<html>`.
 * Вызывается из `main.ts` до монтирования приложения, чтобы не было вспышки светлой темы.
 */
export function initTheme() {
  if (initialized) return
  initialized = true

  preference.value = readStoredPreference()

  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    mq = window.matchMedia(DARK_MQ)
    systemDark.value = mq.matches
    const onChange = (e: MediaQueryListEvent) => {
      systemDark.value = e.matches
      if (preference.value === 'system') applyToDocument(resolve('system', e.matches))
    }
    if (typeof mq.addEventListener === 'function') mq.addEventListener('change', onChange)
    else mq.addListener(onChange)
  }

  applyToDocument(resolve(preference.value, systemDark.value))
}

export function useTheme() {
  initTheme()

  const theme = computed<ResolvedTheme>(() => resolve(preference.value, systemDark.value))
  const isDark = computed(() => theme.value === 'dark')

  function setTheme(value: ThemePreference) {
    preference.value = value
    writeStoredPreference(value)
    applyToDocument(resolve(value, systemDark.value))
  }

  /** Светлая → тёмная → как в системе → светлая. */
  function cycleTheme() {
    const order: ThemePreference[] = ['light', 'dark', 'system']
    const next = order[(order.indexOf(preference.value) + 1) % order.length]
    setTheme(next)
  }

  /** Переключает на противоположную текущей применённой теме. */
  function toggleTheme() {
    setTheme(theme.value === 'dark' ? 'light' : 'dark')
  }

  const label = computed(() => {
    if (preference.value === 'system') return 'Тема: как в системе'
    return preference.value === 'dark' ? 'Тема: тёмная' : 'Тема: светлая'
  })

  const icon = computed(() => {
    if (preference.value === 'system') return '◐'
    return preference.value === 'dark' ? '☾' : '☀'
  })

  return {
    preference,
    theme,
    isDark,
    label,
    icon,
    setTheme,
    toggleTheme,
    cycleTheme,
  }
}
