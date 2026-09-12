import { ref } from 'vue'

const STORAGE_KEY = 'note_inner_scroll'

/** Скролл внутри текста заметки: шапка и панель доступов всегда на экране. */
const innerScroll = ref(true)
let initialized = false

function readStored(): boolean {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw == null) return true
    return raw !== '0' && raw !== 'false'
  } catch {
    return true
  }
}

function writeStored(value: boolean) {
  try {
    localStorage.setItem(STORAGE_KEY, value ? '1' : '0')
  } catch {
    /* приватный режим — просто не запоминаем */
  }
}

function applyToDocument(value: boolean) {
  if (typeof document === 'undefined') return
  document.documentElement.classList.toggle('note-fit', value)
}

export function initNoteLayout() {
  if (initialized) return
  initialized = true
  innerScroll.value = readStored()
  applyToDocument(innerScroll.value)
}

export function useNoteLayout() {
  initNoteLayout()

  function setInnerScroll(value: boolean) {
    innerScroll.value = value
    writeStored(value)
    applyToDocument(value)
  }

  return {
    innerScroll,
    setInnerScroll,
  }
}
