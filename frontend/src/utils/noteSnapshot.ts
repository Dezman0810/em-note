/** Каноническая форма JSON для сравнения «есть ли изменения» без лишних PATCH. */
export function normalizeContentJson(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw || '{}'))
  } catch {
    return raw || '{}'
  }
}
