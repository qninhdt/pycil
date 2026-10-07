import { Suspense } from 'react'
import { QuizFocus } from '@/components/learning/quiz-focus'

export default function Page() { return <Suspense fallback={<main className="focus-gate">Loading focus mode…</main>}><QuizFocus /></Suspense> }
