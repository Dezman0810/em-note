/** Резолвер для NodeView вложений: авторизованный или публичный режим. */
type BlobResolver = (attachmentId: string) => Promise<Blob>

let resolver: BlobResolver | null = null

/**
 * Содержимое вложения неизменяемо (см. ETag/immutable на сервере), поэтому
 * держим последние файлы в памяти: повторное открытие заметки и несколько
 * NodeView одного файла больше не тянут его заново.
 */
const MAX_CACHED = 12
const cache = new Map<string, Blob>()
const inflight = new Map<string, Promise<Blob>>()

export function registerAttachmentBlobResolver(fn: BlobResolver | null) {
  resolver = fn
}

/** Смена пользователя / выход: чужие вложения не должны оставаться в памяти. */
export function clearAttachmentBlobCache(): void {
  cache.clear()
  inflight.clear()
}

function remember(id: string, blob: Blob): Blob {
  cache.delete(id)
  cache.set(id, blob)
  while (cache.size > MAX_CACHED) {
    const oldest = cache.keys().next()
    if (oldest.done) break
    cache.delete(oldest.value)
  }
  return blob
}

export async function fetchAttachmentBlob(attachmentId: string): Promise<Blob> {
  if (!resolver) {
    throw new Error('Attachment loader not configured')
  }
  const hit = cache.get(attachmentId)
  if (hit) return remember(attachmentId, hit)

  const running = inflight.get(attachmentId)
  if (running) return running

  const pending = resolver(attachmentId)
    .then((blob) => remember(attachmentId, blob))
    .finally(() => {
      inflight.delete(attachmentId)
    })
  inflight.set(attachmentId, pending)
  return pending
}
