import axios, { isAxiosError } from 'axios'
import type { Folder, Note, NoteShare, Tag, TagNoteCount, User } from './types'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? '',
  headers: { 'Content-Type': 'application/json' },
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
  folder_id?: string
  unfoldered?: boolean
  tag_id?: string
}

export const notesApi = {
  async list(params?: NotesListParams): Promise<Note[]> {
    const { data } = await api.get<Note[]>('/api/notes', { params })
    return data
  },
  async search(q: string, params?: NotesListParams): Promise<Note[]> {
    const { data } = await api.get<Note[]>('/api/notes/search', { params: { q, ...params } })
    return data
  },
  async get(id: string): Promise<Note> {
    const { data } = await api.get<Note>(`/api/notes/${id}`)
    return data
  },
  async create(
    body: Partial<Pick<Note, 'title' | 'content_json' | 'content_plain' | 'folder_id'>>
  ): Promise<Note> {
    const { data } = await api.post<Note>('/api/notes', body)
    return data
  },
  async update(
    id: string,
    body: Partial<Pick<Note, 'title' | 'content_json' | 'content_plain' | 'folder_id'>>
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
  async detachTag(noteId: string, tagId: string): Promise<Note> {
    const { data } = await api.delete<Note>(`/api/notes/${noteId}/tags/${tagId}`)
    return data
  },
}

export const foldersApi = {
  async list(forNoteId?: string): Promise<Folder[]> {
    const { data } = await api.get<Folder[]>('/api/folders', {
      params: forNoteId ? { for_note_id: forNoteId } : {},
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
  folder_id?: string
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
    const { data } = await api.get<Tag[]>('/api/tags')
    return data
  },
  async noteCounts(params?: TagsNoteCountsParams): Promise<TagNoteCount[]> {
    const { data } = await api.get<unknown>('/api/tags/counts', { params: params ?? {} })
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

export const mailApi = {
  async sendNote(body: { note_id: string; to_emails: string[]; extra_message?: string }) {
    const { data } = await api.post<{ status: string }>('/api/mail/send-note', body)
    return data
  },
}

export { api }
