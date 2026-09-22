import { Slice } from '@tiptap/pm/model'
import { describe, expect, it } from 'vitest'

import {
  clipboardHtmlLooksStructured,
  getNormalizedClipboardHtml,
  plainTextSpreadsheetToTableHtml,
  buildTableHtml,
  clipboardTableHtmlFromParts,
  plainTextSpreadsheetRows,
  resolveStructuredPasteHtml,
  shouldPreferStructuredPasteOverImage,
  withoutEmptyRows,
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

  it('кнопка «Вставить таблицу»: строк ровно столько, сколько скопировано', () => {
    // Excel кладёт картинку-превью в HTML и настоящие данные в TSV.
    const html = clipboardTableHtmlFromParts(
      '<img src="data:image/png;base64,abc">',
      ['A\tB', '1\t2', '3\t4', ''].join('\n')
    )
    expect(html).toContain('<td>A</td>')
    expect((html ?? '').match(/<tr>/g)).toHaveLength(3)

    // Обычный текст таблицей не считаем.
    expect(clipboardTableHtmlFromParts('', 'просто строка')).toBeNull()
    expect(clipboardTableHtmlFromParts(null, null)).toBeNull()
  })

  it('служебные пустые строки Excel выбрасываются, данные остаются', () => {
    const rows = [['A', 'B'], ['', ''], ['1', '2'], ['', '']]
    expect(withoutEmptyRows(rows)).toEqual([
      ['A', 'B'],
      ['1', '2'],
    ])

    const pasted = clipboardTableHtmlFromParts('', ['A\tB', '\t', '1\t2'].join('\n'))
    expect((pasted ?? '').match(/<tr>/g)).toHaveLength(2)
  })

  it('строки TSV и сборка таблицы дополняют короткие строки до прямоугольника', () => {
    expect(plainTextSpreadsheetRows('A\tB\tC\n1\t2')).toEqual([
      ['A', 'B', 'C'],
      ['1', '2'],
    ])
    const html = buildTableHtml([['A', 'B', 'C'], ['1', '2']])
    expect((html ?? '').match(/<td>/g)).toHaveLength(6)
    expect(html).toContain('<td></td>')
    expect(buildTableHtml([])).toBeNull()
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
