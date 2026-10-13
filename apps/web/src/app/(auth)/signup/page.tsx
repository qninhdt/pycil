import { Suspense } from 'react'
import { AuthPage } from '@/features/auth/auth-page.client'
export const metadata = { title: 'Create an account' }
export default function Page() { return <Suspense><AuthPage mode="signup" /></Suspense> }
