import axios, { isAxiosError } from 'axios'
import type {
  AdminUserRow,
  AttachmentMeta,
  Folder,
  FolderNoteCounts,
  Note,
  NotePublicLink,
  NoteShare,
  PublicNotePayload,
  Tag,
  TagNoteCount,
  User,
} from './types'

export type TagAttachByNameResponse = { note: Note; tag: Tag }

const TOKEN_STORAGE_KEY = 'note_token'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? '',
  headers: { 'Content-Type': 'application/json' },
})

/** Всегда подставлять JWT из localStorage — надёжнее, чем только axios.defaults (админка и т.д.). */
api.interceptors.request.use((config) => {
  if (typeof localStorage !== 'undefined') {
    const t = localStorage.getItem(TOKEN_STORAGE_KEY)
    if (t) {
      config.headers.Authorization = `Bearer ${t}`
    }
  }
  return config
})

export function setAuthToken(token: string | null) {
  if (token) {
    api.defaults.headers.common.Authorization = `Bearer ${token}`
  } else {
    delete api.defaults.headers.common.Authorization
  }
}

export function errMessage(e: unknown): string {
  if (isAxiosError(e)) {
    const d = e.response?.data as { detail?: string | object } | undefined
    if (typeof d?.detail === 'string') return d.detail
    if (Array.isArray(d?.detail)) return JSON.stringify(d.detail)
  }
  if (e instanceof Error) return e.message
  return 'Request failed'
}

export const adminApi = {
  async listUsers(): Promise<AdminUserRow[]> {
    const { data } = await api.get<AdminUserRow[]>('/api/admin/users')
    return data
  },
  async setCanCreateNotes(userId: string, can_create_notes: boolean): Promise<AdminUserRow> {
    const { data } = await api.patch<AdminUserRow>(`/api/admin/users/${userId}`, { can_create_notes })
    return data
  },
}

export const authApi = {
  async register(body: { email: string; password: string; display_name?: string }): Promise<User> {
    const { data } = await api.post<User>('/api/auth/register', body)
    return data
  },
  async login(body: { email: string; password: string }): Promise<{ access_token: string }> {
    const { data } = await api.post('/api/auth/login', body)
    return data
  },
  async me(): Promise<User> {
    const { data } = await api.get<User>('/api/auth/me')
    return data
  },
}

export type NotesListParams = {
  /** Одна папка или несколько; повтор `folder_id` в query. */
  folder_id?: string | string[]
  unfoldered?: boolean
  /** Одна метка или несколько; на сервер уходит повторяющийся query `tag_id`. */
  tag_id?: string | string[]
}

const REPEAT_QUERY_KEYS = new Set(['tag_id', 'folder_id'])

function serializeRepeatKeyQuery(params: Record<string, unknown>): string {
  const usp = new URLSearchParams()
  for (const [key, val] of Object.entries(params)) {
    if (val === undefined || val === null) continue
    if (REPEAT_QUERY_KEYS.has(key) && Array.isArray(val)) {
      for (const id of val) {
        if (id !== undefined && id !== null) usp.append(key, String(id))
      }
      continue
    }
    if (typeof val === 'boolean') {
      if (val) usp.append(key, 'true')
      continue
    }
    usp.append(key, String(val))
  }
  return usp.toString()
}

