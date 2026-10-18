import { ProductProvider } from '@/lib/auth/product-provider'

export default function ProductLayout({ children }: { children: React.ReactNode }) {
  return <ProductProvider>{children}</ProductProvider>
}
