import Link from 'next/link'
import { Motif } from '@/components/artwork/artwork'
export default function NotFound() {
  return <main className="flex flex-col items-center text-center gap-6 px-6 py-20 min-h-svh justify-center [&_>_div]:w-[200px] [&_>_div]:h-[150px] [&_h1]:text-[40px] [&_h1]:leading-[1.1] [&_h1]:tracking-tight [&_h1]:font-extrabold [&_p]:text-sm [&_p]:text-muted-foreground [&_a]:underline [&_a]:underline-offset-4"><div><Motif name="orbit" /></div><h1>This page isn’t here.</h1><p>The address may have changed. Your workspace is still here.</p><Link href="/app">Return to Home</Link></main>
}
