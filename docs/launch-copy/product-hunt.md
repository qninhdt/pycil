# Product Hunt listing

**Tagline:** Vocabulary learning that ranks you, not your cards.

**Description:**

Pycil is a fresh take on spaced-repetition vocab. Instead of grading every card the same and asking *you* to rate difficulty, Pycil gives each term an ELO score (1000 to start), updates it after every review based on accuracy + speed, and uses the gap between your ELO and the question's difficulty to schedule the next review.

Add a word, an LLM (OpenRouter) generates POS + CEFR + meaning + paraphrase + example, plus a 4-option MCQ pool. Two first-attempts correctly = term graduates this round, ELO + interval bumped. 11 mastery levels surface on the dashboard.

**Built for:** language learners, exam prep, anyone whose Anki streak died.

**Stack:** Next.js 15, FastAPI, Postgres, Redis, OpenRouter. Single VPS, docker-compose. Source is small and obvious.

**First-time experience:** Sign in with Google, dashboard auto-seeds a "Welcome" folder with a starter deck — try the learn flow before committing.

**Live:** https://pycil.app
