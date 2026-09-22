/**
 * Простые <img src="/api/attachments/UUID/file"> в TipTap невидимы браузеру с JWT —
 * браузер не шлёт Authorization. Переводим в uploadedFile (загрузка через axios+blob в NodeView).
 */
export function rewriteAttachmentImagesInTipTapDoc(doc: unknown): unknown {
  if (!doc || typeof doc !== 'object') return doc

  function uuidFromAttachmentSrc(src: string): string | null {
    const m = src.match(
      /\/api\/attachments\/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\/file/
    )
    if (m?.[1]) return m[1].toLowerCase()
    const m2 = src.match(
      /\/api\/public\/notes\/[^/]+\/attachments\/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\/file/
    )
    if (m2?.[1]) return m2[1].toLowerCase()
    return null
  }

  function walk(node: Record<string, unknown>): Record<string, unknown> {
    if (node.type === 'image') {
      const attrs = node.attrs && typeof node.attrs === 'object' ? (node.attrs as Record<string, unknown>) : {}
      const src = typeof attrs.src === 'string' ? attrs.src : ''
      const id = uuidFromAttachmentSrc(src)
      if (id) {
        const alt = typeof attrs.alt === 'string' ? attrs.alt.trim() : ''
        return {
          type: 'uploadedFile',
          attrs: {
            attachmentId: id,
            filename: alt || 'image',
            mimeType: 'application/octet-stream',
            isImage: true,
            transcript: '',
          },
        }
      }
    }

    const c = node.content
    if (!Array.isArray(c)) return { ...node }
    const nextContent = c.map((child) =>
      typeof child === 'object' && child !== null ? walk(child as Record<string, unknown>) : child
    )
    return { ...node, content: nextContent }
  }

  return walk(doc as Record<string, unknown>)
}

/** Обход TipTap JSON. */

/**
 * Разбор тела заметки кешируется на одно значение: проверки ниже вызываются
 * пачкой (схема, карта, аудио) после каждого автосохранения, а документ со
 * встроенными картинками бывает мегабайтным — три лишних JSON.parse заметны.
 */
let parsedRaw: string | null = null
let parsedDoc: unknown = null

function parseDoc(contentJson: string): unknown {
  const raw = contentJson || '{}'
  if (parsedRaw === raw) return parsedDoc
  let doc: unknown = null
  try {
    doc = JSON.parse(raw)
  } catch {
    doc = null
  }
  parsedRaw = raw
  parsedDoc = doc
  return doc
}

/** Есть ли в документе узел, удовлетворяющий условию. */
function hasNode(doc: unknown, match: (node: Record<string, unknown>) => boolean): boolean {
  function walk(node: unknown): boolean {
    if (!node || typeof node !== 'object') return false
    const o = node as Record<string, unknown>
    if (match(o)) return true
    const c = o.content
    if (Array.isArray(c)) return c.some(walk)
    return false
  }
  return walk(doc)
}

export function contentHasMindmap(contentJson: string): boolean {
  return hasNode(parseDoc(contentJson), (o) => o.type === 'mindmapBlock')
}

export function contentHasExcalidraw(contentJson: string): boolean {
  return hasNode(parseDoc(contentJson), (o) => o.type === 'excalidrawBlock')
}

export function contentHasC4(contentJson: string): boolean {
  return hasNode(parseDoc(contentJson), (o) => o.type === 'c4Block')
}

/** Есть ли в документе аудио (вложение audio/* или legacy audioNote). */
export function contentHasAudio(contentJson: string): boolean {
  return hasNode(parseDoc(contentJson), (o) => {
    if (o.type === 'audioNote') return true
    if (o.type === 'uploadedFile') {
      const attrs = o.attrs as Record<string, unknown> | undefined
      return String(attrs?.mimeType ?? '').toLowerCase().startsWith('audio/')
    }
    return false
  })
}
