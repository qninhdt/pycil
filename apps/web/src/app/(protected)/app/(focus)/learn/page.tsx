import { Suspense } from 'react'
import { QuizFocus } from '@/features/study/quiz-focus.client'

export default function Page() { return <Suspense fallback={<main className="focus-gate">Loading focus mode…</main>}><QuizFocus /></Suspense> }
