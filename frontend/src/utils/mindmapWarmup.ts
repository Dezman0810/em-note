/** Прогрев кэша браузера для embed mindmap-app (~4 МБ JS/CSS). Безопасно вызывать многократно. */
let assetsWarmed = false
let embedWarmed = false
let embedWarmTimer: ReturnType<typeof setTimeout> | null = null

const MINDMAP_ASSETS = [
  '/mindmap-app/assets/css/chunk-vendors.css?c38ada11529d60265d8b',
  '/mindmap-app/assets/css/app.css?c38ada11529d60265d8b',
  '/mindmap-app/ru-ui.css?v=13',
  '/mindmap-app/assets/js/chunk-vendors.js?c38ada11529d60265d8b',
  '/mindmap-app/assets/js/chunk-ef5c9f42.js',
  '/mindmap-app/assets/js/app.js?c38ada11529d60265d8b&v=ro1',
  '/mindmap-app/ru-i18n.js?v=21',
] as const

function prefetchAsset(href: string) {
  if (typeof document === 'undefined') return
  if (document.head.querySelector(`link[data-mindmap-warmup="${href}"]`)) return
  const link = document.createElement('link')
  link.rel = 'prefetch'
  link.as = href.endsWith('.css') ? 'style' : href.endsWith('.js') ? 'script' : undefined
  link.href = href
  link.setAttribute('data-mindmap-warmup', href)
  document.head.appendChild(link)
}

/** Лёгкий prefetch статики — не монтирует iframe. */
export function warmupMindmapAssets() {
  if (assetsWarmed || typeof document === 'undefined') return
  assetsWarmed = true
  for (const href of MINDMAP_ASSETS) prefetchAsset(href)
}

/** Скрытый iframe прогревает полный embed (JS-парсинг + кэш). Вызывать при наведении / разделе «Карты». */
export function warmupMindmapEmbed() {
  warmupMindmapAssets()
  if (embedWarmed || typeof document === 'undefined') return
  embedWarmed = true
  const frame = document.createElement('iframe')
  frame.src = '/mindmap-app/embed.html?v=logical21&preload=1'
  frame.title = 'Предзагрузка редактора карт'
  frame.setAttribute('aria-hidden', 'true')
  frame.tabIndex = -1
  frame.style.cssText =
    'position:fixed;width:0;height:0;border:0;opacity:0;pointer-events:none;visibility:hidden;'
  document.body.appendChild(frame)
}

/** Отложенный прогрев — не мешает первой отрисовке списка заметок. */
export function scheduleMindmapWarmup(delayMs = 1200) {
  if (typeof window === 'undefined') return
  if (embedWarmTimer) clearTimeout(embedWarmTimer)
  embedWarmTimer = setTimeout(() => {
    embedWarmTimer = null
    const idle = (window as Window & { requestIdleCallback?: (cb: () => void) => number })
      .requestIdleCallback
    if (idle) idle(() => warmupMindmapEmbed())
    else warmupMindmapEmbed()
  }, delayMs)
}

export function primeMindmapOnIntent() {
  warmupMindmapAssets()
  if (embedWarmTimer) {
    clearTimeout(embedWarmTimer)
    embedWarmTimer = null
  }
  warmupMindmapEmbed()
}
