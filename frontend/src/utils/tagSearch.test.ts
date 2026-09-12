import { describe, expect, it } from 'vitest'
import { tagNameMatchesQuery } from './tagSearch'

describe('tagNameMatchesQuery', () => {
  it('не считает «Проекты» совпадением с «ест» (там ект, не ест)', () => {
    expect(tagNameMatchesQuery('Проекты', 'ест')).toBe(false)
    expect(tagNameMatchesQuery('10.000 - Проекты', 'ест')).toBe(false)
    expect(tagNameMatchesQuery('1. Проекты в процессе', 'ест')).toBe(false)
  })

  it('не считает «Проекты» совпадением с «есть»', () => {
    expect(tagNameMatchesQuery('10.000 - Проекты', 'есть')).toBe(false)
    expect(tagNameMatchesQuery('Проекты', 'есть')).toBe(false)
    expect(tagNameMatchesQuery('.Есть действие', 'есть')).toBe(true)
  })

  it('находит подстроку «ест» в «Есть» и «престолов»', () => {
    expect(tagNameMatchesQuery('.Есть действие', 'ест')).toBe(true)
    expect(tagNameMatchesQuery('Научится играть мелодию игра престолов', 'ест')).toBe(true)
  })

  it('для длинного запроса понимает простые словоформы', () => {
    expect(tagNameMatchesQuery('Работа', 'работы')).toBe(true)
    expect(tagNameMatchesQuery('Работа', 'работой')).toBe(true)
  })
})
