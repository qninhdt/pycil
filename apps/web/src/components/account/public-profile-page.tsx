'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarDays, Check, Pencil, Share2 } from '@/components/artwork/artwork'
import { toast } from 'sonner'
import { Shape } from '@/components/artwork/artwork'
import { useAccount } from '@/components/application/providers'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useServices } from '@/lib/services/provider'
import { HomeApiError } from '@/lib/home-api'
import { LibraryFolder } from '@/components/library/library-folder'
import { useTranslations, useLocale } from 'next-intl'

export function PublicProfilePage({ identifier, publishedBase }: { identifier: string; nodeId?: string; publishedBase?: string }) {
  const { services, scope } = useServices(), account = useAccount(), queryClient = useQueryClient(), router = useRouter()
  const t = useTranslations('account')
  const tCommon = useTranslations('common')
  const locale = useLocale()
  const query = useQuery({ queryKey: [services.mode, scope, 'public-profile', identifier], queryFn: ({ signal }) => services.account.publicProfile(identifier, signal) })
  const [displayName, setDisplayName] = useState('')
  const [editing, setEditing] = useState(false), [handle, setHandle] = useState(''), [bio, setBio] = useState(''), [saving, setSaving] = useState(false)
  const profile = query.data, own = !!profile && account.profile?.id === profile.id

  async function share() {
    if (!profile) return
    const url = `${location.origin}/u/${encodeURIComponent(profile.handle || profile.id)}`
    try { await navigator.clipboard.writeText(url); toast.success(t('profileLinkCopied')) }
    catch { toast.error(t('couldNotCopyProfileLink')) }
  }

  async function save() {
    if (!profile) return
    setSaving(true)
    try {
      const patch: Parameters<typeof services.account.updateProfile>[0] = {}
      if (displayName.trim() !== profile.display_name) patch.display_name = displayName.trim()
      if (handle.trim().toLowerCase() !== profile.handle) patch.handle = handle.trim().toLowerCase()
      if ((bio.trim() || null) !== profile.bio) patch.bio = bio.trim() || null
      const next = await services.account.updateProfile(patch, new AbortController().signal)
      queryClient.setQueryData([services.mode, scope, 'account'], next)
      await queryClient.invalidateQueries({ queryKey: [services.mode, scope, 'public-profile'] })
      setEditing(false)
      if (next.handle !== profile.handle) router.replace(`/u/${encodeURIComponent(next.handle || next.id)}`)
      toast.success(t('profileUpdated'))
    } catch (error) { toast.error(error instanceof HomeApiError && error.code === 'handle_unavailable' ? t('handleUnavailable') : t('couldNotSaveProfile')) }
    finally { setSaving(false) }
  }

  if (query.isPending) return <div className="w-full py-6 text-muted-foreground" role="status">{t('loadingProfile')}</div>
  if (query.isError || !profile) return <div className="w-full py-6 text-muted-foreground" role="alert"><h1 className="text-2xl font-extrabold tracking-tight">{t('profileUnavailable')}</h1><p className="mt-2 mb-4">{t('profileNotFound')}</p><Button variant="outline" onClick={() => { void query.refetch() }}>{t('tryAgain')}</Button></div>

  return (
    <div className="w-full">
      <header className="relative grid min-h-[204px] grid-cols-[160px_minmax(0,1fr)_auto] gap-7 overflow-hidden border border-border max-[850px]:grid-cols-[130px_1fr] max-[850px]:gap-5 max-[650px]:grid-cols-[90px_1fr] max-[650px]:gap-3.5">
        <div className="flex flex-wrap content-center justify-center border-r border-border [&_svg]:size-16 [&_svg:first-child]:size-32 max-[850px]:[&_svg]:size-[50px] max-[850px]:[&_svg:first-child]:size-[100px] max-[650px]:[&_svg]:size-[38px] max-[650px]:[&_svg:first-child]:size-[76px]" aria-hidden="true">
          <Shape name="circle" />
          <Shape name="square" />
          <Shape name="triangle" />
        </div>
        <div className="z-1 self-center py-6 max-[650px]:py-5 max-[650px]:pr-3 max-[650px]:pb-2 [&_h1]:leading-[1.12] [&_h1]:font-extrabold [&_h1]:tracking-[-.03em]">
          <h1 className="text-[clamp(2.25rem,2.6vw,3rem)] font-extrabold leading-[1.12] tracking-[-.03em] max-[700px]:text-[34px]">
            {profile.display_name || profile.handle || t('pycilLearner')}<span className="text-art-red" aria-hidden="true">.</span>
          </h1>
          {profile.handle && <p className="mt-1 text-xl">@{profile.handle}</p>}
          <p className="my-3 max-w-[60ch] text-muted-foreground">{profile.bio || (own ? t('addBioPrompt') : t('noBioYet'))}</p>
          <p className="mt-4.5 flex items-center gap-1.5 text-xs [&_svg]:size-4">
            <CalendarDays aria-hidden="true" /> {t('joinedDate', { date: new Intl.DateTimeFormat(locale, { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(profile.joined_at)) })}
          </p>
        </div>
        <div className="z-1 flex self-start gap-2 p-5.5 [&_svg]:size-4 max-[850px]:col-start-2 max-[850px]:p-0 max-[850px]:pb-5 max-[650px]:col-[1/3] max-[650px]:px-3.5 max-[650px]:pb-4.5 max-[410px]:flex-wrap">
          {own && (
            <Button
              variant="outline"
              onClick={() => {
                setDisplayName(profile.display_name || '')
                setHandle(profile.handle || '')
                setBio(profile.bio || '')
                setEditing(true)
              }}
            >
              <Pencil aria-hidden="true" /> {t('editProfile')}
            </Button>
          )}
          <Button variant="outline" onClick={share}><Share2 aria-hidden="true" /> {t('shareProfile')}</Button>
        </div>
        <div className="pointer-events-none absolute -right-9 -bottom-12 flex opacity-85 [&_svg]:size-[100px] [&_svg+svg]:-ml-9.5 [&_svg+svg]:translate-y-[30px] max-[850px]:opacity-35" aria-hidden="true">
          <Shape name="circle" />
          <Shape name="square" />
        </div>
      </header>

      <Dialog open={editing} onOpenChange={setEditing}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('editPublicProfile')}</DialogTitle>
            <DialogDescription>{t('profileVisibilityDesc')}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="grid gap-1.5">
              <label className="text-xs font-bold" htmlFor="profile-display-name">
                {t('displayName')}
              </label>
              <Input
                id="profile-display-name"
                value={displayName}
                required
                maxLength={255}
                autoComplete="name"
                disabled={saving}
                onChange={event => setDisplayName(event.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <label className="text-xs font-bold" htmlFor="profile-handle">
                {t('handle')}
              </label>
              <Input
                id="profile-handle"
                value={handle}
                disabled={saving}
                maxLength={30}
                onChange={event => setHandle(event.target.value)}
                aria-describedby="profile-handle-help"
              />
              <small id="profile-handle-help" className="text-xs text-muted-foreground">
                {t('handleHelp')}
              </small>
            </div>
            <div className="grid gap-1.5">
              <label className="text-xs font-bold" htmlFor="profile-bio">
                {t('bio')}
              </label>
              <Textarea
                id="profile-bio"
                value={bio}
                disabled={saving}
                maxLength={500}
                rows={3}
                onChange={event => setBio(event.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" disabled={saving} onClick={() => setEditing(false)}>
              {tCommon('cancel')}
            </Button>
            <Button
              disabled={saving || !displayName.trim() || displayName.trim().length > 255 || !/^[a-z][a-z0-9_]{2,29}$/.test(handle.trim().toLowerCase())}
              onClick={save}
            >
              {saving ? tCommon('saving') : <><Check aria-hidden="true" /> {t('saveProfile')}</>}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <section className="mt-8" aria-labelledby="profile-published-title">
        <div className="border-b border-border pb-4 mb-5">
          <h2 id="profile-published-title" className="text-[22px] font-extrabold tracking-tight">
            {t('publishedCollections')}
          </h2>
        </div>
        <LibraryFolder
          nodeId={profile.published_node_id}
          name={profile.display_name || profile.handle || t('publishedCollections')}
          space="PUBLISHED"
          canCreate={own}
        />
      </section>
    </div>
  )
}
