import type { IconName } from '@/components/artwork/artwork'

export type NavKey = 'home' | 'myLibrary' | 'published' | 'discovery' | 'dictionary'
type NavigationItem = { href: string; title: string; key: NavKey; icon: IconName }

export const mainNavigationItems = [
  { href: '/app', title: 'Home', key: 'home', icon: 'home' },
  { href: '/app/personal', title: 'My Library', key: 'myLibrary', icon: 'collection' },
  { href: '/app/published', title: 'Published', key: 'published', icon: 'published' },
  { href: '/app/discovery', title: 'Discovery', key: 'discovery', icon: 'explore' },
  { href: '/app/dictionary', title: 'Dictionary', key: 'dictionary', icon: 'dictionary' },
] as const satisfies readonly NavigationItem[]
