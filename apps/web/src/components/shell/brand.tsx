import Link from 'next/link'
import { cn } from '@/lib/utils'

export function MarkPaths() {
  return <>
    <path d="M0 93L188 2V49L48 117V268L0 291Z" fill="var(--art-yellow)" />
    <path d="M62 128L250 37V84L110 152V303L62 326Z" fill="var(--art-blue)" />
    <polygon points="124,163 312,72 312,270 124,361" fill="var(--art-red)" />
  </>
}

export function PycilMark() {
  return <svg className="block h-8 w-7 flex-none" viewBox="0 0 312 362" aria-hidden="true"><MarkPaths /></svg>
}

export function PycilBrand({ compact = false, markOnly = false, className }: { compact?: boolean; markOnly?: boolean; className?: string }) {
  return <Link href="/app" className={cn('pycil-brand relative inline-flex items-center text-foreground no-underline', compact && 'z-1 h-9 w-[86px] min-w-8', markOnly && 'w-8 overflow-hidden', className)} aria-label="Pycil home">
    <svg className={cn('pycil-logo pycil-logo-full block shrink-0', compact ? 'absolute left-[2.21px] top-0.5 h-8 w-[82.74px]' : 'h-auto w-24 md:w-28')} viewBox="0 0 936 362" aria-hidden="true">
      <MarkPaths />
      <g className={`pycil-wordmark transition-[opacity,visibility] duration-200 motion-reduce:transition-none ${markOnly ? 'invisible opacity-0' : ''}`} transform="translate(392 80)" fill="currentColor">
        <path fillRule="evenodd" d="M0 14H84C125 14 156 44 156 85C156 126 126 158 84 158H48V216H0ZM48 58V114H84C101 114 109 102 109 86C109 70 101 58 84 58Z" />
        <path d="M156 75H193L226 157L259 75H310L214 276H166L202 202Z" />
        <path d="M427 115L397 130C391 120 381 115 369 115C352 115 338 129 338 147C338 166 351 181 369 181C381 181 391 176 397 167L427 181C417 206 395 220 369 220C326 220 294 188 294 147C294 106 326 73 369 73C395 73 417 88 427 115Z" />
        <path d="M436 75H483V216H436Z" />
        <path d="M497 10H544V216H497Z" />
        <path className="pycil-i-dot" d="M483 32A27 27 0 1 1 429 32A27 27 0 1 1 483 32Z" fill="var(--art-red)" />
      </g>
    </svg>
  </Link>
}
