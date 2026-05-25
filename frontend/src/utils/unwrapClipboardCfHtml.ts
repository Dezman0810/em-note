/** Распаковка формата Windows CF_HTML для вставки в TipTap из MindManager / Office / SSMS. */

function extractBetweenFragmentMarkers(html: string): string | null {
  const reOpen = /<!--\s*StartFragment\b[^>]*-->/gi
  const reClose = /<!--\s*EndFragment\b[^>]*-->/gi
  const mOpen = reOpen.exec(html)
  if (!mOpen) return null
  const innerStart = mOpen.index + mOpen[0].length
  reClose.lastIndex = innerStart
  const mClose = reClose.exec(html)
  if (!mClose || mClose.index <= innerStart) return null
  const frag = html.slice(innerStart, mClose.index).trim()
  return frag.length >= 2 ? frag : null
}

function fragmentByByteOffsets(cf: string): string | null {
  const gs = /\bStartFragment\s*:\s*(\d+)/im.exec(cf)
  const ge = /\bEndFragment\s*:\s*(\d+)/im.exec(cf)
  if (!gs?.[1] || !ge?.[1]) return null
  const start = Number(gs[1])
  const end = Number(ge[1])
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return null
  if (start < 0 || start >= cf.length || end > cf.length) return null
  const frag = cf.slice(start, end).trim()
  return frag.length >= 2 ? frag : null
}

function extractBodyInterior(full: string): string | null {
  const bm = /<body[^>]*>([\s\S]*?)<\/body>/im.exec(full)
  if (!bm?.[1]) return null
  const t = bm[1].trim()
  return t.length >= 2 ? t : null
}

/** Убираем заголовочные строки CF_HTML («Version», «StartHTML» …) перед первым содержательным тегом. */
function stripLeadingCfHtmlHeaders(raw: string): string {
  const t = raw.trimStart().replace(/^\ufeff/, '')
  if (!/^Version:\s*/im.test(t)) return raw.trimStart().replace(/^\ufeff/, '')

  for (let j = 0; j < t.length && j < 4000; j++) {
    if (t.charAt(j) === '<') {
      const sniff = t.slice(j, Math.min(j + 48, t.length))
      if (/<(?:html|body|meta|style|table|div|p|span|font|svg|ul|li|colgroup|thead|tbody|tr|td|figure|h\d)\b/i.test(sniff))
        return t.slice(j).trimStart()
    }
  }
  const nl = t.search(/\n<[a-z!]/im)
  return nl > 80 ? t.slice(nl + 1).trimStart() : t
}

/**
 * Из «сырой» строки clipboard `text/html` получить HTML содержимого для парсера.
 */
export function unwrapCfHtmlClipboard(raw: string): string {
  let s = (raw ?? '').replace(/^\ufeff/, '')
  if (!s.trim()) return s

  const byMarkers = extractBetweenFragmentMarkers(s)
  if (byMarkers) return byMarkers.trim()

  const byOff = fragmentByByteOffsets(s)
  if (byOff) return byOff.trim()

  if (/^Version:\s*\d/im.test(s)) {
    const body = extractBodyInterior(s)
    if (body) return body.trim()
    return stripLeadingCfHtmlHeaders(s).trim()
  }

  return s.trim()
}
