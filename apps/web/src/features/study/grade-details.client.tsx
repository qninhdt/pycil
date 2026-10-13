'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { ChevronDown } from '@/components/artwork/artwork'
import type { Diagnostic } from '@/lib/api/study'

export function GradeDetails({ grade }: { grade: Diagnostic | null }) {
  const [open, setOpen] = useState(false)
  const t = useTranslations('learning')
  const tCommon = useTranslations('common')
  if (!grade) return null


  const valueLabels: Record<string, string> = {
    correct: t('correct'), approximate: t('approximate'), wrong: t('needsWork'),
    accurate: t('accurate'), mixed: t('mixed'), inaccurate: t('inaccurate'),
    sufficient: t('sufficient'), partial: t('partial'), minimal: t('minimal'),
    spelling_error: t('spellingIssue'), form_error: t('formIssue'),
    preserved: t('preserved'), changed: t('changed'),
  }
  const fieldLabels: Record<string, string> = {
    correct: t('meaningMatch'), task_fit: t('taskFit'), spelling_error: t('formMatch'),
    accuracy: t('accuracy'), coverage: t('coverage'), used: t('targetUsed'),
    meaning: t('meaningMatch'), form: t('formMatch'), construction: t('grammarConstruction'),
    collocation: t('collocationUsage'), appropriacy: t('appropriacyUsage'),
    meaning_preservation: t('nuancePreserved'),
  }

  const d = grade
  const pills: { key: string; label: string; value: string; status: 'pass' | 'fail' | 'warn' }[] = []

  if ('correct' in d && typeof d.correct === 'boolean') {
    pills.push({
      key: 'correct',
      label: t('meaningMatch'),
      value: d.correct ? t('correct') : t('needsWork'),
      status: d.correct ? 'pass' : 'fail',
    })
  }

  if ('task_fit' in d && typeof d.task_fit === 'boolean') {
    pills.push({
      key: 'task_fit',
      label: t('taskFit'),
      value: d.task_fit ? t('correct') : t('needsWork'),
      status: d.task_fit ? 'pass' : 'fail',
    })
  }

  if ('meaning' in d && typeof d.meaning === 'string' && d.meaning) {
    const isExact = d.meaning === 'correct'
    const isRelated = d.meaning === 'approximate'
    pills.push({
      key: 'meaning',
      label: t('meaningMatch'),
      value: isExact ? t('exact') : isRelated ? t('approximate') : t('needsWork'),
      status: isExact ? 'pass' : isRelated ? 'warn' : 'fail',
    })
  }

  if ('accuracy' in d && typeof d.accuracy === 'string' && d.accuracy) {
    const isAccurate = d.accuracy === 'accurate'
    pills.push({
      key: 'accuracy',
      label: t('meaningMatch'),
      value: isAccurate ? t('correct') : valueLabels[d.accuracy],
      status: isAccurate ? 'pass' : 'warn',
    })
  }

  if ('spelling_error' in d && typeof d.spelling_error === 'boolean') {
    pills.push({
      key: 'spelling',
      label: t('formMatch'),
      value: d.spelling_error ? t('spellingIssue') : t('noSpellingError'),
      status: d.spelling_error ? 'warn' : 'pass',
    })
  } else if ('form' in d && typeof d.form === 'string' && d.form) {
    const isCorrect = d.form === 'correct'
    pills.push({
      key: 'form',
      label: t('formMatch'),
      value: isCorrect ? t('correct') : valueLabels[d.form],
      status: isCorrect ? 'pass' : 'warn',
    })
  }

  if ('construction' in d && typeof d.construction === 'boolean' && d.construction !== null) {
    pills.push({
      key: 'construction',
      label: t('grammarConstruction'),
      value: d.construction ? t('correct') : t('needsWork'),
      status: d.construction ? 'pass' : 'fail',
    })
  }

  if ('collocation' in d && typeof d.collocation === 'boolean' && d.collocation !== null) {
    pills.push({
      key: 'collocation',
      label: t('collocationUsage'),
      value: d.collocation ? t('naturalCollocation') : t('needsWork'),
      status: d.collocation ? 'pass' : 'warn',
    })
  }

  if ('appropriacy' in d && typeof d.appropriacy === 'boolean' && d.appropriacy !== null) {
    pills.push({
      key: 'appropriacy',
      label: t('appropriacyUsage'),
      value: d.appropriacy ? t('correct') : t('needsWork'),
      status: d.appropriacy ? 'pass' : 'warn',
    })
  }

  if ('meaning' in d && 'meaning_preservation' in d && typeof d.meaning_preservation === 'string' && d.meaning_preservation) {
    const isPreserved = d.meaning_preservation === 'preserved'
    pills.push({
      key: 'preservation',
      label: t('nuancePreserved'),
      value: isPreserved ? t('exact') : valueLabels[d.meaning_preservation],
      status: isPreserved ? 'pass' : 'warn',
    })
  }

  const allEntries = Object.entries(grade).filter(([key]) => key !== 'sense_id')

  return (
    <div className="mt-3 pt-3 border-t border-border/80">
      <div className="flex items-center flex-wrap gap-2 text-xs">
        {pills.map(pill => (
          <span
            key={pill.key}
            className={`inline-flex items-center gap-1.5 px-2 py-0.5 border text-[11px] font-semibold ${
              pill.status === 'pass'
                ? 'border-art-blue/40 bg-art-blue/10 text-art-blue'
                : pill.status === 'fail'
                  ? 'border-art-red/40 bg-art-red/10 text-art-red'
                  : 'border-art-yellow/40 bg-art-yellow/15 text-art-yellow'
            }`}
          >
            <span
              className={`size-1.5 rounded-full ${
                pill.status === 'pass'
                  ? 'bg-art-blue'
                  : pill.status === 'fail'
                    ? 'bg-art-red'
                    : 'bg-art-yellow'
              }`}
              aria-hidden="true"
            />
            <span className="text-muted-foreground font-normal">{pill.label}:</span>
            <span>{pill.value}</span>
          </span>
        ))}
        {allEntries.length > 0 && (
          <button
            type="button"
            onClick={() => setOpen(prev => !prev)}
            className="inline-flex items-center gap-1 text-[11px] font-bold text-muted-foreground hover:text-foreground underline decoration-dotted underline-offset-2 ml-auto cursor-pointer"
            aria-expanded={open}
          >
            {t('diagnosticDetails')}
            <ChevronDown className={`size-3 transition-transform duration-150 ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
          </button>
        )}
      </div>

      {open && (
        <div className="mt-2.5 p-3 bg-muted/40 border border-border text-xs">
          <dl className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
            {allEntries.map(([key, value]) => (
              <div key={key} className="flex flex-col gap-0.5">
                <dt className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold">
                  {fieldLabels[key]}
                </dt>
                <dd className="font-semibold text-foreground capitalize">
                  {value === null
                    ? tCommon('notAssessed')
                    : typeof value === 'boolean'
                      ? value
                        ? tCommon('yes')
                        : tCommon('no')
                      : valueLabels[String(value)]}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  )
}
