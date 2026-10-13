'use client'

import { TooltipProvider } from '@/components/ui/tooltip'
import { Toaster } from '@/components/ui/sonner'
import { useTheme } from './theme-provider.client'

export function UiProvider({ children }: { children: React.ReactNode }) {
  const { theme } = useTheme()
  return <TooltipProvider>{children}<Toaster theme={theme} position="bottom-right" /></TooltipProvider>
}
