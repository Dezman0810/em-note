export type MindmapNode = {
  data: { text: string; [key: string]: unknown }
  children: MindmapNode[]
}

export type MindmapScene = {
  root: MindmapNode
  theme: { template: string; config: Record<string, unknown> }
  layout: string
  config: Record<string, unknown>
  view: unknown
}

export const DEFAULT_MINDMAP_THEME = 'classic4'

export const DEFAULT_MINDMAP_THEME_CONFIG: Record<string, unknown> = {
  root: { fillColor: '#0062b1', color: '#ffffff' },
  second: { marginX: 50, marginY: 15, fillColor: '#73d8ff', color: '#000000' },
  node: { marginX: 30, marginY: 5 },
}

export const DEFAULT_MINDMAP_DATA: MindmapScene = {
  root: { data: { text: 'Главная' }, children: [] },
  theme: { template: DEFAULT_MINDMAP_THEME, config: { ...DEFAULT_MINDMAP_THEME_CONFIG } },
  layout: 'logicalStructure',
  config: {},
  view: null,
}

export const DEFAULT_MINDMAP_SCENE = JSON.stringify(DEFAULT_MINDMAP_DATA)

const PLACEHOLDER_ROOT = new Set(['главная', 'центр', 'root', 'central topic', '根节点', '中心主题'])

function nodeTitle(text: unknown): string {
  return String(text ?? '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === 'object' && !Array.isArray(v)
}

function plainJson<T>(value: T, fallback: T): T {
  try {
    return JSON.parse(JSON.stringify(value)) as T
  } catch {
    return fallback
  }
}

function emptyScene(): MindmapScene {
  return {
    root: { data: { text: 'Главная' }, children: [] },
    theme: { template: DEFAULT_MINDMAP_THEME, config: { ...DEFAULT_MINDMAP_THEME_CONFIG } },
    layout: 'logicalStructure',
    config: {},
    view: null,
  }
}

function cloneNode(raw: unknown, seen: WeakSet<object>, depth: number): MindmapNode | null {
  if (!isPlainObject(raw) || depth > 48) return null
  if (seen.has(raw)) return null
  seen.add(raw)

  if (isPlainObject(raw.root) && isPlainObject((raw.root as { data?: unknown }).data)) {
    return cloneNode(raw.root, seen, depth + 1)
  }

  const dataRaw = isPlainObject(raw.data) ? raw.data : null
  if (!dataRaw) return null

  const data: Record<string, unknown> = {}
  for (const [key, val] of Object.entries(dataRaw)) {
    if (key === 'parent' || key === 'mindMap' || key === 'node' || key === 'el') continue
    if (val !== null && typeof val === 'object') {
      const copied = plainJson(val, null)
      if (copied !== null) data[key] = copied
    } else {
      data[key] = val
    }
  }
  if (typeof data.text !== 'string') {
    data.text = data.text == null ? '' : String(data.text)
  }

  const children: MindmapNode[] = []
  if (Array.isArray(raw.children)) {
    for (const child of raw.children) {
      const node = cloneNode(child, seen, depth + 1)
      if (node) children.push(node)
    }
  }
  return { data: data as MindmapNode['data'], children }
}

function unwrapNestedDocument(raw: unknown): Record<string, unknown> | null {
  let cur: unknown = raw
  for (let i = 0; i < 8; i++) {
    if (!isPlainObject(cur)) return null
    const inner = cur.root
    if (isPlainObject(inner) && isPlainObject(inner.root)) {
      cur = {
        root: inner.root,
        theme: inner.theme ?? cur.theme,
        layout: inner.layout ?? cur.layout,
        config: inner.config ?? cur.config,
        view: inner.view ?? cur.view,
      }
      continue
    }
    break
  }
  return isPlainObject(cur) ? cur : null
}

function unwrapDuplicatePlaceholder(node: MindmapNode): MindmapNode {
  let cur = node
  for (let i = 0; i < 48; i++) {
    const text = nodeTitle(cur.data?.text)
    const only = cur.children.length === 1 ? cur.children[0] : null
    if (!only || !PLACEHOLDER_ROOT.has(text)) break
    const childText = nodeTitle(only.data?.text)
    if (childText === text || PLACEHOLDER_ROOT.has(childText)) {
      cur = only
      continue
    }
    break
  }
  return cur
}

export function sanitizeMindmapScene(raw: unknown): MindmapScene {
  const doc =
    unwrapNestedDocument(raw) ?? (isPlainObject(raw) ? raw : null) ?? ({} as Record<string, unknown>)
  const rootSrc = doc.root ?? (isPlainObject(doc.data) ? doc : null)
  const cloned = cloneNode(rootSrc, new WeakSet(), 0)
  if (!cloned) return emptyScene()

  const themeRaw = isPlainObject(doc.theme) ? doc.theme : null
  return {
    root: unwrapDuplicatePlaceholder(cloned),
    theme: {
      template: typeof themeRaw?.template === 'string' ? themeRaw.template : DEFAULT_MINDMAP_THEME,
      config: isPlainObject(themeRaw?.config) ? plainJson(themeRaw.config, {}) : {},
    },
    layout: typeof doc.layout === 'string' ? doc.layout : 'logicalStructure',
    config: isPlainObject(doc.config) ? plainJson(doc.config, {}) : {},
    view: validView(doc.view),
  }
}

function validView(raw: unknown): unknown {
  if (!isPlainObject(raw) || !isPlainObject(raw.state)) return null
  return plainJson(raw, null)
}

export function parseMindmapScene(raw: string): MindmapScene {
  try {
    return sanitizeMindmapScene(JSON.parse(raw || '{}'))
  } catch {
    return emptyScene()
  }
}

export function stringifyMindmapScene(raw: unknown): string {
  return JSON.stringify(sanitizeMindmapScene(raw))
}
