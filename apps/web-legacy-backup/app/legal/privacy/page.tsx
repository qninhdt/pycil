export const metadata = { title: "Privacy — Pycil" };

export default function PrivacyPage() {
  return (
    <main className="mx-auto max-w-2xl p-8 prose prose-sm">
      <h1>Privacy Policy</h1>
      <p>Last updated: 2026-05-25</p>

      <h2>What we store</h2>
      <p>
        Pycil stores your Google account email and display name (for sign-in),
        the vocabulary terms and decks you create, and your study history
        (ELO score, last review date, mastery level) to power spaced
        repetition. Data lives in our managed Postgres database.
      </p>

      <h2>Third parties</h2>
      <ul>
        <li>
          <strong>Google OAuth</strong> — for sign-in only. We never read
          mail, drive, or profile data beyond email + name + avatar.
        </li>
        <li>
          <strong>OpenRouter</strong> — terms you add are sent to a hosted
          LLM to generate definitions and questions. Do not enter
          confidential text.
        </li>
      </ul>

      <h2>Your rights</h2>
      <p>
        Email <a href="mailto:hi@pycil.app">hi@pycil.app</a> to delete your
        account and all associated data.
      </p>
    </main>
  );
}
