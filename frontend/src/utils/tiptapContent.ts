/** Обход TipTap JSON. */

export function contentHasExcalidraw(contentJson: string): boolean {
  let doc: unknown
  try {
    doc = JSON.parse(contentJson || '{}')
  } catch {
    return false
  }
  function walk(node: unknown): boolean {
    if (!node || typeof node !== 'object') return false
    const o = node as Record<string, unknown>
    if (o.type === 'excalidrawBlock') return true
    const c = o.content
    if (Array.isArray(c)) return c.some(walk)
    return false
  }
  return walk(doc)
}
