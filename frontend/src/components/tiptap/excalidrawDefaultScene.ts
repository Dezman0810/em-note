import { restore, serializeAsJSON } from '@excalidraw/excalidraw'

/** Пустая сцена в том же формате, что и экспорт .excalidraw */
const empty = restore(
  {
    elements: [],
    appState: { viewBackgroundColor: '#ffffff' },
    files: {},
  },
  null,
  null
)

export const DEFAULT_EXCALIDRAW_SCENE = serializeAsJSON(empty.elements, empty.appState, empty.files, 'local')
