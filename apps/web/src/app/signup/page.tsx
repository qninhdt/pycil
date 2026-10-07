import { Suspense } from 'react'
import { AuthPage } from '@/components/auth/auth-page'
export const metadata = { title: 'Create an account' }
export default function Page() { return <Suspense><AuthPage mode="signup" /></Suspense> }
