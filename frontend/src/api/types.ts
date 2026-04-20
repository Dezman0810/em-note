export interface User {
  id: string
  email: string
  display_name: string
  created_at: string
  /** Если false — нельзя создавать новые заметки (выдаёт только админ). */
  can_create_notes: boolean
  /** Единственный email из настроек API; видит админку. */
  is_admin: boolean
}

export interface AdminUserRow {
  id: string
  email: string
  display_name: string
  created_at: string
  can_create_notes: boolean
}

export interface Note {
  id: string
  owner_id: string
  title: string
  content_json: string
  content_plain: string
  created_at: string
  updated_at: string
  deleted_at: string | null
  folder_id: string | null
  accent_color: string
  reminder_at: string | null
  tag_ids: string[]
}

export interface Folder {
  id: string
  user_id: string
  name: string
  created_at: string
}

export interface Tag {
  id: string
  user_id: string
  parent_id: string | null
  name: string
  slug: string
  depth: number
  created_at: string
}

export interface TagNoteCount {
  tag_id: string
  count: number
}

export interface FolderNoteCounts {
  total: number
  unfoldered: number
  folder_counts: { folder_id: string; count: number }[]
}

export interface NoteShare {
  id: string
  note_id: string
  shared_with_user_id: string | null
  invite_email: string | null
  role: string
  created_at: string
}

export interface NotePublicLink {
  token: string
  role: string
  created_at: string
}

export interface PublicNotePayload {
  note: Note
  can_edit: boolean
  role: string
}
