import type { Slice } from '@tiptap/pm/model'

import { normalizePastedRichCodeHtml } from './normalizePastedRichCodeHtml'

const STRUCTURED_BLOCK_RE =
  /<(?:p|div|table|tr|td|th|ul|ol|li|thead|tbody|caption|colgroup|svg|picture|figure|h[1-6])\b/i

export function getNormalizedClipboardHtml(rawHtml: string | null | undefined): string {
  if (!rawHtml?.trim()) return ''
  return normalizePastedRichCodeHtml(rawHtml).trim()
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** Excel / Sheets / LibreOffice: text/plain с табами и переводами строк. */
export function plainTextSpreadsheetToTableHtml(plain: string | null | undefined): string | null {
  const text = (plain ?? '').replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  if (!text.includes('\t')) return null

  const lines = text.split('\n')
  while (lines.length > 0 && lines[lines.length - 1] === '') lines.pop()
  if (lines.length === 0) return null

  const rows = lines.map((line) => line.split('\t'))
  const maxCols = Math.max(...rows.map((row) => row.length), 1)
  if (maxCols < 2 && lines.length < 2) return null

  const parts = ['<table><tbody>']
  for (const row of rows) {
    parts.push('<tr>')
    for (let col = 0; col < maxCols; col++) {
      parts.push(`<td>${escapeHtml(row[col] ?? '')}</td>`)
    }
    parts.push('</tr>')
  }
  parts.push('</tbody></table>')
  return parts.join('')
}

function htmlIsSpreadsheetImagePreview(normalizedHtml: string): boolean {
  if (!normalizedHtml || /<table\b/i.test(normalizedHtml)) return false
  try {
    const doc = new DOMParser().parseFromString(normalizedHtml, 'text/html')
    const body = doc.body
    if (body.querySelector('table')) return false
    const imgs = body.querySelectorAll('img')
    if (imgs.length === 0) return false
    const text = (body.textContent ?? '').replace(/\s+/g, '')
    return text.length === 0
  } catch {
    return false
  }
}

/** HTML из буфера, который нужно вставлять как разметку, а не как одиночную картинку. */
export function clipboardHtmlLooksStructured(normalizedHtml: string, rawHtml: string): boolean {
  if (!normalizedHtml) return false
  if (/<table\b/i.test(normalizedHtml)) return true
  if (htmlIsSpreadsheetImagePreview(normalizedHtml)) return false

  const cfHtml = /^Version:\s*\d/m.test(rawHtml)
  const hasBlocks = STRUCTURED_BLOCK_RE.test(normalizedHtml)
  const hasInlineRich =
    /<span\b[^>]*style\s*=/i.test(normalizedHtml) ||
    /<font\b/i.test(normalizedHtml)

  return cfHtml || hasBlocks || hasInlineRich
}

/** Лучший HTML для вставки: CF_HTML / Office или TSV из Excel. */
export function resolveStructuredPasteHtml(cd: DataTransfer | null): string | null {
  if (!cd) return null

  const rawHtml = cd.getData('text/html')
  const normalized = getNormalizedClipboardHtml(rawHtml)
  if (normalized && clipboardHtmlLooksStructured(normalized, rawHtml)) {
    return normalized
  }

  if (normalized && htmlIsSpreadsheetImagePreview(normalized)) {
    const fromPlain = plainTextSpreadsheetToTableHtml(cd.getData('text/plain'))
    if (fromPlain) return fromPlain
  }

  return plainTextSpreadsheetToTableHtml(cd.getData('text/plain'))
}

export function shouldPreferStructuredPasteOverImage(cd: DataTransfer | null): boolean {
  return resolveStructuredPasteHtml(cd) != null
}

/** @deprecated use shouldPreferStructuredPasteOverImage */
export function shouldPreferClipboardHtmlOverImage(cd: DataTransfer | null): boolean {
  return shouldPreferStructuredPasteOverImage(cd)
}

export function isTableSlice(slice: Slice): boolean {
  let found = false
  slice.content.forEach((node) => {
    if (node.type.name === 'table') found = true
  })
  return found
}

export function sliceIsSpreadsheetImageFallback(slice: Slice): boolean {
  if (slice.content.childCount !== 1) return false
  const node = slice.content.firstChild
  if (!node) return false
  if (node.type.name === 'image') return true
  if (node.type.name === 'paragraph' && node.content.childCount === 1) {
    return node.content.firstChild?.type.name === 'image'
  }
  return false
}
