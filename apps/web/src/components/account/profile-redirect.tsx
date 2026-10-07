'use client'
import { useEffect } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useAccount } from '@/components/application/providers'
import { Button } from '@/components/ui/button'

export function ProfileRedirect() {
  const account = useAccount(), router = useRouter()
  useEffect(() => { if (account.profile) router.replace(`/u/${encodeURIComponent(account.profile.id)}`) }, [account.profile, router])
  return <div className="w-full py-8 [&_h1]:text-[clamp(2.25rem,2.6vw,3rem)] [&_h1]:font-extrabold [&_h1]:leading-[1.12] [&_h1]:tracking-[-.03em] [&_p]:mt-3 [&_p]:mb-5.5 [&_p]:text-muted-foreground"><h1>Profile</h1>{account.status === 'signed-out' ? <p>Sign in to view your profile. <Link href="/login" className="underline underline-offset-4">Sign in</Link></p>
    : account.status === 'error' ? <><p>{account.error || 'Could not load your account.'}</p><Button variant="outline" onClick={account.retry}>Retry</Button></>
      : account.status === 'task' ? <p>Complete <Link href="/auth/continue" className="underline underline-offset-4">account verification</Link> to open your profile.</p>
        : <p>Opening your public profile…</p>}</div>
}
