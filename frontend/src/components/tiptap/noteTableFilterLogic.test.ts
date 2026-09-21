import { describe, expect, it } from 'vitest'
import { Schema } from '@tiptap/pm/model'
import { getSchema } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import { TableKit } from '@tiptap/extension-table'
import { NoteTableCell, NoteTableHeader } from './noteTableSizingCells'
import {
  EMPTY_CELL_LABEL,
  getColumnUniqueValues,
  rowMatchesTableFilters,
  tableHasHeaderRow,
} from './noteTableFilterLogic'

function buildSchema(): Schema {
  return getSchema([
    StarterKit.configure({ heading: { levels: [2, 3] } }),
    TableKit.configure({ tableCell: false, tableHeader: false }),
    NoteTableCell,
    NoteTableHeader,
  ])
}

function makeTableDoc(schema: Schema) {
  const header = schema.nodes.tableHeader.create({}, schema.nodes.paragraph.create({}, schema.text('City')))
  const h2 = schema.nodes.tableHeader.create({}, schema.nodes.paragraph.create({}, schema.text('Status')))
  const row1c1 = schema.nodes.tableCell.create({}, schema.nodes.paragraph.create({}, schema.text('Moscow')))
  const row1c2 = schema.nodes.tableCell.create({}, schema.nodes.paragraph.create({}, schema.text('Active')))
  const row2c1 = schema.nodes.tableCell.create({}, schema.nodes.paragraph.create({}, schema.text('Berlin')))
  const row2c2 = schema.nodes.tableCell.create({}, schema.nodes.paragraph.create({}, schema.text('Paused')))

  const table = schema.nodes.table.create({}, [
    schema.nodes.tableRow.create({}, [header, h2]),
    schema.nodes.tableRow.create({}, [row1c1, row1c2]),
    schema.nodes.tableRow.create({}, [row2c1, row2c2]),
  ])
  return schema.nodes.doc.create({}, [table])
}

describe('noteTableFilterLogic', () => {
  it('detects header row and unique values', () => {
    const schema = buildSchema()
    const doc = makeTableDoc(schema)
    const table = doc.firstChild!
    expect(tableHasHeaderRow(table)).toBe(true)
    expect(getColumnUniqueValues(table, 0)).toEqual(['Berlin', 'Moscow'])
    expect(getColumnUniqueValues(table, 1)).toEqual(['Active', 'Paused'])
  })

  it('filters rows with AND across columns', () => {
    const schema = buildSchema()
    const table = makeTableDoc(schema).firstChild!
    const filters = {
      0: new Set(['Moscow']),
      1: new Set(['Active']),
    }
    expect(rowMatchesTableFilters(table, 1, filters)).toBe(true)
    expect(rowMatchesTableFilters(table, 2, filters)).toBe(false)
  })

  it('treats empty cells as blank label', () => {
    const schema = buildSchema()
    const emptyCell = schema.nodes.tableCell.create({}, schema.nodes.paragraph.create())
    const row = schema.nodes.tableRow.create({}, [emptyCell])
    const table = schema.nodes.table.create({}, [row])
    expect(getColumnUniqueValues(table, 0)).toEqual([EMPTY_CELL_LABEL])
  })
})
