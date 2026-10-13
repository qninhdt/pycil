import type { Metadata } from 'next'
import { ProductProvider } from '@/lib/auth/product-provider'
import { Workshop } from './workshop.client'
export const metadata: Metadata = { title: 'Design workshop' }
export default function Page() { return <ProductProvider><Workshop /></ProductProvider> }
