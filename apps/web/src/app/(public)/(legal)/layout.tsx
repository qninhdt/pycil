import Link from 'next/link'

export default function LegalLayout({ children }: { children: React.ReactNode }) {
  return <div className="min-h-svh bg-background text-foreground">
    <header className="mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-6 border-b px-6 py-6">
      <Link href="/" className="text-xl font-extrabold tracking-tight">Pycil</Link>
      <nav aria-label="Legal pages" className="flex gap-6 text-sm underline-offset-4 [&_a:hover]:underline">
        <Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link>
      </nav>
    </header>
    <main className="mx-auto max-w-3xl px-6 py-12 leading-7 [&_h1]:mb-4 [&_h1]:text-4xl [&_h1]:font-extrabold [&_h1]:tracking-tight [&_h2]:mb-3 [&_h2]:mt-10 [&_h2]:text-xl [&_h2]:font-bold [&_p]:mb-4 [&_ul]:mb-4 [&_ul]:list-disc [&_ul]:space-y-2 [&_ul]:pl-6 [&_a]:underline [&_a]:underline-offset-4">{children}</main>
  </div>
}