export const notesApi = {
  async listReminders(params: { from: string; to: string }): Promise<Note[]> {
    const { data } = await api.get<Note[]>('/api/notes/reminders', { params })
    return data
  },
  async list(params?: NotesListParams): Promise<Note[]> {
    const { data } = await api.get<Note[]>('/api/notes', {
      params: { ...params, _ts: Date.now() },
      paramsSerializer: { serialize: serializeRepeatKeyQuery },
    })
    return data
  },
  async search(q: string, params?: NotesListParams): Promise<Note[]> {
    const { data } = await api.get<Note[]>('/api/notes/search', {
      params: { q, ...params, _ts: Date.now() },
      paramsSerializer: { serialize: serializeRepeatKeyQuery },
    })
    return data
  },
  async get(id: string): Promise<Note> {
    const { data } = await api.get<Note>(`/api/notes/${id}`)
    return data
  },
  async create(
    body: Partial<
      Pick<Note, 'title' | 'content_json' | 'content_plain' | 'folder_id' | 'reminder_at'>
    >
  ): Promise<Note> {
    const { data } = await api.post<Note>('/api/notes', body)
    return data
  },
  async update(
    id: string,
    body: Partial<
      Pick<Note, 'title' | 'content_json' | 'content_plain' | 'folder_id' | 'reminder_at'>
    >
  ): Promise<Note> {
    const { data } = await api.patch<Note>(`/api/notes/${id}`, body)
    return data
  },
  async remove(id: string): Promise<void> {
    await api.delete(`/api/notes/${id}`)
  },
  async listTrash(): Promise<Note[]> {
    const { data } = await api.get<Note[]>('/api/notes', { params: { trash_only: true } })
    return data
  },
  async restore(id: string): Promise<Note> {
    const { data } = await api.post<Note>(`/api/notes/${id}/restore`)
    return data
  },
  async purge(id: string): Promise<void> {
    await api.delete(`/api/notes/${id}/permanent`)
  },
  async attachTag(noteId: string, tagId: string): Promise<Note> {
    const { data } = await api.post<Note>(`/api/notes/${noteId}/tags/${tagId}`)
    return data
  },
  /** Создать метку у владельца заметки по имени и прикрепить (устраняет Tag not found при Enter). */
  async attachTagByName(noteId: string, name: string): Promise<TagAttachByNameResponse> {
    const { data } = await api.post<TagAttachByNameResponse>(`/api/notes/${noteId}/tags/by-name`, { name })
    return data
  },
  async detachTag(noteId: string, tagId: string): Promise<Note> {
    const { data } = await api.delete<Note>(`/api/notes/${noteId}/tags/${tagId}`)
    return data
  },
  async getPublicLink(noteId: string): Promise<NotePublicLink> {
    const { data } = await api.get<NotePublicLink>(`/api/notes/${noteId}/public-link`)
    return data
  },
  async upsertPublicLink(noteId: string, body: { role: string }): Promise<NotePublicLink> {
    const { data } = await api.put<NotePublicLink>(`/api/notes/${noteId}/public-link`, body)
    return data
  },
  async regeneratePublicLink(noteId: string): Promise<NotePublicLink> {
    const { data } = await api.post<NotePublicLink>(`/api/notes/${noteId}/public-link/regenerate`)
    return data
  },
  async deletePublicLink(noteId: string): Promise<void> {
    await api.delete(`/api/notes/${noteId}/public-link`)
  },
}

export const foldersApi = {
  async list(forNoteId?: string): Promise<Folder[]> {
    const { data } = await api.get<Folder[]>('/api/folders', {
      params: {
        ...(forNoteId ? { for_note_id: forNoteId } : {}),
        /* сброс кэша браузера/прокси после DELETE и т.п. */
        _t: Date.now(),
      },
      headers: { 'Cache-Control': 'no-cache', Pragma: 'no-cache' },
    })
    return data
  },
  async noteCounts(): Promise<FolderNoteCounts> {
    const { data } = await api.get<FolderNoteCounts>('/api/folders/note-counts', {
      params: { _t: Date.now() },
      headers: { 'Cache-Control': 'no-cache', Pragma: 'no-cache' },
    })
    return data
  },
  async create(body: { name: string }): Promise<Folder> {
    const { data } = await api.post<Folder>('/api/folders', body)
    return data
  },
  async update(id: string, body: { name: string }): Promise<Folder> {
    const { data } = await api.patch<Folder>(`/api/folders/${id}`, body)
    return data
  },
  async remove(id: string): Promise<void> {
    await api.delete(`/api/folders/${id}`)
  },
}

export type TagsNoteCountsParams = {
  folder_id?: string | string[]
  unfoldered?: boolean
}

/** Разбор ответа /api/tags/counts (учёт разных форматов ключей и типов). */
export function tagCountsResponseToMap(data: unknown): Record<string, number> {
  const map: Record<string, number> = {}
  if (!Array.isArray(data)) return map
  for (const row of data) {
    if (!row || typeof row !== 'object') continue
    const r = row as Record<string, unknown>
    const id = r.tag_id ?? r.tagId
    const raw = r.count
    if (id == null) continue
    const n = typeof raw === 'number' ? raw : Number(raw)
    if (Number.isNaN(n)) continue
    map[String(id)] = n
  }
  return map
}

