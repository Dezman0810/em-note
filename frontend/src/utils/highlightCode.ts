import hljs from 'highlight.js/lib/core'
import sql from 'highlight.js/lib/languages/sql'
import python from 'highlight.js/lib/languages/python'

hljs.registerLanguage('sql', sql)
hljs.registerLanguage('python', python)

export type CodeSnippetLanguage = 'sql' | 'python'

const LANGUAGE_LABELS: Record<CodeSnippetLanguage, string> = {
  sql: 'SQL',
  python: 'Python',
}

export function codeSnippetLanguageLabel(lang: string): string {
  if (lang === 'python') return LANGUAGE_LABELS.python
  return LANGUAGE_LABELS.sql
}

export function defaultCodeSnippetTitle(lang: string): string {
  return codeSnippetLanguageLabel(lang)
}

export function highlightCodeSnippet(code: string, language: string): string {
  const lang = language === 'python' ? 'python' : 'sql'
  const trimmed = code.trim()
  if (!trimmed) {
    return hljs.highlight('', { language: lang, ignoreIllegals: true }).value
  }
  try {
    return hljs.highlight(code, { language: lang, ignoreIllegals: true }).value
  } catch {
    return hljs.highlight(code, { language: 'sql', ignoreIllegals: true }).value
  }
}
