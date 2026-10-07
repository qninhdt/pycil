'use client'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
export default function ErrorPage({ reset }: { reset: () => void }) {
  return <div className="px-8 py-16 flex flex-col gap-5 max-w-[680px] mx-auto [&_h1]:text-[32px] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_a]:underline [&_a]:underline-offset-4" role="alert"><h1>This page could not be opened.</h1><p>Please retry. Your saved learning material has not been changed.</p><Button onClick={reset}>Retry</Button><Link href="/app">Return to Home</Link></div>
}