export const tagsApi = {
  async list(): Promise<Tag[]> {
    const { data } = await api.get<Tag[]>('/api/tags', {
      params: { _ts: Date.now() },
    })
    return data
  },
  async noteCounts(params?: TagsNoteCountsParams): Promise<TagNoteCount[]> {
    const { data } = await api.get<unknown>('/api/tags/counts', {
      params: { ...(params ?? {}), _ts: Date.now() },
      paramsSerializer: { serialize: serializeRepeatKeyQuery },
    })
    if (!Array.isArray(data)) return []
    const out: TagNoteCount[] = []
    for (const row of data) {
      if (!row || typeof row !== 'object') continue
      const r = row as Record<string, unknown>
      const id = r.tag_id ?? r.tagId
      const raw = r.count
      if (id == null) continue
      const n = typeof raw === 'number' ? raw : Number(raw)
      if (Number.isNaN(n)) continue
      out.push({ tag_id: String(id), count: n })
    }
    return out
  },
  async create(body: { name: string; parent_id?: string | null }): Promise<Tag> {
    const { data } = await api.post<Tag>('/api/tags', body)
    return data
  },
  async update(id: string, body: { name?: string; parent_id?: string | null }): Promise<Tag> {
    const { data } = await api.patch<Tag>(`/api/tags/${id}`, body)
    return data
  },
  async remove(id: string): Promise<void> {
    await api.delete(`/api/tags/${id}`)
  },
}

export const sharesApi = {
  async list(noteId: string): Promise<NoteShare[]> {
    const { data } = await api.get<NoteShare[]>(`/api/notes/${noteId}/shares`)
    return data
  },
  async create(
    noteId: string,
    body: { shared_with_user_id?: string; invite_email?: string; role?: string }
  ): Promise<NoteShare> {
    const { data } = await api.post<NoteShare>(`/api/notes/${noteId}/shares`, body)
    return data
  },
  async remove(noteId: string, shareId: string): Promise<void> {
    await api.delete(`/api/notes/${noteId}/shares/${shareId}`)
  },
}

export const attachmentsApi = {
  async upload(noteId: string, file: File): Promise<AttachmentMeta> {
    const form = new FormData()
    form.append('file', file)
    const { data } = await api.post<AttachmentMeta>(`/api/notes/${noteId}/attachments`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },
  async downloadBlob(attachmentId: string): Promise<Blob> {
    const { data } = await api.get(`/api/attachments/${attachmentId}/file`, { responseType: 'blob' })
    return data
  },
  async transcribe(attachmentId: string): Promise<{ text: string }> {
    const { data } = await api.post<{ text: string }>(
      `/api/attachments/${encodeURIComponent(attachmentId)}/transcribe`,
      {}
    )
    return data
  },
}

export const publicNoteApi = {
  async get(token: string): Promise<PublicNotePayload> {
    const { data } = await api.get<PublicNotePayload>(`/api/public/notes/${encodeURIComponent(token)}`)
    return data
  },
  async update(
    token: string,
    body: Partial<Pick<Note, 'title' | 'content_json' | 'content_plain'>>
  ): Promise<Note> {
    const { data } = await api.patch<Note>(`/api/public/notes/${encodeURIComponent(token)}`, body)
    return data
  },
  async uploadAttachment(token: string, file: File): Promise<AttachmentMeta> {
    const form = new FormData()
    form.append('file', file)
    const { data } = await api.post<AttachmentMeta>(
      `/api/public/notes/${encodeURIComponent(token)}/attachments`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )
    return data
  },
  async downloadAttachmentBlob(token: string, attachmentId: string): Promise<Blob> {
    const { data } = await api.get(
      `/api/public/notes/${encodeURIComponent(token)}/attachments/${attachmentId}/file`,
      { responseType: 'blob' }
    )
    return data
  },
  async transcribeAttachment(token: string, attachmentId: string): Promise<{ text: string }> {
    const { data } = await api.post<{ text: string }>(
      `/api/public/notes/${encodeURIComponent(token)}/attachments/${encodeURIComponent(attachmentId)}/transcribe`,
      {}
    )
    return data
  },
}

export const mailApi = {
  async sendNote(body: { note_id: string; to_emails: string[]; extra_message?: string }) {
    const { data } = await api.post<{ status: string }>('/api/mail/send-note', body)
    return data
  },
}

export { api }
