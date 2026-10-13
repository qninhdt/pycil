import { Suspense } from 'react'
import { AuthPage } from '@/features/auth/auth-page.client'
export const metadata = { title: 'Reset password' }
export default function Page() { return <Suspense><AuthPage mode="reset" /></Suspense> }
