import TaskItem from '@tiptap/extension-task-item'

/**
 * Один абзац на пункт чек-листа (Enter даёт новый пункт, а не второй абзац в той же ячейке).
 * Без input rules — чекбоксы только через кнопку «Чек-лист», не по вводу "- [ ]".
 */
export const TaskItemNote = TaskItem.extend({
  /**
   * Выше, чем у core Keymap (100): сначала Enter → splitListItem для чек-листа,
   * иначе splitBlock вставляет «перенос» без нового пункта / ломает строку у чекбокса.
   */
  priority: 1000,

  content: 'paragraph',

  addInputRules() {
    return []
  },
})
