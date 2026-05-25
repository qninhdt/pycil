export default function PrivacyPage() {
  return (
    <main className="container mx-auto max-w-3xl py-12 px-6 space-y-6">
      <h1 className="text-3xl font-bold">Privacy Policy</h1>
      <p className="text-sm text-muted-foreground">
        Draft, last updated 2026-05-26.
      </p>
      <section className="space-y-3 text-sm">
        <h2 className="text-xl font-semibold">What we store</h2>
        <p>
          Your email and Google profile info, the decks/terms/definitions you
          create, learning history (responses, mastery progression), and chat
          history. Profile images are stored in Backblaze B2 with private
          ACLs.
        </p>
        <h2 className="text-xl font-semibold">What we share</h2>
        <p>
          Nothing with third parties for marketing. We send your prompts to
          OpenRouter (LLM provider) and Google (TTS) to generate enrichment;
          neither retains identifiable data per their privacy terms.
        </p>
        <h2 className="text-xl font-semibold">Your rights</h2>
        <p>
          Delete your account from Profile → Settings; data is purged after
          14 days. Contact us before then to undo.
        </p>
      </section>
    </main>
  );
}
