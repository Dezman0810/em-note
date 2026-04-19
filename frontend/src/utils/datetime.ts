/**
 * Даты в API — в UTC (с суффиксом +00:00/Z или без суффикса = тоже UTC).
 * Отображение в интерфейсе — календарное время Москвы.
 */

/** Строка без явного часового пояса трактуем как UTC (иначе JS считает её «локальной» и даёт сдвиг). */
function parseApiInstant(iso: string): Date {
  const s = iso.trim()
  const hasTz = /([zZ]$)|([+-]\d{2}:\d{2}$)|([+-]\d{2}\d{2}$)/.test(s)
  const normalized = hasTz ? s : `${s}Z`
  return new Date(normalized)
}

export function fmtMsk(iso: string | undefined | null): string {
  if (!iso) return '—'
  try {
    const d = parseApiInstant(iso)
    if (Number.isNaN(d.getTime())) return String(iso).slice(0, 19)
    return d.toLocaleString('ru-RU', {
      timeZone: 'Europe/Moscow',
      dateStyle: 'short',
      timeStyle: 'short',
    })
  } catch {
    return String(iso).slice(0, 19)
  }
}

/** Короткая отметка для списков заметок (дд.мм.гг, чч:мм) по Москве. */
export function fmtCompactMsk(iso: string | undefined | null): string {
  if (!iso) return '—'
  try {
    const d = parseApiInstant(iso)
    if (Number.isNaN(d.getTime())) return String(iso).slice(0, 16)
    return d.toLocaleString('ru-RU', {
      timeZone: 'Europe/Moscow',
      day: '2-digit',
      month: '2-digit',
      year: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return String(iso).slice(0, 16)
  }
}
