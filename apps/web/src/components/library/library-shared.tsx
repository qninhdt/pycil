'use client'

import { useTranslations } from 'next-intl'
import { Search, X, ArrowLeft, ArrowRight } from '@/components/artwork/artwork'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { InputGroup, InputGroupAddon, InputGroupInput, InputGroupButton } from '@/components/ui/input-group'
import { Empty, EmptyHeader, EmptyTitle, EmptyDescription, EmptyContent } from '@/components/ui/empty'
import { StatusShape } from '@/components/home/home-state'
import { learningLabel, type LearningState } from '@/lib/library-model'

export function LearningBadge({ state }: { state: LearningState }) {
  return <Badge variant="outline"><StatusShape state={state === 'due' ? 'due' : state === 'new' ? 'new' : 'not-due'} />{learningLabel(state)}</Badge>
}

export function LibrarySearch({ value, onChange, label }: { value: string; onChange: (value: string) => void; label: string }) {
  return <InputGroup className="w-[min(360px,100%)] max-w-[360px] flex-[1_1_224px] max-[767px]:w-full max-[767px]:max-w-none max-[767px]:basis-full">
    <InputGroupInput type="text" inputMode="search" role="searchbox" aria-label={label} placeholder={label} value={value} maxLength={200} onChange={event => onChange(event.target.value)} />
    <InputGroupAddon><Search aria-hidden="true" /></InputGroupAddon>
    {value && <InputGroupAddon align="inline-end"><InputGroupButton aria-label={`Clear ${label.toLowerCase()}`} onClick={() => onChange('')}><X aria-hidden="true" /></InputGroupButton></InputGroupAddon>}
  </InputGroup>
}

export function LibraryEmpty({ title, description, reset }: { title: string; description?: string; reset?: () => void }) {
  const t = useTranslations('library')
  return <Empty className="min-h-60"><EmptyHeader><EmptyTitle>{title}</EmptyTitle>{description && <EmptyDescription>{description}</EmptyDescription>}</EmptyHeader>
    {reset && <EmptyContent><Button variant="outline" onClick={reset}>{t('clearFilters')}</Button></EmptyContent>}
  </Empty>
}

export function LibraryPagination({ previous, next, page, busy = false }: { previous?: () => void; next?: () => void; page: number; busy?: boolean }) {
  const t = useTranslations('library')
  const tCommon = useTranslations('common')
  return <nav className="flex items-center justify-between gap-4 border-t border-border pt-5 mt-3 text-xs text-muted-foreground [&_>_div]:flex [&_>_div]:gap-2 max-[767px]:items-start max-[767px]:flex-wrap" aria-label={t('pagination')}><span aria-live="polite">{tCommon('page', { page })}</span><div>
    <Button variant="outline" size="sm" onClick={previous} disabled={!previous || busy} aria-label={t('previousPage')}><ArrowLeft data-icon="inline-start" aria-hidden="true" />{tCommon('previous')}</Button>
    <Button variant="outline" size="sm" onClick={next} disabled={!next || busy} aria-label={t('nextPage')}>{tCommon('next')}<ArrowRight data-icon="inline-end" aria-hidden="true" /></Button>
  </div></nav>
}
