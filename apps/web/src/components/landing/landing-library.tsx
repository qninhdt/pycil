import Link from 'next/link'
import { getTranslations } from 'next-intl/server'
import { ArrowUpRight, Icon } from '@/components/artwork/artwork'

export async function LandingLibrary() {
  const tLanding = await getTranslations('landing')
  const tHome = await getTranslations('home')

  return (
    <section id="library" className="mt-[88px] grid grid-cols-2 border-y border-foreground max-md:mt-14 max-md:grid-cols-1" aria-labelledby="library-title">
      <div className="relative min-h-[600px] overflow-hidden border-r border-foreground bg-art-blue px-[8%] py-13 text-[var(--palette-ink)] [&_h2]:relative [&_h2]:z-1 [&_h2]:text-[clamp(40px,4.3vw,64px)] [&_h2]:font-extrabold [&_h2]:leading-[1.06] [&_h2]:tracking-[-.035em] max-[1100px]:min-h-[660px] max-md:min-h-[480px] max-md:border-r-0 max-md:border-b max-md:px-[6%] max-md:py-9 max-md:[&_h2]:text-[42px]">
        <h2 id="library-title" className="whitespace-pre-line">{tLanding('libraryHeading')}</h2>
        <svg className="absolute right-0 bottom-0 max-h-[310px] w-[86%] max-md:max-h-[250px] max-md:w-[82%]" viewBox="0 0 480 350" aria-hidden="true">
          <path d="M0 318H480M88 0V350" stroke="var(--palette-ink)" fill="none" />
          <path d="M88 318V136H270V318Z" fill="var(--palette-canvas)" />
          <path d="M88 136V46H270V136Z" fill="var(--art-yellow)" />
          <path d="M270 136H452V318H270Z" fill="var(--palette-ink)" />
          <circle cx="361" cy="227" r="91" fill="var(--art-red)" />
          <path d="M88 136H270L88 318Z" fill="var(--palette-primary-blue)" />
          <path d="M270 46V318M0 136H480" stroke="var(--palette-ink)" fill="none" />
        </svg>
      </div>
      <div className="px-[10%] py-13 [&_>_p]:max-w-[50ch] [&_>_p]:text-sm [&_>_p]:leading-[1.85] max-[1100px]:px-[8%] max-md:px-[6%] max-md:py-9">
        <p className="!mb-[22px] !text-[26px] !font-[750] !leading-[1.45] !tracking-[-.02em] max-md:!text-[25px] whitespace-pre-line">{tLanding('libraryDesc1')}</p>
        <p>{tLanding('libraryDesc2')}</p>
        <div className="my-8 border-y border-foreground [&_>_div]:flex [&_>_div]:min-h-[62px] [&_>_div]:items-center [&_>_div]:gap-4 [&_>_div]:border-b [&_>_div]:border-border [&_>_div:last-child]:border-b-0 [&_svg]:size-[30px] [&_strong]:text-sm [&_strong]:font-bold [&_span:last-child]:ml-auto [&_span:last-child]:text-[11px] [&_span:last-child]:text-muted-foreground max-md:my-6" aria-label={tLanding('exampleLibrary')}>
          <div className="!min-h-[39px] text-[11px]"><span>{tLanding('exampleLibrary')}</span><span>{tHome('personal')}</span></div>
          <div><Icon name="folder" /><strong>{tLanding('folderReading')}</strong><span>{tLanding('folder')}</span></div>
          <div><Icon name="collection" /><strong>{tLanding('deckWork')}</strong><span>{tLanding('deck')}</span></div>
          <div><Icon name="collection" /><strong>{tLanding('deckPlaces')}</strong><span>{tLanding('deck')}</span></div>
        </div>
        <p>{tLanding('libraryPrivacy')}</p>
        <Link className="inline-flex min-h-11 items-center justify-between gap-3.5 text-[13px] font-bold underline-offset-4 hover:underline [&_svg]:size-[18px]" href="/app/discovery">{tLanding('explorePublishedDecks')} <ArrowUpRight /></Link>
      </div>
    </section>
  )
}
