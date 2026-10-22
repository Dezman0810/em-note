/**
 * Пустая сцена в формате экспорта .excalidraw.
 *
 * Строка задана литералом, а не через restore/serializeAsJSON: импорт из
 * `@excalidraw/excalidraw` здесь затягивал весь пакет (~4,5 МБ) в стартовую загрузку
 * списка заметок. Недостающие поля appState дополняет restore() в ExcalidrawApp.parseScene.
 */
export const DEFAULT_EXCALIDRAW_SCENE = JSON.stringify({
  type: 'excalidraw',
  version: 2,
  source: 'em-note',
  elements: [],
  appState: { viewBackgroundColor: '#ffffff' },
  files: {},
})
