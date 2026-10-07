import { PublishedRoute } from '@/components/library/published-route'

export const metadata = { title: 'Published' }

export default async function Page({ params }: { params: Promise<{ identifier: string }> }) {
  const { identifier } = await params
  return <PublishedRoute identifier={identifier} />
}
