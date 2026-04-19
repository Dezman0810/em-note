import { Extension } from '@tiptap/core'

/**
 * Enter в пункте чек-листа должен вызывать splitListItem раньше core Keymap (splitBlock).
 * Приоритет выше любых узлов — иначе текст «уезжает» от чекбокса / не создаётся новый пункт.
 */
export const TaskListEnterKeymap = Extension.create({
  name: 'taskListEnterKeymap',

  priority: 10000,

  addKeyboardShortcuts() {
    return {
      Enter: ({ editor }) => {
        if (!editor.isActive('taskItem')) return false
        return editor.commands.splitListItem('taskItem')
      },
    }
  },
})
