import { describe, expect, it } from 'vitest'

import {
  DEFAULT_MINDMAP_DATA,
  parseMindmapScene,
  sanitizeMindmapScene,
  stringifyMindmapScene,
} from './mindmapDefaultScene'

describe('sanitizeMindmapScene', () => {
  it('новая карта по умолчанию — классика 4 и логическая структура', () => {
    expect(DEFAULT_MINDMAP_DATA.theme.template).toBe('classic4')
    expect(DEFAULT_MINDMAP_DATA.layout).toBe('logicalStructure')
    expect(DEFAULT_MINDMAP_DATA.theme.config).toEqual({
      root: { fillColor: '#0062b1', color: '#ffffff' },
      second: { marginX: 50, marginY: 15, fillColor: '#73d8ff', color: '#000000' },
      node: { marginX: 30, marginY: 5 },
    })
    expect(parseMindmapScene('{}').theme.template).toBe('classic4')
    expect(parseMindmapScene('{}').layout).toBe('logicalStructure')
  })

  it('оставляет обычную карту', () => {
    const scene = {
      root: { data: { text: 'Работа' }, children: [{ data: { text: 'Задачи' }, children: [] }] },
      theme: { template: 'classic', config: {} },
      layout: 'mindMap',
      config: {},
      view: null,
    }
    expect(sanitizeMindmapScene(scene).root.data.text).toBe('Работа')
    expect(sanitizeMindmapScene(scene).root.children).toHaveLength(1)
  })

  it('разворачивает вложенный документ {root:{root}}', () => {
    const inner = { data: { text: 'Тема' }, children: [{ data: { text: 'Узел' }, children: [] }] }
    const nested = {
      root: {
        root: inner,
        theme: { template: 'classic', config: {} },
        layout: 'mindMap',
      },
      theme: { template: 'dark', config: {} },
      layout: 'logicalStructure',
    }
    const out = sanitizeMindmapScene(nested)
    expect(out.root.data.text).toBe('Тема')
    expect(out.root.children[0]?.data.text).toBe('Узел')
    expect(out.layout).toBe('mindMap')
  })

  it('убирает второй корень-заглушку Главная/Главная', () => {
    const out = sanitizeMindmapScene({
      root: {
        data: { text: 'Главная' },
        children: [
          {
            data: { text: 'Главная' },
            children: [{ data: { text: 'Покупки' }, children: [] }],
          },
        ],
      },
    })
    expect(out.root.data.text).toBe('Главная')
    expect(out.root.children).toHaveLength(1)
    expect(out.root.children[0]?.data.text).toBe('Покупки')
  })

  it('убирает дубль Главная в rich text <p>', () => {
    const out = sanitizeMindmapScene({
      root: {
        data: { text: '<p>Главная</p>' },
        children: [{ data: { text: 'Главная' }, children: [] }],
      },
    })
    expect(out.root.data.text.replace(/<[^>]+>/g, '')).toMatch(/Главная/)
    expect(out.root.children).toHaveLength(0)
  })

  it('не трогает Главная с обычными детьми', () => {
    const out = sanitizeMindmapScene({
      root: {
        data: { text: 'Главная' },
        children: [
          { data: { text: 'А' }, children: [] },
          { data: { text: 'Б' }, children: [] },
        ],
      },
    })
    expect(out.root.data.text).toBe('Главная')
    expect(out.root.children.map((c) => c.data.text)).toEqual(['А', 'Б'])
  })

  it('отбрасывает цикл parent и не раздувает дерево', () => {
    const root: Record<string, unknown> = { data: { text: 'Корень' }, children: [] }
    const child: Record<string, unknown> = { data: { text: 'Дитя' }, children: [], parent: root }
    ;(root as { children: unknown[] }).children = [child, root]
    const out = sanitizeMindmapScene({ root })
    expect(out.root.data.text).toBe('Корень')
    expect(out.root.children).toHaveLength(1)
    expect(out.root.children[0]?.data.text).toBe('Дитя')
    expect(JSON.stringify(out).includes('"parent"')).toBe(false)
  })

  it('пустой view не отдаёт {} — из‑за него карта не поднимается', () => {
    const out = sanitizeMindmapScene({
      root: { data: { text: 'Тема' }, children: [] },
      view: {},
    })
    expect(out.view).toBeNull()
  })

  it('сохраняет валидный view.state', () => {
    const view = { transform: { a: 1 }, state: { scale: 1, x: 0, y: 0 } }
    const out = sanitizeMindmapScene({
      root: { data: { text: 'Тема' }, children: [] },
      view,
    })
    expect(out.view).toEqual(view)
  })

  it('parse/stringify переживают битый JSON', () => {
    expect(parseMindmapScene('not-json').root.data.text).toBe('Главная')
    const json = stringifyMindmapScene({ root: { data: { text: 'Ок' }, children: [] } })
    expect(parseMindmapScene(json).root.data.text).toBe('Ок')
  })
})
