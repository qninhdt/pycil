import Link from 'next/link'
import { ArrowUpRight } from '@/components/artwork/artwork'
import { Motif, type MotifName } from '@/components/artwork/artwork'

const content = {
  home: { title: 'Home', description: 'A place to return to your learning.', motif: 'balance', detail: 'Your Library summary, activity and upcoming reviews will live here.' },
  dictionary: { title: 'Dictionary', description: 'Find the meaning you want to learn.', motif: 'orbit', detail: 'Search for words and explore their separate meanings here.' },
  library: { title: 'My Library', description: 'Your words. Your way of organizing them.', motif: 'modular', detail: 'Personal and Published material, folders, decks and references will live here.' },
  discovery: { title: 'Discovery', description: 'A new perspective on what to learn.', motif: 'interlock', detail: 'Explore published material without changing your own Library.' },
  profile: { title: 'Profile', description: 'Your public introduction.', motif: 'counterform', detail: 'Your public identity and Published Library will live here. Private learning information stays private.' },
  settings: { title: 'Settings', description: 'Make learning work for you.', motif: 'axis', detail: 'Account and learning preferences will live here.' },
} satisfies Record<string, { title: string; description: string; motif: MotifName; detail: string }>

export function Placeholder({ page, create }: { page: keyof typeof content; create?: string }) {
  const item = content[page]
  const action = create === 'deck' ? 'Deck creation' : create === 'folder' ? 'Folder creation' : null
  return <div className="w-full">
    <header className="grid grid-cols-[minmax(0,1.3fr)_1fr_1fr_1fr] max-[767px]:grid-cols-1 items-stretch min-h-[124px] max-[767px]:min-h-0 max-[767px]:py-4 border-b border-border [&_h1]:leading-[1.12]"><div className="col-span-3 max-[767px]:col-span-1 min-w-0 flex flex-col justify-center py-4 pr-6 max-[767px]:p-0"><h1 className="text-[clamp(2.25rem,2.6vw,3rem)] font-extrabold leading-[1.12] tracking-[-.03em] max-[700px]:text-[34px] text-balance">{item.title}<span className="text-art-red" aria-hidden="true">.</span></h1><p className="mt-1.5 text-sm leading-[1.6] text-muted-foreground max-md:text-xs">{item.description}</p></div><div className="header-motif-art col-span-1 max-[767px]:hidden" aria-hidden="true"><Motif name={item.motif} /></div></header>
    <section className="max-w-[620px] pb-16 pt-[72px] max-md:py-12" aria-label="Page implementation status">
      <div className="mb-8 flex gap-[5px]" aria-hidden="true"><span className="h-[5px] w-8 bg-art-red" /><span className="h-[5px] w-8 bg-art-blue" /><span className="h-[5px] w-8 bg-art-yellow" /></div>
      <h2 className="text-[28px] font-bold leading-[1.2] tracking-[-.025em] max-md:text-[25px]">{action ? `${action} comes next.` : 'The foundation is in place.'}</h2>
      <p className="mt-4 max-w-[50ch] text-sm leading-[1.8] text-muted-foreground">{action ? 'This is a placeholder. Nothing has been created or saved.' : 'This page is a placeholder, not an empty account.'} {item.detail}</p>
      <Link href="/showcase" className="mt-8 inline-flex min-h-11 items-center gap-2.5 text-[13px] font-semibold underline underline-offset-[6px] [&_svg]:size-4">Explore the design workshop <ArrowUpRight aria-hidden="true" /></Link>
    </section>
  </div>
}
