import { getTranslations } from 'next-intl/server'
import { Icon } from '@/components/artwork/artwork'

export async function LandingPrinciples() {
  const tLanding = await getTranslations('landing')

  return (
    <section className="grid grid-cols-2 gap-[8%] px-[4%] py-[104px] max-md:grid-cols-1 max-md:gap-10 max-md:px-[6%] max-md:py-14" aria-labelledby="principles-title">
      <div className="[&_h2]:text-[clamp(36px,3.8vw,56px)] [&_h2]:font-extrabold [&_h2]:leading-[1.13] [&_h2]:tracking-[-.035em] [&_h2_span]:text-action-red dark:[&_h2_span]:text-art-yellow [&_>_p]:mt-[25px] [&_>_p]:text-sm [&_>_p]:leading-[1.7] max-md:[&_h2]:text-[40px] max-md:[&_>_p]:mt-4">
        <h2 id="principles-title">
          {tLanding('principlesTitle1')}
          <br />
          {tLanding('principlesTitle2')}
          <br />
          <span>{tLanding('principlesTitle3')}</span>
        </h2>
        <p>{tLanding('principlesSubtitle')}</p>
      </div>
      <div className="[&_article]:flex [&_article]:gap-6 [&_article]:border-t [&_article]:border-foreground [&_article]:py-[25px] [&_article:first-child]:border-t-0 [&_article:first-child]:pt-0 [&_svg]:size-[42px] [&_svg]:shrink-0 [&_h3]:text-[19px] [&_h3]:font-[750] [&_h3]:leading-[1.4] [&_h3]:tracking-[-.015em] [&_p]:mt-[9px] [&_p]:max-w-[50ch] [&_p]:text-[13px] [&_p]:leading-[1.85] [&_p]:text-muted-foreground max-md:[&_article]:gap-[18px] max-md:[&_h3]:text-[17px]">
        <article>
          <Icon name="dictionary" />
          <div>
            <h3>{tLanding('principle1Title')}</h3>
            <p>{tLanding('principle1Desc')}</p>
          </div>
        </article>
        <article>
          <Icon name="review" />
          <div>
            <h3>{tLanding('principle2Title')}</h3>
            <p>{tLanding('principle2Desc')}</p>
          </div>
        </article>
        <article>
          <Icon name="robot" />
          <div>
            <h3>{tLanding('principle3Title')}</h3>
            <p>{tLanding('principle3Desc')}</p>
          </div>
        </article>
      </div>
    </section>
  )
}
