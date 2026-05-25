import { unwrapCfHtmlClipboard } from './unwrapClipboardCfHtml'

/**
 * MindManager / SSMS / Office / VS и т.п.:
 * 1) Windows CF_HTML в буфере → реальный HTML-фрагмент;
 * 2) `<font>` → `<span style="…">`, чтобы сохранились цвет и шрифт;
 * убираем `on*` и `javascript:`.
 */
export function normalizePastedRichCodeHtml(html: string): string {
  const unwrapped = unwrapCfHtmlClipboard(html ?? '').trim()
  if (!unwrapped) return (html ?? '').trim()
  /** Нет ни одного тега после распаковки — отдаём как текст */
  if (!/<(?![?!])[^\s>/<]/i.test(unwrapped)) return unwrapped

  try {
    const doc = new DOMParser().parseFromString(unwrapped, 'text/html')
    const body = doc.body

    body.querySelectorAll('script').forEach((el) => el.remove())
    stripDangerousInlineHandlers(body)

    let fd = 0
    while (body.querySelector('font') && fd < 99) {
      fd += 1
      const font = body.querySelector('font')
      if (!font) break
      const span = doc.createElement('span')
      const chunks: string[] = []

      const color = font.getAttribute('color')?.trim()
      if (color) chunks.push(`color: ${cssColorOrKeyword(color)}`)

      const face = font.getAttribute('face')?.trim()
      if (face) {
        const primary = face.split(',')[0]?.replace(/^["']+|["']+$/g, '').trim()
        if (primary) chunks.push(`font-family: ${quoteFontCss(primary)}, Consolas, "Courier New", monospace`)
      }

      const existing = font.getAttribute('style')?.trim()
      if (existing) chunks.push(existing.replace(/;+$/g, ''))

      if (chunks.length) span.setAttribute('style', chunks.join('; '))

      while (font.firstChild) span.appendChild(font.firstChild)
      font.replaceWith(span)
    }

    unwrapNamedAnchors(body)

    return body.innerHTML
  } catch {
    return unwrapped
  }
}

function cssColorOrKeyword(raw: string): string {
  const v = raw.trim()
  if (/^#[\da-f]{3,8}$/i.test(v)) return v.toLowerCase()
  if (/^(?:rgb|rgba|hsl|hsla)\(/i.test(v)) return v
  return v.toLowerCase()
}

function quoteFontCss(name: string): string {
  if (/["']/.test(name)) return name
  return /\s/.test(name) ? `"${name.replace(/"/g, '\\"')}"` : name
}

function stripDangerousInlineHandlers(root: HTMLElement) {
  const walk = (el: HTMLElement) => {
    for (const attr of [...el.attributes]) {
      const n = attr.name.toLowerCase()
      if (n.startsWith('on')) el.removeAttribute(attr.name)
      if (n === 'href' && /^\s*javascript:/i.test(attr.value)) el.removeAttribute('href')
    }
    for (let i = 0; i < el.children.length; i++) walk(el.children[i] as HTMLElement)
  }
  walk(root)
}

function unwrapNamedAnchors(root: HTMLElement) {
  root.querySelectorAll('a[name]').forEach((a) => {
    const el = a as HTMLAnchorElement
    if (!el.getAttribute('href')) {
      while (el.firstChild) el.parentNode?.insertBefore(el.firstChild, el)
      el.remove()
    }
  })
}
