import { auth } from '@clerk/nextjs/server'
import { ProductProvider } from '@/lib/auth/product-provider'
import { dataMode } from '@/lib/api/services/config'

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  if (dataMode !== 'mock' && process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
    await auth.protect()
  }
  return <ProductProvider>{children}</ProductProvider>
}
