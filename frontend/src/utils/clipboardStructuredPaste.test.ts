import { Slice } from '@tiptap/pm/model'
import { describe, expect, it } from 'vitest'

import {
  clipboardHtmlLooksStructured,
  getNormalizedClipboardHtml,
  plainTextSpreadsheetToTableHtml,
  resolveStructuredPasteHtml,
  shouldPreferStructuredPasteOverImage,
  sliceIsSpreadsheetImageFallback,
} from './clipboardStructuredPaste'

describe('clipboardStructuredPaste', () => {
  it('detects Excel table HTML', () => {
    const raw =
      'Version:1.0\r\n<html><body><table><tr><td>A</td><td>B</td></tr></table></body></html>'
    const normalized = getNormalizedClipboardHtml(raw)
    expect(normalized).toContain('<table')
    expect(clipboardHtmlLooksStructured(normalized, raw)).toBe(true)
  })

  it('builds table HTML from Excel TSV plain text', () => {
    const html = plainTextSpreadsheetToTableHtml('2\t3\n\t\n')
    expect(html).toContain('<table')
    expect(html).toContain('<td>2</td>')
    expect(html).toContain('<td>3</td>')
  })

  it('prefers TSV table over clipboard image file when HTML is only preview img', () => {
    const cd = {
      getData(type: string) {
        if (type === 'text/html') return '<img src="data:image/png;base64,abc">'
        if (type === 'text/plain') return '2\t3\n\t\n'
        return ''
      },
      files: [{ type: 'image/png' }],
      items: [],
    } as unknown as DataTransfer

    expect(shouldPreferStructuredPasteOverImage(cd)).toBe(true)
    expect(resolveStructuredPasteHtml(cd)).toContain('<td>2</td>')
  })

  it('does not prefer structured paste when only a screenshot is pasted', () => {
    const cd = {
      getData() {
        return ''
      },
      files: [{ type: 'image/png' }],
      items: [],
    } as unknown as DataTransfer

    expect(shouldPreferStructuredPasteOverImage(cd)).toBe(false)
  })

  it('detects image-only fallback slice', () => {
    const image = {
      type: { name: 'image' },
      content: { size: 0 },
    }
    const slice = {
      size: 1,
      content: {
        childCount: 1,
        firstChild: image,
        forEach() {},
      },
    } as unknown as Slice
    expect(sliceIsSpreadsheetImageFallback(slice)).toBe(true)
  })
})
