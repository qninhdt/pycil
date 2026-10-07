import { Suspense } from 'react'
import { FlashcardFocus } from '@/components/learning/flashcard-focus'

export default function Page() { return <Suspense fallback={<main className="focus-gate">Loading flashcards…</main>}><FlashcardFocus /></Suspense> }
