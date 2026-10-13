import { ProductProvider } from '@/lib/auth/product-provider'

export default function Layout({ children }: { children: React.ReactNode }) {
  return <ProductProvider>{children}</ProductProvider>
}
