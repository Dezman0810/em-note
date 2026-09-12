import { beforeEach, describe, expect, it, vi } from 'vitest'
import { cachedGet, clearRequestCache, invalidateCache } from './requestCache'

function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

describe('cachedGet', () => {
  beforeEach(() => {
    clearRequestCache()
    vi.useRealTimers()
  })

  it('склеивает одновременные запросы с одним ключом в один вызов', async () => {
    const d = deferred<string[]>()
    const run = vi.fn(() => d.promise)

    const first = cachedGet('tags:list', 0, run)
    const second = cachedGet('tags:list', 0, run)
    d.resolve(['a'])

    expect(await first).toEqual(['a'])
    expect(await second).toEqual(['a'])
    expect(run).toHaveBeenCalledTimes(1)
  })

  it('разные ключи выполняются независимо', async () => {
    const run = vi.fn(async (v: string) => [v])
    await Promise.all([
      cachedGet('folders:list:', 0, () => run('folders')),
      cachedGet('tags:list', 0, () => run('tags')),
    ])
    expect(run).toHaveBeenCalledTimes(2)
  })

  it('при ttl = 0 следующий запрос идёт на сервер заново', async () => {
    const run = vi.fn(async () => ['x'])
    await cachedGet('notes:list:', 0, run)
    await cachedGet('notes:list:', 0, run)
    expect(run).toHaveBeenCalledTimes(2)
  })

  it('внутри ttl отдаёт сохранённое значение без запроса', async () => {
    const run = vi.fn(async () => ['x'])
    await cachedGet('tags:list', 10_000, run)
    await cachedGet('tags:list', 10_000, run)
    expect(run).toHaveBeenCalledTimes(1)
  })

  it('после истечения ttl запрашивает снова', async () => {
    const run = vi.fn(async () => ['x'])
    const now = vi.spyOn(Date, 'now')
    now.mockReturnValue(1_000)
    await cachedGet('tags:list', 5_000, run)
    now.mockReturnValue(6_500)
    await cachedGet('tags:list', 5_000, run)
    expect(run).toHaveBeenCalledTimes(2)
    now.mockRestore()
  })

  it('invalidateCache по префиксу сбрасывает только свои ключи', async () => {
    const tags = vi.fn(async () => ['t'])
    const folders = vi.fn(async () => ['f'])
    await cachedGet('tags:list', 10_000, tags)
    await cachedGet('folders:list:', 10_000, folders)

    invalidateCache('tags:')

    await cachedGet('tags:list', 10_000, tags)
    await cachedGet('folders:list:', 10_000, folders)
    expect(tags).toHaveBeenCalledTimes(2)
    expect(folders).toHaveBeenCalledTimes(1)
  })

  it('массив отдаётся копией: правка результата не портит кеш', async () => {
    const run = vi.fn(async () => ['a', 'b'])
    const first = await cachedGet('tags:list', 10_000, run)
    first.push('лишнее')
    const second = await cachedGet('tags:list', 10_000, run)
    expect(second).toEqual(['a', 'b'])
  })

  it('ошибка не кешируется и не блокирует следующий запрос', async () => {
    const run = vi
      .fn<() => Promise<string[]>>()
      .mockRejectedValueOnce(new Error('сеть'))
      .mockResolvedValueOnce(['ok'])

    await expect(cachedGet('tags:list', 10_000, run)).rejects.toThrow('сеть')
    expect(await cachedGet('tags:list', 10_000, run)).toEqual(['ok'])
    expect(run).toHaveBeenCalledTimes(2)
  })

  it('clearRequestCache убирает и кеш, и запись о выполняющемся запросе', async () => {
    const run = vi.fn(async () => ['x'])
    await cachedGet('tags:list', 10_000, run)
    clearRequestCache()
    await cachedGet('tags:list', 10_000, run)
    expect(run).toHaveBeenCalledTimes(2)
  })
})
