import { PublicPage, publicPageMetadata, type PublicPageProps } from '@/features/library/public-pages.server'

export function generateMetadata(props: PublicPageProps) { return publicPageMetadata(props, true) }
export default function Page(props: PublicPageProps) { return <PublicPage {...props} words /> }
