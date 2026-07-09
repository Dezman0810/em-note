import { format } from 'sql-formatter'

export function formatSqlCode(code: string): string {
  const trimmed = code.trim()
  if (!trimmed) return code
  try {
    return format(trimmed, {
      language: 'postgresql',
      tabWidth: 4,
      keywordCase: 'upper',
      linesBetweenQueries: 2,
      logicalOperatorNewline: 'before',
      expressionWidth: 120,
    })
  } catch {
    return code
  }
}
