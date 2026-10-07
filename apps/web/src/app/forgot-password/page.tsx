import { Suspense } from 'react'
import { AuthPage } from '@/components/auth/auth-page'
export const metadata = { title: 'Reset password' }
export default function Page() { return <Suspense><AuthPage mode="reset" /></Suspense> }
