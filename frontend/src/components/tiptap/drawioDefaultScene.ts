export const DEFAULT_DRAWIO_XML = `<mxfile host="Em-Note" agent="Em-Note" version="22.1.0" type="device">
  <diagram id="page-1" name="Страница-1">
    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="827" pageHeight="1169" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>`

/** Совместимость с TipTap-атрибутом scene: храним draw.io XML. */
export const DEFAULT_C4_SCENE = DEFAULT_DRAWIO_XML

export function isDrawioXml(raw: string): boolean {
  const s = (raw || '').trim()
  return s.includes('<mxfile') || s.includes('<mxGraphModel')
}

export function parseDrawioScene(raw: string): string {
  const s = (raw || '').trim()
  if (isDrawioXml(s)) return s
  return DEFAULT_DRAWIO_XML
}

export function stringifyDrawioScene(xml: string): string {
  const s = (xml || '').trim()
  return isDrawioXml(s) ? s : DEFAULT_DRAWIO_XML
}

export function diagramNameFromXml(xml: string): string {
  const m = (xml || '').match(/<diagram[^>]+name="([^"]{1,80})"/i)
  return m?.[1]?.trim() || ''
}

export function normalizeDrawioXml(s: string): string {
  return stringifyDrawioScene(s).replace(/\s+/g, ' ').trim()
}
