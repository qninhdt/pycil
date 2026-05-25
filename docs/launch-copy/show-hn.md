# Show HN draft

**Title:**

`Show HN: Pycil – AI vocab cards with ELO-driven spaced repetition`

**Body:**

Hi HN. I built Pycil because I kept abandoning Anki decks: every card felt the same weight, and I had no signal on which words were actually sticking. Pycil ranks each term you study with an ELO score (starting at 1000), updates the score after each review based on how fast and accurately you answered, and uses the gap between the score and the question's difficulty to push the next-review date out (or pull it in).

Add a word, an LLM (via OpenRouter) generates a clean POS + CEFR + meaning + paraphrase + example, and an MCQ pool. Sessions are timed-Leitner-ish: answer two first-attempts correctly to "review" a term, ELO + interval update, term graduates to the next round. Folders + decks for organization, 11 mastery levels for the dashboard.

Stack: Next.js 15 + Auth.js v5 (Google OAuth) on the web side, FastAPI + SQLModel on the API side, an arq worker calling LangChain → OpenRouter for generation. Postgres + Redis. Single VPS via docker-compose. Source is small and unsurprising.

Live at https://pycil.app · sample deck seeded on first sign-in.

Open questions for HN:
- Is ELO an over-fit for vocabulary? I expect mid-difficulty terms to oscillate; the time-since-review factor dampens that, but I don't have enough longitudinal data yet.
- Anyone using a different scoring system (FSRS variants, etc.) and finding ELO ergonomic?
