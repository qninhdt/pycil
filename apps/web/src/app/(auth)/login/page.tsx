import { Suspense } from 'react'
import { AuthPage } from '@/features/auth/auth-page.client'
export const metadata = { title: 'Sign in' }
export default function Page() { return <Suspense><AuthPage mode="login" /></Suspense> }
