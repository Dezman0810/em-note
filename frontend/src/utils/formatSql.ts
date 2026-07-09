import { format } from 'sql-formatter'

const FORMAT_OPTS = {
  tabWidth: 4,
  keywordCase: 'upper' as const,
  linesBetweenQueries: 2,
  logicalOperatorNewline: 'before' as const,
  expressionWidth: 120,
}

export function formatSqlCode(code: string): string {
  const trimmed = code.trim()
  if (!trimmed) return code

  for (const language of ['postgresql', 'sql', 'transactsql'] as const) {
    try {
      const out = format(trimmed, { ...FORMAT_OPTS, language })
      if (out.trim()) return out
    } catch {
      /* try next dialect */
    }
  }

  throw new Error('SQL formatter could not parse this query')
}
