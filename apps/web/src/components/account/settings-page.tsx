'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Check, LockKeyhole, Shape, Icon } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { useAccount } from '@/components/application/providers'
import { useI18n } from '@/components/application/i18n-provider'
import { useServices } from '@/lib/services/provider'
import type { AccountProfile, AnswerFormat, SettingsPatch } from '@/lib/api'



function SettingsHeader() {
  const t = useTranslations('account')
  return <header className="grid grid-cols-[minmax(0,1.3fr)_1fr_1fr_1fr] max-[767px]:grid-cols-1 items-stretch min-h-[124px] max-[767px]:min-h-0 max-[767px]:py-4 border-b border-border [&_h1]:leading-[1.12]">
    <div className="col-span-3 max-[767px]:col-span-1 min-w-0 flex flex-col justify-center py-4 pr-6 max-[767px]:p-0"><h1 className="text-[clamp(2.25rem,2.6vw,3rem)] font-extrabold leading-[1.12] tracking-[-.03em] max-[700px]:text-[34px]">{t('settings')}<span className="text-art-red" aria-hidden="true">.</span></h1></div>
    <div className="header-motif-art col-span-1 max-[767px]:hidden" aria-hidden="true"><div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center justify-center [&_svg:first-child]:size-[112px] [&_svg:last-child]:-ml-7 [&_svg:last-child]:size-[90px] [&_svg:last-child]:translate-y-[32px]"><Shape name="square" /><Shape name="triangle" /></div></div>
  </header>
}

