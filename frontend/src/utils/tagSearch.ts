/** Поиск меток: подстрока и лёгкая нормализация русских словоформ (работа / работы / работой). */

function foldTagSearchText(s: string): string {
  return s.trim().toLowerCase().replace(/ё/g, 'е')
}

/** Длинные окончания раньше коротких. */
const RU_SUFFIXES = [
  'ами',
  'ями',
  'ого',
  'ему',
  'ому',
  'ыми',
  'ими',
  'ах',
  'ях',
  'ой',
  'ей',
  'ий',
  'ый',
  'ое',
  'ее',
  'ая',
  'яя',
  'ые',
  'ие',
  'ов',
  'ев',
  'ам',
  'ям',
  'ом',
  'ем',
  'ую',
  'юю',
  'у',
  'ю',
  'а',
  'я',
  'ы',
  'и',
  'е',
  'о',
  'ь',
]

function lightStem(s: string): string {
  if (s.length < 4) return s
  for (const suf of RU_SUFFIXES) {
    if (s.length - suf.length >= 3 && s.endsWith(suf)) return s.slice(0, -suf.length)
  }
  return s
}

/** Совпадение: имя содержит запрос; словоформы — только если основа достаточно длинная. */
export function tagNameMatchesQuery(name: string, query: string): boolean {
  const q = foldTagSearchText(query)
  if (!q) return true
  const n = foldTagSearchText(name)
  if (!n) return false
  if (n.includes(q)) return true
  const tokens = n.split(/[\s/|,;:_\-+]+/).filter(Boolean)
  if (tokens.some((tok) => tok.includes(q))) return true
  const qs = lightStem(q)
  if (qs.length < 4) return false
  if (lightStem(n) === qs || lightStem(n).startsWith(qs)) return true
  return tokens.some((tok) => {
    const ts = lightStem(tok)
    return ts === qs || ts.startsWith(qs)
  })
}
