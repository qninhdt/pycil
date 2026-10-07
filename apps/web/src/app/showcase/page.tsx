import type { Metadata } from 'next'
import { Workshop } from './workshop'
export const metadata: Metadata = { title: 'Design workshop' }
export default function Page() { return <Workshop /> }
