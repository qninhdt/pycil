'use client'

import Link from 'next/link'
import { ArrowRight, X } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'
import type { SessionSelection } from '@/lib/home-api'

export function HomeSession({ nodeId, selection, close }: { nodeId: string; selection: SessionSelection; close: () => void }) {
  return <section className="border-y border-border py-4 mb-5 [&_>div:first-child]:mb-3 [&_p]:text-xs [&_p]:text-muted-foreground [&_p]:leading-relaxed [&_p]:mb-4 [&_p[role=alert]]:text-destructive" aria-label="Start learning session">
    <div className="flex items-center justify-between gap-4 mb-6 [&_h2]:text-[22px] [&_h2]:leading-snug [&_h3]:text-lg [&_h3]:leading-snug [&_p]:text-muted-foreground [&_p]:text-[13px] [&_p]:mt-1.5 max-md:[&_h2]:text-xl"><h3>{selection === 'DUE' ? 'Review due meanings' : selection === 'NEW' ? 'Learn new meanings' : 'Practice your Library'}</h3>
      <Button variant="ghost" size="icon" onClick={close} aria-label="Close session preparation"><X aria-hidden="true" /></Button></div>
    <p>Your questions will be prepared from your learning settings. Progress is saved on this device.</p>
    <Button asChild><Link href={`/focus/learn?node=${encodeURIComponent(nodeId)}&selection=${selection}`}>Start session <ArrowRight data-icon="inline-end" aria-hidden="true" /></Link></Button>
  </section>
}
