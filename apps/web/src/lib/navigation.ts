import type { IconName } from '@/components/artwork/artwork'

type NavigationItem = { href: string; title: string; icon: IconName }

export const mainNavigationItems = [
  { href: '/app', title: 'Home', icon: 'home' },
  { href: '/app/personal', title: 'My Library', icon: 'collection' },
  { href: '/app/u/me/published', title: 'Published', icon: 'published' },
  { href: '/app/discovery', title: 'Discovery', icon: 'explore' },
  { href: '/app/dictionary', title: 'Dictionary', icon: 'dictionary' },
] as const satisfies readonly NavigationItem[]
