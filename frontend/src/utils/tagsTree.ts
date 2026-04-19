import type { Tag } from '../api/types'

/** Обход дерева: корни по имени, затем поддеревья (как в TagsView). */
export function orderedTree(flat: Tag[]): Tag[] {
  const byParent = new Map<string | null, Tag[]>()
  for (const t of flat) {
    const k = t.parent_id
    if (!byParent.has(k)) byParent.set(k, [])
    byParent.get(k)!.push(t)
  }
  for (const [, arr] of byParent) {
    arr.sort((a, b) => a.name.localeCompare(b.name, 'ru'))
  }
  const out: Tag[] = []
  const walk = (pid: string | null) => {
    const kids = byParent.get(pid) ?? []
    for (const t of kids) {
      out.push(t)
      walk(t.id)
    }
  }
  walk(null)
  return out
}

/** У кого есть дочерние метки. */
export function tagsWithChildrenSet(flat: Tag[]): Set<string> {
  const s = new Set<string>()
  for (const t of flat) {
    if (t.parent_id) s.add(t.parent_id)
  }
  return s
}

/**
 * Список меток для боковой панели с учётом свёрнутых узлов.
 * При свёрнутом родителе потомки не показываются.
 */
/** tagId лежит строго под ancestorId (не сам ancestor). */
export function isStrictDescendantOf(flat: Tag[], ancestorId: string, tagId: string): boolean {
  if (tagId === ancestorId) return false
  const byId = new Map(flat.map((t) => [t.id, t]))
  let cur: string | null = byId.get(tagId)?.parent_id ?? null
  while (cur) {
    if (cur === ancestorId) return true
    cur = byId.get(cur)?.parent_id ?? null
  }
  return false
}

/** Является ли tagId потомком ancestorId (или совпадает). */
export function isDescendantTag(flat: Tag[], ancestorId: string, tagId: string): boolean {
  const byId = new Map(flat.map((t) => [t.id, t]))
  let cur: string | null = tagId
  while (cur) {
    if (cur === ancestorId) return true
    cur = byId.get(cur)?.parent_id ?? null
  }
  return false
}

export function visibleTagsForNav(flat: Tag[], collapsedTagIds: Record<string, boolean>): Tag[] {
  const children = new Map<string | null, Tag[]>()
  for (const t of flat) {
    const k = t.parent_id
    if (!children.has(k)) children.set(k, [])
    children.get(k)!.push(t)
  }
  for (const [, arr] of children) {
    arr.sort((a, b) => a.name.localeCompare(b.name, 'ru'))
  }
  const out: Tag[] = []
  const dfs = (parentId: string | null, skipSubtree: boolean) => {
    if (skipSubtree) return
    for (const t of children.get(parentId) ?? []) {
      out.push(t)
      const hasKids = (children.get(t.id)?.length ?? 0) > 0
      const folded = hasKids && !!collapsedTagIds[t.id]
      dfs(t.id, folded)
    }
  }
  dfs(null, false)
  return out
}