export function SettingsPage() {
  const t = useTranslations('account')
  const tNav = useTranslations('nav')
  const tCommon = useTranslations('common')
  const { setLocale } = useI18n()
  const account = useAccount(), { services, scope } = useServices(), queryClient = useQueryClient()
  const profile = account.profile
  const [tab, setTab] = useState<'general' | 'learning'>('general')
  const [override, setOverride] = useState<{ profile: AccountProfile; settings: AccountProfile['settings'] } | null>(null)
  const draft = override?.profile === profile ? override.settings : profile?.settings ?? null
  const setDraft = (settings: AccountProfile['settings']) => { if (profile) setOverride({ profile, settings }) }
  const [saving, setSaving] = useState(false)
  if (account.status === 'signed-out') return <div className="w-full"><SettingsHeader /><div className="py-8"><p className="mb-5 text-muted-foreground">{t('signInToSettings')}</p><Button asChild><Link href="/login">{tNav('signIn')}</Link></Button></div></div>
  if (account.status === 'error') return <div className="w-full" role="alert"><SettingsHeader /><div className="py-8"><p className="mb-5 text-muted-foreground">{account.error || 'Could not load your account.'}</p><Button variant="outline" onClick={account.retry}>{tCommon('retry')}</Button></div></div>
  if (account.status === 'task') return <div className="w-full"><SettingsHeader /><div className="py-8"><p className="mb-5 text-muted-foreground">{t('verifyToEditSettings')}</p><Button asChild><Link href="/auth/continue">{tNav('continueVerification')}</Link></Button></div></div>
  if (account.status === 'loading' || !profile || !draft) return <div className="w-full py-10 text-muted-foreground" role="status">{tCommon('loading')}</div>
  const savedSettings = profile.settings
  const learning = draft.learning, options = profile.learning_options
  const changed = JSON.stringify(draft) !== JSON.stringify(savedSettings)
  let timezoneValid = true
  try { new Intl.DateTimeFormat('en', { timeZone: draft.timezone }) } catch { timezoneValid = false }
  const valid = timezoneValid && learning.question_types.length > 0 && learning.formats.length > 0 &&
    learning.question_types.some(type => (options.advanced_grading ? learning.formats : ['SINGLE_CHOICE']).some(format => options.pairs.some(pair => pair.question_type === type && pair.format === format))) &&
    learning.questions_per_sense >= options.limits.min_questions_per_sense && learning.questions_per_sense <= options.limits.max_questions_per_sense &&
    learning.max_sense_count >= 1 && learning.max_sense_count <= 20 && learning.questions_per_sense * learning.max_sense_count <= options.limits.max_questions_per_prepare
  const updateLearning = (patch: Partial<typeof learning>) => setDraft({ ...draft, learning: { ...learning, ...patch } })
  const toggle = (values: string[], value: string) => values.includes(value) ? values.filter(item => item !== value) : [...values, value]
  async function save() {
    if (!draft || !changed || !valid) return
    setSaving(true)
    try {
      const patch: SettingsPatch = {}
      for (const key of ['locale', 'timezone', 'translation_language'] as const) if (draft[key] !== savedSettings[key]) patch[key] = draft[key]
      const learningPatch: NonNullable<SettingsPatch['learning']> = {}
      for (const key of ['question_types', 'formats', 'questions_per_sense', 'max_sense_count'] as const) {
        if (JSON.stringify(draft.learning[key]) !== JSON.stringify(savedSettings.learning[key])) Object.assign(learningPatch, { [key]: draft.learning[key] })
      }
      if (Object.keys(learningPatch).length) patch.learning = learningPatch
      const next = await services.account.updateSettings(patch, new AbortController().signal)
      queryClient.setQueryData([services.mode, scope, 'account'], next)
      if (draft.locale === 'en' || draft.locale === 'vi') setLocale(draft.locale)
      toast.success(t('settingsSaved'))
    } catch (error) { toast.error(error instanceof Error ? error.message : t('couldNotSaveSettings')) }
    finally { setSaving(false) }
  }
  const questionItems = [
    { id: 'DEFINITION_TO_WORD' as const, label: t('defToWord'), description: t('defToWordDesc') },
    { id: 'WORD_TO_DEFINITION' as const, label: t('wordToDef'), description: t('wordToDefDesc') },
    { id: 'CONTEXT_TO_WORD' as const, label: t('contextToWord'), description: t('contextToWordDesc') },
    { id: 'CLOZE_TO_WORD' as const, label: t('clozeToWord'), description: t('clozeToWordDesc') },
    { id: 'DIALOGUE_COMPLETION' as const, label: t('dialogueCompletion'), description: t('dialogueCompletionDesc') },
    { id: 'WORD_TO_USAGE' as const, label: t('wordToUsage'), description: t('wordToUsageDesc') },
    { id: 'MEANING_IN_CONTEXT' as const, label: t('meaningInContext'), description: t('meaningInContextDesc') },
  ]
  const formatItems: { id: AnswerFormat; label: string; description: string }[] = [
    { id: 'SINGLE_CHOICE', label: t('multipleChoice'), description: t('multipleChoiceDesc') },
    { id: 'SINGLE_WORD', label: t('singleWord'), description: t('singleWordDesc') },
    { id: 'SHORT_ANSWER', label: t('shortAnswer'), description: t('shortAnswerDesc') },
  ]
  return <div className="w-full">
    <SettingsHeader />
    <div className="flex justify-between gap-4 py-5.5 max-[650px]:items-stretch max-[410px]:flex-wrap max-[410px]:[&_button:last-child]:w-full"><div className="inline-flex border border-border [&_button]:min-h-[42px] [&_button]:min-w-[112px] [&_button]:px-4 [&_button]:text-[13px] [&_button]:font-bold [&_button+button]:border-l [&_button+button]:border-border [&_button[aria-pressed=true]]:bg-action-red [&_button[aria-pressed=true]]:text-on-action-red max-[650px]:flex-1 max-[650px]:[&_button]:min-w-0 max-[650px]:[&_button]:flex-1" role="group" aria-label={t('settingsSections')}>
      <button type="button" aria-pressed={tab === 'general'} onClick={() => setTab('general')}>{t('general')}</button>
      <button type="button" aria-pressed={tab === 'learning'} onClick={() => setTab('learning')}>{t('learningTab')}</button>
    </div><Button onClick={save} disabled={!changed || !valid || saving}>{saving ? t('saving') : t('saveChanges')}</Button></div>
    {tab === 'general' ? <section className="mb-3 border border-border" aria-labelledby="language-heading"><div className="border-b border-border px-5.5 py-4.5 [&_h2]:text-[22px] [&_h2]:font-extrabold [&_h2]:leading-snug [&_h2]:tracking-tight max-md:[&_h2]:text-xl [&_p]:mt-1 [&_p]:text-xs [&_p]:leading-normal [&_p]:text-muted-foreground"><h2 id="language-heading">{t('languageAndRegion')}</h2><p>{t('languageDesc')}</p></div>
      <label className="grid grid-cols-[minmax(200px,1fr)_minmax(230px,320px)] items-center gap-5 px-5.5 py-5 [+&]:border-t [+&]:border-border [&_strong]:block [&_strong]:text-[13px] [&_strong]:font-extrabold [&_small]:mt-1 [&_small]:block [&_small]:text-xs [&_small]:leading-normal [&_small]:text-muted-foreground max-[650px]:grid-cols-1 max-[650px]:gap-2.5 max-[650px]:p-4"><span><strong>{t('interfaceLanguage')}</strong><small>{t('interfaceLanguageDesc')}</small></span><NativeSelect className="w-full" value={draft.locale} onChange={event => setDraft({ ...draft, locale: event.target.value })}><option value="en">English</option><option value="vi">Tiếng Việt</option></NativeSelect></label>
      <label className="grid grid-cols-[minmax(200px,1fr)_minmax(230px,320px)] items-center gap-5 px-5.5 py-5 [+&]:border-t [+&]:border-border [&_strong]:block [&_strong]:text-[13px] [&_strong]:font-extrabold [&_small]:mt-1 [&_small]:block [&_small]:text-xs [&_small]:leading-normal [&_small]:text-muted-foreground max-[650px]:grid-cols-1 max-[650px]:gap-2.5 max-[650px]:p-4"><span><strong>{t('translationLanguage')}</strong><small>{t('translationLanguageDesc')}</small></span><NativeSelect className="w-full" value={draft.translation_language} onChange={event => setDraft({ ...draft, translation_language: event.target.value })}><option value="vi">Tiếng Việt</option><option value="en">English</option></NativeSelect></label>
      <div className="grid grid-cols-[minmax(200px,1fr)_minmax(230px,320px)] items-center gap-5 px-5.5 py-5 [+&]:border-t [+&]:border-border [&_strong]:block [&_strong]:text-[13px] [&_strong]:font-extrabold [&_small]:mt-1 [&_small]:block [&_small]:text-xs [&_small]:leading-normal [&_small]:text-muted-foreground max-[650px]:grid-cols-1 max-[650px]:gap-2.5 max-[650px]:p-4"><label htmlFor="settings-timezone"><strong>{t('timeZone')}</strong><small>{t('timeZoneDesc')}</small></label><div className="[&_button]:mt-2 [&_button]:block [&_button]:text-xs [&_button]:text-art-blue [&_button]:underline [&_button]:underline-offset-[3px]"><Input id="settings-timezone" list="settings-timezones" value={draft.timezone} aria-invalid={!timezoneValid} onChange={event => setDraft({ ...draft, timezone: event.target.value })} /><datalist id="settings-timezones"><option value="UTC" /><option value="Asia/Ho_Chi_Minh" /><option value="Asia/Tokyo" /><option value="Europe/London" /><option value="America/New_York" /></datalist>{!timezoneValid && <small role="alert">{t('timeZoneError')}</small>}<button type="button" onClick={() => setDraft({ ...draft, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone })}>{t('useDeviceTimeZone')}</button></div></div>
    </section> : <div>
      <section className="mb-3 border border-border" aria-labelledby="questions-heading"><div className="border-b border-border px-5.5 py-4.5 [&_h2]:text-[22px] [&_h2]:font-extrabold [&_h2]:leading-snug [&_h2]:tracking-tight max-md:[&_h2]:text-xl [&_p]:mt-1 [&_p]:text-xs [&_p]:leading-normal [&_p]:text-muted-foreground"><h2 id="questions-heading">{t('questionTypes')}</h2><p>{t('questionTypesDesc')}</p></div><div className="grid grid-cols-3 gap-2 p-3.5 max-[650px]:grid-cols-2 max-[410px]:grid-cols-1">
        {questionItems.map(item => <label key={item.id} className="group relative grid min-h-[108px] cursor-pointer grid-cols-[34px_1fr_18px] grid-rows-2 items-start gap-x-3 border border-border p-4 hover:border-art-blue focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ring data-[selected=true]:bg-[color-mix(in_srgb,var(--art-red)_7%,var(--background))] data-[selected=true]:hover:border-action-red data-[locked=true]:cursor-not-allowed data-[locked=true]:opacity-70 [&_input]:absolute [&_input]:size-px [&_input]:opacity-0 [&_strong]:col-start-2 [&_strong]:text-xs [&_strong]:font-extrabold [&_small]:col-[2/4] [&_small]:mt-1 [&_small]:text-xs [&_small]:leading-normal [&_small]:text-muted-foreground" data-selected={learning.question_types.includes(item.id)}><input type="checkbox" checked={learning.question_types.includes(item.id)} onChange={() => updateLearning({ question_types: toggle(learning.question_types, item.id) })} /><span className="row-[1/3] size-[34px] [&_svg]:block [&_svg]:size-[34px]"><Icon name={item.id} variant="learning" data-learning-icon={item.id} /></span><strong>{item.label}</strong><small>{item.description}</small><Check className="col-start-3 row-start-1 size-[17px] justify-self-end text-action-red opacity-0 group-data-[selected=true]:opacity-100" aria-hidden="true" /></label>)}
      </div></section>
      <section className="mb-3 border border-border" aria-labelledby="formats-heading"><div className="border-b border-border px-5.5 py-4.5 [&_h2]:text-[22px] [&_h2]:font-extrabold [&_h2]:leading-snug [&_h2]:tracking-tight max-md:[&_h2]:text-xl [&_p]:mt-1 [&_p]:text-xs [&_p]:leading-normal [&_p]:text-muted-foreground"><h2 id="formats-heading">{t('answerFormats')}</h2><p>{t('answerFormatsDesc')}</p></div><div className="grid grid-cols-3 gap-2 p-3.5 max-[650px]:grid-cols-2 max-[410px]:grid-cols-1 [&>label]:min-h-[92px]">
        {formatItems.map(format => { const locked = format.id !== 'SINGLE_CHOICE' && !options.advanced_grading; return <label key={format.id} className="group relative grid min-h-[108px] cursor-pointer grid-cols-[34px_1fr_18px] grid-rows-2 items-start gap-x-3 border border-border p-4 hover:border-art-blue focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ring data-[selected=true]:bg-[color-mix(in_srgb,var(--art-red)_7%,var(--background))] data-[selected=true]:hover:border-action-red data-[locked=true]:cursor-not-allowed data-[locked=true]:opacity-70 [&_input]:absolute [&_input]:size-px [&_input]:opacity-0 [&_strong]:col-start-2 [&_strong]:text-xs [&_strong]:font-extrabold [&_small]:col-[2/4] [&_small]:mt-1 [&_small]:text-xs [&_small]:leading-normal [&_small]:text-muted-foreground" data-selected={learning.formats.includes(format.id)} data-locked={locked}><input type="checkbox" checked={learning.formats.includes(format.id)} disabled={locked} onChange={() => updateLearning({ formats: toggle(learning.formats, format.id) as AnswerFormat[] })} /><span className="row-[1/3] size-[34px] [&_svg]:block [&_svg]:size-[34px]"><Icon name={format.id} variant="learning" data-learning-icon={format.id} /></span><strong>{format.label}</strong><small>{format.description}</small>{locked ? <span className="col-start-3 row-start-1 inline-flex justify-self-end gap-1 whitespace-nowrap text-[11px] text-muted-foreground [&_svg]:size-[13px]"><LockKeyhole aria-hidden="true" /> Pro</span> : <Check className="col-start-3 row-start-1 size-[17px] justify-self-end text-action-red opacity-0 group-data-[selected=true]:opacity-100" aria-hidden="true" />}</label> })}
      </div>{!options.advanced_grading && <p className="px-5.5 pb-4.5 text-xs leading-normal text-muted-foreground">{t('freePlanNotice')}</p>}</section>
      <section className="mb-3 border border-border" aria-labelledby="depth-heading"><div className="border-b border-border px-5.5 py-4.5 [&_h2]:text-[22px] [&_h2]:font-extrabold [&_h2]:leading-snug [&_h2]:tracking-tight max-md:[&_h2]:text-xl [&_p]:mt-1 [&_p]:text-xs [&_p]:leading-normal [&_p]:text-muted-foreground"><h2 id="depth-heading">{t('learningDepth')}</h2><p>{t('learningDepthDesc')}</p></div><div className="grid grid-cols-2 max-[650px]:grid-cols-1 [&_label]:grid [&_label]:grid-cols-[1fr_80px] [&_label]:items-center [&_label]:gap-x-3 [&_label]:gap-y-1 [&_label]:p-5.5 [&_label+label]:border-l [&_label+label]:border-border max-[650px]:[&_label+label]:border-l-0 max-[650px]:[&_label+label]:border-t [&_strong]:block [&_strong]:text-[13px] [&_strong]:font-extrabold [&_small]:col-start-1 [&_small]:mt-1 [&_small]:block [&_small]:text-xs [&_small]:leading-normal [&_small]:text-muted-foreground">
        <label><strong>{t('questionsPerSense')}</strong><small>{t('questionsPerSenseDesc')}</small><Input type="number" className="col-start-2 row-[1/3] text-center" min={options.limits.min_questions_per_sense} max={options.limits.max_questions_per_sense} value={learning.questions_per_sense} onChange={event => updateLearning({ questions_per_sense: Number(event.target.value) })} /></label>
        <label><strong>{t('maxSenses')}</strong><small>{t('maxSensesDesc')}</small><Input type="number" className="col-start-2 row-[1/3] text-center" min="1" max={Math.min(20, Math.floor(options.limits.max_questions_per_prepare / Math.max(1, learning.questions_per_sense)))} value={learning.max_sense_count} onChange={event => updateLearning({ max_sense_count: Number(event.target.value) })} /></label>
      </div><p className="px-5.5 pb-4.5 text-xs leading-normal text-muted-foreground">{t('depthSummary', { max: learning.questions_per_sense * learning.max_sense_count, limit: options.limits.max_questions_per_prepare })}</p></section>
      {profile.learning_restriction && <p className="border border-action-red px-4 py-3 text-[13px] text-foreground" role="status">{t('restrictionNotice')}</p>}
      {!valid && <p className="border border-action-red px-4 py-3 text-[13px] text-foreground" role="status">{t('invalidSettingsNotice')}</p>}
    </div>}
  </div>
}
