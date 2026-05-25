export default function TermsPage() {
  return (
    <main className="container mx-auto max-w-3xl py-12 px-6 space-y-6">
      <h1 className="text-3xl font-bold">Terms of Service</h1>
      <p className="text-sm text-muted-foreground">
        Draft, last updated 2026-05-26.
      </p>
      <section className="space-y-3 text-sm">
        <h2 className="text-xl font-semibold">Acceptable use</h2>
        <p>
          Don&apos;t upload illegal content, abuse the AI to harm others, or
          attempt to scrape other users&apos; private decks. We reserve the
          right to suspend accounts violating these rules.
        </p>
        <h2 className="text-xl font-semibold">Public decks</h2>
        <p>
          Decks marked public are visible to all users and may be cloned.
          Cloning creates an independent copy; the cloner becomes its
          author. The original author retains rights to their original.
        </p>
        <h2 className="text-xl font-semibold">No warranty</h2>
        <p>
          Pycil is provided as-is. AI-generated content can be wrong; verify
          before relying on it for exams or assessments.
        </p>
        <h2 className="text-xl font-semibold">Liability</h2>
        <p>
          We&apos;re not liable for indirect or consequential damages
          arising from use of the service.
        </p>
      </section>
    </main>
  );
}
