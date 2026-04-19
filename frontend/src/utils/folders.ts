import type { Folder } from '../api/types'

export function foldersSortedAlphabetical(folders: Folder[]): Folder[] {
  return [...folders].sort((a, b) => a.name.localeCompare(b.name, 'ru'))
}
