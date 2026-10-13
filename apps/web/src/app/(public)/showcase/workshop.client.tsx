'use client'
import dynamic from 'next/dynamic'
const Showcase = dynamic(() => import('@/app/(public)/showcase/examples/showcase.client'), {
  ssr: false,
  loading: () => <div className="route-loading" role="status">Opening the design workshop…</div>,
})
export function Workshop() { return <Showcase /> }
