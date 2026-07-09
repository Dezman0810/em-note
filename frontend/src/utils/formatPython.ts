type RuffFmtModule = typeof import('@wasm-fmt/ruff_fmt/vite')

let ruffModulePromise: Promise<RuffFmtModule> | null = null

async function loadRuffFmt(): Promise<RuffFmtModule> {
  if (!ruffModulePromise) {
    ruffModulePromise = (async () => {
      const mod = await import('@wasm-fmt/ruff_fmt/vite')
      await mod.default()
      return mod
    })()
  }
  return ruffModulePromise
}

/** Ruff (совместим с Black / PEP 8): отступы 4, ширина строки 88. */
export async function formatPythonCode(code: string): Promise<string> {
  const trimmed = code.trim()
  if (!trimmed) return code

  const { format } = await loadRuffFmt()
  return format(trimmed, 'snippet.py', {
    indent_style: 'space',
    indent_width: 4,
    line_width: 88,
    quote_style: 'double',
    magic_trailing_comma: 'respect',
    line_ending: 'lf',
  })
}
