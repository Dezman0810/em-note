/** Резолвер для NodeView вложений: авторизованный или публичный режим. */
type BlobResolver = (attachmentId: string) => Promise<Blob>

let resolver: BlobResolver | null = null

export function registerAttachmentBlobResolver(fn: BlobResolver | null) {
  resolver = fn
}

export async function fetchAttachmentBlob(attachmentId: string): Promise<Blob> {
  if (!resolver) {
    throw new Error('Attachment loader not configured')
  }
  return resolver(attachmentId)
}
