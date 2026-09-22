import { describe, expect, it } from 'vitest'
import { contentHasAudio, contentHasExcalidraw, contentHasMindmap } from './tiptapContent'

function doc(...nodes: unknown[]): string {
  return JSON.stringify({ type: 'doc', content: nodes })
}

describe('проверки содержимого заметки', () => {
  it('находит блоки схемы, карты и аудио на любой глубине', () => {
    const nested = doc({
      type: 'bulletList',
      content: [{ type: 'listItem', content: [{ type: 'excalidrawBlock' }] }],
    })
    expect(contentHasExcalidraw(nested)).toBe(true)
    expect(contentHasMindmap(doc({ type: 'mindmapBlock' }))).toBe(true)
    expect(
      contentHasAudio(doc({ type: 'uploadedFile', attrs: { mimeType: 'audio/webm' } }))
    ).toBe(true)
    expect(contentHasAudio(doc({ type: 'audioNote' }))).toBe(true)
  })

  it('пустой и битый документ ничего не находят', () => {
    for (const raw of ['', '{}', 'не json']) {
      expect(contentHasExcalidraw(raw)).toBe(false)
      expect(contentHasMindmap(raw)).toBe(false)
      expect(contentHasAudio(raw)).toBe(false)
    }
  })

  it('кеш разбора не путает разные документы', () => {
    const withMap = doc({ type: 'mindmapBlock' })
    const withoutMap = doc({ type: 'paragraph' })
    expect(contentHasMindmap(withMap)).toBe(true)
    expect(contentHasMindmap(withoutMap)).toBe(false)
    expect(contentHasMindmap(withMap)).toBe(true)
    // Тот же разобранный документ переиспользуется другой проверкой.
    expect(contentHasExcalidraw(withMap)).toBe(false)
  })

  it('вложение не-аудио аудиометкой не считается', () => {
    expect(contentHasAudio(doc({ type: 'uploadedFile', attrs: { mimeType: 'image/png' } }))).toBe(
      false
    )
  })
})
