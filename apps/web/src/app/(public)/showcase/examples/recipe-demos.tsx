import { useState } from 'react'
import {
  columnFilteringFeature, createColumnHelper, createFilteredRowModel,
  createPaginatedRowModel, createSortedRowModel, filterFn_includesString,
  rowPaginationFeature, rowSortingFeature, sortFn_text, tableFeatures, useTable,
  type ColumnFiltersState, type SortingState,
} from '@tanstack/react-table'
import { ArrowUpDown, CalendarDays } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

function DatePickerDemo() {
  const [date, setDate] = useState<Date>()
  const [open, setOpen] = useState(false)
  return <FieldGroup><Field><FieldLabel htmlFor="study-date">Study date</FieldLabel>
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild><Button id="study-date" variant="outline"><CalendarDays data-icon="inline-start" />{date ? date.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' }) : 'Pick a study date'}</Button></PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start"><Calendar mode="single" selected={date} defaultMonth={date || new Date(2026, 9, 1)} onSelect={selected => { setDate(selected); setOpen(false) }} /></PopoverContent>
    </Popover>
  </Field><p className="text-xs text-muted-foreground leading-relaxed mt-4">The official date-picker recipe composes Calendar and Popover; it is not another registry primitive.</p></FieldGroup>
}

const features = tableFeatures({
  columnFilteringFeature, rowSortingFeature, rowPaginationFeature,
  filteredRowModel: createFilteredRowModel(), sortedRowModel: createSortedRowModel(),
  paginatedRowModel: createPaginatedRowModel(),
  filterFns: { includesString: filterFn_includesString }, sortFns: { text: sortFn_text },
})
type Study = { name: string; kind: string; items: number }
const helper = createColumnHelper<typeof features, Study>()
const studies: Study[] = [
  { name: 'Color studies', kind: 'Collection', items: 12 },
  { name: 'Everyday architecture', kind: 'Folder', items: 18 },
  { name: 'Form & function', kind: 'Collection', items: 24 },
  { name: 'Notes from Dessau', kind: 'Document', items: 8 },
  { name: 'Objects of interest', kind: 'Collection', items: 42 },
  { name: 'New perspectives', kind: 'Folder', items: 16 },
]
const columns = helper.columns([
  helper.accessor('name', {
    filterFn: 'includesString', sortFn: 'text',
    header: ({ column }) => <Button variant="ghost" size="sm" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>Study name <ArrowUpDown data-icon="inline-end" /></Button>,
  }),
  helper.accessor('kind', { header: 'Type', enableSorting: false }),
  helper.accessor('items', { header: 'Items', enableSorting: false }),
])

function DataTableDemo() {
  const [sorting, setSorting] = useState<SortingState>([])
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([])
  const table = useTable({
    features, columns, data: studies,
    initialState: { pagination: { pageSize: 3, pageIndex: 0 } },
    state: { sorting, columnFilters }, onSortingChange: setSorting, onColumnFiltersChange: setColumnFilters,
  })
  return <div className="flex flex-col gap-5" data-testid="data-table-recipe">
    <Field><FieldLabel htmlFor="filter-studies">Filter studies</FieldLabel><Input id="filter-studies" placeholder="Search this table…"
      value={(table.getColumn('name')?.getFilterValue() as string) || ''} onChange={event => table.getColumn('name')?.setFilterValue(event.target.value)} /></Field>
    <Table><TableHeader>{table.getHeaderGroups().map(group => <TableRow key={group.id}>{group.headers.map(header => <TableHead key={header.id}>{header.isPlaceholder ? null : <table.FlexRender header={header} />}</TableHead>)}</TableRow>)}</TableHeader>
      <TableBody>{table.getRowModel().rows.length ? table.getRowModel().rows.map(row => <TableRow key={row.id}>{row.getAllCells().map(cell => <TableCell key={cell.id}><table.FlexRender cell={cell} /></TableCell>)}</TableRow>) : <TableRow><TableCell colSpan={3}>No studies match.</TableCell></TableRow>}</TableBody>
    </Table>
    <div className="flex flex-wrap items-center gap-2.5"><Button variant="outline" size="sm" onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()}>Previous studies</Button>
      <span className="text-sm" aria-live="polite">Page {table.state.pagination.pageIndex + 1} of {Math.max(1, table.getPageCount())}</span>
      <Button variant="outline" size="sm" onClick={() => table.nextPage()} disabled={!table.getCanNextPage()}>Next studies</Button></div>
    <p className="text-xs text-muted-foreground leading-relaxed mt-4">TanStack Table v9 + the owned shadcn Table. Filter, sort and paginate local rows.</p>
  </div>
}

export const recipeDemos = [
  { title: 'Date picker', components: 'Popover · Calendar · Field', code: '<Popover><PopoverTrigger asChild><Button>Pick a date</Button></PopoverTrigger><PopoverContent><Calendar mode="single" selected={date} onSelect={setDate} /></PopoverContent></Popover>', render: DatePickerDemo },
  { title: 'Data table', components: 'Table · TanStack Table · Input · Button', code: 'const table = useTable({ features, columns, data })\n<Table><TableBody>{table.getRowModel().rows.map(row => <TableRow key={row.id}>{row.getAllCells().map(cell => <TableCell key={cell.id}><table.FlexRender cell={cell} /></TableCell>)}</TableRow>)}</TableBody></Table>', render: DataTableDemo, wide: true },
]
