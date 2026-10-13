'use client'

import { useEffect, useState, type CSSProperties } from 'react'
import { ArrowRight, ArrowUpRight, Moon, Search, Sun } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
import { Kbd } from '@/components/ui/kbd'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useTheme } from '@/lib/preferences/theme-provider.client'
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent,
  SidebarGroupLabel, SidebarHeader, SidebarMenu, SidebarMenuButton,
  SidebarMenuItem, SidebarProvider, SidebarTrigger, useSidebar,
} from '@/components/ui/sidebar'
import {
  CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from '@/components/ui/command'
import {
  Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyTitle,
} from '@/components/ui/empty'
import {
  Background, BrandMark, Motif, Icon, iconNames, compactIconNames, learningIconNames, motifNames, backgroundNames, displayName,
} from '@/components/artwork/artwork'
import { ArtGallery, Foundations } from '@/app/(public)/showcase/examples/art-gallery'
import { componentDemos, compositionDemos } from '@/app/(public)/showcase/examples/component-demos'
import { SectionIntro, Specimen } from '@/app/(public)/showcase/examples/specimen'
import IconGallery from '@/app/(public)/showcase/examples/icon-gallery'
import { AssistantShowcase } from '@/features/assistant/showcase.client'

type View = 'components' | 'artwork' | 'icons' | 'foundations' | 'compositions' | 'assistant'
const views: View[] = ['components', 'artwork', 'icons', 'foundations', 'compositions', 'assistant']
const artworkNames = [...motifNames, ...backgroundNames]
const counts = {
  components: componentDemos.length,
  artwork: artworkNames.length,
  icons: iconNames.length + compactIconNames.length + learningIconNames.length,
  foundations: 3,
  compositions: compositionDemos.length,
  assistant: 1,
}
const specimenId = (title: string) => title.toLowerCase().replaceAll(/[^a-z0-9]+/g, '-')

function CatalogSidebar({ view, navigate }: {
  view: View
  navigate: (view: View, anchor?: string) => void
}) {
  const { setOpenMobile } = useSidebar()
  const go = (target: View, anchor?: string) => {
    navigate(target, anchor)
    setOpenMobile(false)
  }
  const index = view === 'compositions' ? compositionDemos : componentDemos

  return (
    <Sidebar>
      <SidebarHeader className="px-5 pt-6">
        <p className="text-sm font-bold">The design workshop.</p>
        <p className="text-[11px] leading-relaxed text-muted-foreground">A practical system with an artistic point of view.</p>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Explore the system</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {views.map(v => (
                <SidebarMenuItem key={v}>
                  <SidebarMenuButton isActive={view === v} onClick={() => go(v)}>
                    <span className="size-[9px] border border-current mr-0.5" />{displayName(v)}
                    <span className="ml-auto tabular-nums text-[11px]">{String(counts[v]).padStart(2, '0')}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        {view !== 'foundations' && view !== 'icons' && view !== 'assistant' && (
          <SidebarGroup>
            <SidebarGroupLabel>{view === 'artwork' ? 'Artwork collection' : 'Specimen index'}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {view === 'artwork' ? ['motifs', 'backgrounds'].map(name => (
                  <SidebarMenuItem key={name}>
                    <SidebarMenuButton onClick={() => go('artwork', name)}>{displayName(name)}</SidebarMenuButton>
                  </SidebarMenuItem>
                )) : index.map(demo => (
                  <SidebarMenuItem key={demo.title}>
                    <SidebarMenuButton onClick={() => go(view, specimenId(demo.title))}>{demo.title}</SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}
      </SidebarContent>
      <SidebarFooter>
        <div className="h-[100px] my-3.5"><Motif name="modular" /></div>
        <p className="text-[11px] leading-relaxed text-muted-foreground">Authored geometry.<br />Accessible primitives.<br />No random decisions.</p>
      </SidebarFooter>
    </Sidebar>
  )
}

function Showcase() {
  const [view, setView] = useState<View>(() => new URLSearchParams(window.location.search).get('view') === 'assistant' ? 'assistant' : 'components')
  const [query, setQuery] = useState('')
  const [commandOpen, setCommandOpen] = useState(false)
  const { theme, toggleTheme } = useTheme()
  const navigate = (target: View, anchor?: string) => {
    setView(target)
    setQuery('')
    window.requestAnimationFrame(() => {
      document.getElementById(anchor || 'catalog')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  useEffect(() => {
    // Reuse the rendered mark and canonical CSS palette; no second icon palette.
    const mark = document.querySelector('[data-brand-mark]')?.cloneNode(true) as SVGElement | undefined
    const icon = document.getElementById('app-icon') as HTMLLinkElement | null
    if (mark && icon) {
      mark.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
      const palette = getComputedStyle(document.documentElement)
      mark.querySelectorAll('[fill]').forEach(shape => {
        const fill = shape.getAttribute('fill') || ''
        const token = fill.match(/^var\((--[\w-]+)\)$/)?.[1]
        if (token) shape.setAttribute('fill', palette.getPropertyValue(token).trim())
      })
      icon.href = `data:image/svg+xml,${encodeURIComponent(mark.outerHTML)}`
    }
    const handler = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === 'k' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        setCommandOpen(open => !open)
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  const demoList = view === 'compositions' ? compositionDemos : componentDemos
  const filtered = demoList.filter(demo =>
    `${demo.title} ${demo.components}`.toLowerCase().includes(query.toLowerCase()))
  const noResults = view === 'artwork'
    ? !artworkNames.some(name => displayName(name).toLowerCase().includes(query.toLowerCase()))
    : view !== 'foundations' && view !== 'icons' && view !== 'assistant' && !filtered.length

  return (
    <TooltipProvider>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <SidebarProvider className="showcase-shell flex-col" style={{ '--sidebar-width': '240px' } as CSSProperties}>
        <header className="h-[72px] sticky top-0 z-40 flex items-center gap-[30px] px-[30px] border-b border-border bg-background max-[1100px]:gap-5.5 max-[1100px]:px-5.5 max-md:h-16 max-md:px-4 max-md:gap-3">
          <SidebarTrigger className="hidden max-md:inline-flex" />
          <a className="inline-flex items-center gap-2.5 text-[22px] font-extrabold tracking-[-.04em] no-underline text-inherit [&_small]:text-[11px] [&_small]:font-medium [&_small]:tracking-normal [&_small]:text-muted-foreground [&_small]:ml-1 max-[1100px]:[&_small]:hidden max-md:text-xl" href="#" onClick={event => {
            event.preventDefault()
            setView('components')
            setQuery('')
            window.scrollTo({ top: 0, behavior: 'smooth' })
          }}>
            <BrandMark />bauhaus<span aria-hidden="true">.</span><small>form & function</small>
          </a>
          <nav className="flex items-center gap-6 text-[13px] [&_button]:bg-transparent [&_button]:border-0 [&_button]:py-6 [&_button]:text-muted-foreground [&_button[aria-pressed=true]]:text-foreground max-md:hidden" aria-label="Main navigation">
            {views.slice(0, 3).map(v => (
              <button key={v} aria-pressed={view === v} onClick={() => navigate(v)}>{displayName(v)}</button>
            ))}
          </nav>
          <div className="flex gap-2 items-center ml-auto">
            <Button variant="outline" className="min-w-[190px] justify-between text-muted-foreground max-md:inline-flex max-md:min-w-0 max-md:w-10 max-md:p-0 max-md:justify-center max-md:[&_.search-text]:hidden max-md:[&_[data-slot=kbd]]:hidden" aria-label="Find a component or collection" onClick={() => setCommandOpen(true)}>
              <span className="flex items-center gap-2"><Search /><span className="search-text">Find something</span></span>
              <Kbd>⌘ K</Kbd>
            </Button>
            <Button variant="ghost" size="icon" aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
              onClick={toggleTheme}>
              {theme === 'dark' ? <Sun /> : <Moon />}
            </Button>
          </div>
        </header>
        <div className="flex min-h-0 flex-1">
          <CatalogSidebar view={view} navigate={navigate} />
          <main id="main-content" className="flex-1 min-w-0 px-11 pt-9 min-[1600px]:pt-[45px] max-[1100px]:p-7 max-md:px-4.5 max-md:pt-6" tabIndex={-1}>
            <div className="max-w-[1220px] mx-auto">
              <section className="grid grid-cols-[1.25fr_1fr] border-b border-border min-h-[320px] mb-7 [&_h1]:text-[clamp(44px,5vw,78px)] [&_h1]:font-extrabold [&_h1]:tracking-[-.04em] [&_h1]:leading-[1.03] [&_h1]:mb-5.5 [&_h1]:text-balance [&_h1_span]:inline-block [&_h1_span]:text-[var(--palette-red-dark)] [&_p]:max-w-[410px] [&_p]:text-muted-foreground [&_p]:text-sm [&_p]:leading-loose [&_p]:mb-6 min-[1600px]:min-h-[365px] max-[1100px]:[&_h1]:text-[54px] max-md:grid-cols-1 max-md:min-h-0 max-md:[&_h1]:text-[54px] max-md:[&_h1]:max-w-[320px] max-md:[&_p]:text-[13px]" aria-label="Introducing the theme">
                <div className="pt-2.5 pr-6 pb-8 max-md:p-0 max-md:pb-6">
                  <h1>Good form.<br />Great <span className="dark:text-foreground">function.</span></h1>
                  <p>A little art. A lot of intention. A Bauhaus-inspired workshop of components and geometry, made for interfaces that have something to say.</p>
                  <div className="flex flex-wrap items-center gap-2.5">
                    <Button onClick={() => navigate('components')}>Explore components <ArrowRight data-icon="inline-end" /></Button>
                    <Button variant="outline" onClick={() => navigate('artwork')}>Meet the artwork <ArrowUpRight data-icon="inline-end" /></Button>
                  </div>
                </div>
                <div className="relative border-l border-border mb-7.5 overflow-hidden [&_.bauhaus-background]:absolute [&_.bauhaus-background]:inset-0 max-md:h-[185px] max-md:border-l-0 max-md:border-t max-md:border-border max-md:mb-5">
                  <Background name="primary-poster" />
                  <span className="absolute bottom-3.5 left-5 text-[11px] font-semibold">Circle. Square. Possibility.</span>
                </div>
              </section>
              <div className="flex gap-6 items-center justify-between border-b border-border pb-3 [&_[data-slot=input-group]]:w-[230px] max-md:items-stretch max-md:gap-3.5 max-md:flex-col max-md:[&_[data-slot=input-group]]:w-full" id="catalog">
                <nav className="flex gap-2 flex-wrap [&_button]:text-[13px] max-md:gap-1 max-md:[&_button]:px-2.5" aria-label="Catalog categories">
                  {views.map(v => (
                    <Button key={v} variant={view === v ? 'default' : 'ghost'} size="sm"
                      aria-pressed={view === v} onClick={() => navigate(v)}>{displayName(v)}</Button>
                  ))}
                </nav>
                {view !== 'foundations' && (
                  <InputGroup>
                    <InputGroupAddon><Search /></InputGroupAddon>
                    <InputGroupInput aria-label="Filter catalog" placeholder={view === 'icons' ? 'Find any icon…' : view === 'artwork' ? 'Find artwork…' : 'Find a component…'}
                      value={query} onChange={event => setQuery(event.target.value)} />
                  </InputGroup>
                )}
              </div>
              {noResults ? (
                <Empty className="my-10">
                  <EmptyHeader>
                    <Icon name="search" />
                    <EmptyTitle>No matches for “{query}”</EmptyTitle>
                    <EmptyDescription>Try a component name, such as Button, or an artwork name, such as Orbit.</EmptyDescription>
                  </EmptyHeader>
                  <EmptyContent><Button variant="outline" onClick={() => setQuery('')}>Clear search</Button></EmptyContent>
                </Empty>
              ) : view === 'icons' ? <IconGallery query={query} />
                : view === 'artwork' ? <ArtGallery query={query} />
                : view === 'foundations' ? <Foundations /> : view === 'assistant' ? <AssistantShowcase /> : (
                  <>
                    <SectionIntro title={view === 'compositions' ? 'Pieces, working together.' : 'Components with character.'}
                      description={view === 'compositions' ? 'Reusable compositions for real interfaces. Try the interactions.'
                        : 'Official shadcn primitives, thoughtfully restyled. Every preview is interactive.'} />
                    <div className="grid grid-cols-2 gap-5.5 items-start max-[1100px]:gap-4 max-md:grid-cols-1">
                      {filtered.map(demo => (
                        <Specimen key={demo.title} title={demo.title} components={demo.components} code={demo.code} wide={demo.wide}>
                          <demo.render />
                        </Specimen>
                      ))}
                    </div>
                  </>
                )}
              <footer className="border-t border-border mt-12 py-6 flex justify-between gap-5 text-[11px] text-muted-foreground max-md:flex-col max-md:gap-2">
                <span>Bauhaus-inspired. Built with shadcn + Tailwind.</span>
                <span>{iconNames.length + compactIconNames.length + learningIconNames.length} icons · {motifNames.length} motifs · {backgroundNames.length} backgrounds · Light & dark</span>
              </footer>
            </div>
          </main>
        </div>
      </SidebarProvider>
      <CommandDialog open={commandOpen} onOpenChange={setCommandOpen} title="Explore the workshop" description="Find a component or artwork collection.">
        <CommandInput placeholder="Where would you like to go?" />
        <CommandList>
          <CommandEmpty>No results found.</CommandEmpty>
          <CommandGroup heading="Collections">
            {views.map(v => (
              <CommandItem key={v} onSelect={() => { navigate(v); setCommandOpen(false) }}>{displayName(v)}</CommandItem>
            ))}
          </CommandGroup>
          <CommandGroup heading="Components">
            {componentDemos.map(demo => (
              <CommandItem key={demo.title} onSelect={() => { navigate('components', specimenId(demo.title)); setCommandOpen(false) }}>
                {demo.title}
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </TooltipProvider>
  )
}

export default function App() {
  return <Showcase />
}
