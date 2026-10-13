'use client'

import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useServices } from '@/lib/services/provider'
import type { AccountProfile } from '@/lib/api'

export function AppAccountScope({
  initialAccount,
  children,
}: {
  initialAccount: AccountProfile | null
  children: React.ReactNode
}) {
  const { services, scope } = useServices()
  const queryClient = useQueryClient()
  const initialized = useRef(false)

  if (!initialized.current && initialAccount && services.mode === 'live') {
    queryClient.setQueryData([services.mode, scope, 'account'], initialAccount)
    initialized.current = true
  }

  useEffect(() => {
    if (initialAccount && services.mode === 'live') {
      queryClient.setQueryData([services.mode, scope, 'account'], initialAccount)
    }
  }, [initialAccount, services.mode, scope, queryClient])

  return <>{children}</>
}
