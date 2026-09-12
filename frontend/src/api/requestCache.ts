/**
 * Дедупликация одновременных GET-запросов и короткий кеш справочников.
 *
 * Зачем: метки и папки запрашивают сразу несколько компонентов (список, редактор,
 * сайдбар), а каскад `refresh` после автосохранения повторял те же запросы ещё раз.
 * Один и тот же запрос, начатый параллельно, теперь выполняется один раз.
 *
 * `ttlMs = 0` — только дедупликация «на лету», без отдачи устаревших данных.
 */

type CacheEntry = { at: number; value: unknown }

const inflight = new Map<string, Promise<unknown>>()
const fresh = new Map<string, CacheEntry>()

/** Массивы отдаём копией: вызывающий код кладёт их в ref и мутирует. */
function detach<T>(value: T): T {
  return (Array.isArray(value) ? [...value] : value) as T
}

export async function cachedGet<T>(key: string, ttlMs: number, run: () => Promise<T>): Promise<T> {
  if (ttlMs > 0) {
    const hit = fresh.get(key)
    if (hit && Date.now() - hit.at < ttlMs) return detach(hit.value as T)
  }

  const running = inflight.get(key)
  if (running) return detach((await running) as T)

  const pending = run()
    .then((value) => {
      if (ttlMs > 0) fresh.set(key, { at: Date.now(), value })
      return value as unknown
    })
    .finally(() => {
      inflight.delete(key)
    })

  inflight.set(key, pending)
  return detach((await pending) as T)
}

/** Сбросить кеш по префиксу ключа — вызывать после изменений на сервере. */
export function invalidateCache(prefix: string): void {
  for (const key of [...fresh.keys()]) {
    if (key.startsWith(prefix)) fresh.delete(key)
  }
}

/** Полный сброс: смена пользователя (вход/выход) не должна показывать чужие данные. */
export function clearRequestCache(): void {
  fresh.clear()
  inflight.clear()
}
